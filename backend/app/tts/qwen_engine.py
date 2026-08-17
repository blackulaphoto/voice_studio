from __future__ import annotations

import multiprocessing as mp
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import EngineCapabilities, TTSEngine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_CACHE_DIR = str(PROJECT_ROOT / "storage" / "model-cache")
PROJECT_SOX_DIR = PROJECT_ROOT / "tools" / "sox" / "sox-14.4.2"


def _configure_process_environment() -> None:
    """Idempotent env setup. Runs in the main process at import time, and again inside the
    worker subprocess (a fresh interpreter on Windows spawn does not inherit these)."""
    os.environ.setdefault("HF_HOME", MODEL_CACHE_DIR)
    if PROJECT_SOX_DIR.joinpath("sox.exe").is_file():
        sox_dir = str(PROJECT_SOX_DIR)
        if sox_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{sox_dir}{os.pathsep}{os.environ.get('PATH', '')}"


_configure_process_environment()


class EngineUnavailableError(RuntimeError):
    """Raised when the selected local inference engine cannot be loaded."""


@dataclass(frozen=True)
class HardwareInfo:
    active_device: str
    accelerator_available: bool
    gpu_name: str | None
    vram_total_mb: int | None


def _filter_prompt_cache(cache: dict[str, Any], voice_id: str) -> dict[str, Any]:
    """Pure filtering logic for clear_prompt — extracted so it's unit-testable without a live
    worker subprocess, since the actual prompt cache now lives inside that subprocess."""
    return {key: value for key, value in cache.items() if not (key == voice_id or key.startswith(f"{voice_id}:"))}


def _worker_main(model_id: str, force_device: str | None, request_queue: Any, response_queue: Any) -> None:
    """Entry point for the persistent Qwen worker subprocess.

    Services one request at a time from request_queue until it receives a None sentinel (clean
    shutdown) or is forcibly killed by the parent (timeout / crash recovery — see
    QwenVoiceCloneEngine._send). Owns the actual torch/model instance and the voice-clone prompt
    cache; nothing here is shared with the parent FastAPI process, so killing this process can
    never corrupt parent state or leave the model in a bad in-process state. This exists
    specifically because Python cannot safely cancel a blocking call running inside a thread —
    only a whole process can be reliably killed. See PROJECT_SCHEMA_AND_HANDOFF.md, "Phase 4
    follow-up 5" for the incident (repeated 10-20+ minute stalls on degenerate Qwen output) that
    made this necessary.
    """
    _configure_process_environment()
    helper = QwenVoiceCloneEngine(model_id, force_device)
    model: Any | None = None
    prompt_cache: dict[str, Any] = {}

    def load() -> Any:
        nonlocal model
        if model is not None:
            return model
        import torch
        from qwen_tts import Qwen3TTSModel

        hardware = helper.hardware()
        dtype = helper._safe_dtype(torch, hardware)
        kwargs: dict[str, Any] = {"device_map": hardware.active_device, "dtype": dtype}
        local_snapshot = helper._local_snapshot_path()
        if local_snapshot:
            kwargs["local_files_only"] = True
        if hardware.accelerator_available:
            try:
                import flash_attn  # noqa: F401

                kwargs["attn_implementation"] = "flash_attention_2"
            except ImportError:
                pass
        try:
            model_source = str(local_snapshot) if local_snapshot else model_id
            model = Qwen3TTSModel.from_pretrained(model_source, **kwargs)
        except Exception as exc:
            raise EngineUnavailableError(
                f"Could not load local model '{model_id}' on {hardware.active_device}: {exc}"
            ) from exc
        return model

    while True:
        message = request_queue.get()
        if message is None:
            break
        request_id, kind, payload = message
        try:
            if kind == "synthesize":
                total_started = time.perf_counter()
                load_started = time.perf_counter()
                active_model = load()
                load_seconds = time.perf_counter() - load_started

                voice_id = payload["voice_id"]
                prompt_started = time.perf_counter()
                if voice_id in prompt_cache:
                    prompt = prompt_cache[voice_id]
                else:
                    prompt = active_model.create_voice_clone_prompt(
                        ref_audio=payload["reference_audio"],
                        ref_text=payload["reference_text"] or "",
                        x_vector_only_mode=not bool(payload["reference_text"]),
                    )
                    prompt_cache[voice_id] = prompt
                prompt_seconds = time.perf_counter() - prompt_started

                import soundfile as sf

                generation_kwargs = payload["generation_kwargs"]
                inference_started = time.perf_counter()
                wavs, sample_rate = active_model.generate_voice_clone(
                    text=payload["text"],
                    language=payload["language"],
                    voice_clone_prompt=prompt,
                    **generation_kwargs,
                )
                inference_seconds = time.perf_counter() - inference_started
                write_started = time.perf_counter()
                output_path = Path(payload["output_path"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(output_path), wavs[0], sample_rate)
                write_seconds = time.perf_counter() - write_started

                response_queue.put((request_id, "ok", {
                    "sample_rate": int(sample_rate),
                    "effective_settings": generation_kwargs,
                    "timings": {
                        "model_load_seconds": round(load_seconds, 3),
                        "voice_prompt_seconds": round(prompt_seconds, 3),
                        "inference_and_decode_seconds": round(inference_seconds, 3),
                        "wav_write_seconds": round(write_seconds, 3),
                        "engine_total_seconds": round(time.perf_counter() - total_started, 3),
                    },
                }))
            elif kind == "clear_prompt":
                prompt_cache = _filter_prompt_cache(prompt_cache, payload["voice_id"])
                response_queue.put((request_id, "ok", None))
            elif kind == "unload":
                model = None
                prompt_cache = {}
                try:
                    import gc

                    import torch

                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                response_queue.put((request_id, "ok", None))
            else:
                response_queue.put((request_id, "error", f"Unknown request kind '{kind}'"))
        except Exception as exc:  # keep the worker loop alive; report the failure and continue
            response_queue.put((request_id, "error", str(exc)))


class QwenVoiceCloneEngine(TTSEngine):
    """Process-boundary wrapper around a persistent Qwen3-TTS worker subprocess.

    All real model inference happens in a separate child process (see _worker_main), never in
    this one. synthesize() sends a request and waits up to a token-budget-proportional timeout;
    if the worker hasn't responded in time, it is forcibly killed (a hung/degenerate PyTorch
    generate() call cannot be safely cancelled any other way) and a fresh worker is spawned for
    the next request. This reloads the model once (~15-20s) — a one-time cost paid only when a
    runaway actually happens, not on every request.
    """

    # Calibrated from a real incident: 1800 max_new_tokens took 1412s of pure inference to
    # exhaust on this CPU ⇒ ~0.785s/token. 1.3s/token keeps real margin over that measurement
    # (hardware variance, background load) while staying proportional to how much generation
    # was actually requested — a flat timeout would either kill legitimate long paragraphs too
    # early or let short ones hang far longer than necessary. See PROJECT_SCHEMA_AND_HANDOFF.md,
    # "Phase 4 follow-up 5".
    SECONDS_PER_TOKEN_TIMEOUT = 1.3
    MIN_TIMEOUT_SECONDS = 90.0

    def __init__(self, model_id: str, force_device: str | None = None) -> None:
        self.engine_id = "qwen3"
        self.display_name = "Qwen3-TTS Base"
        self.model_id = model_id
        self.force_device = force_device
        self._hardware: HardwareInfo | None = None
        self._last_timings: dict[str, float] = {}
        self._last_effective_settings: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._process: Any | None = None
        self._request_queue: Any | None = None
        self._response_queue: Any | None = None
        self._request_counter = 0
        self._worker_has_loaded_model = False

    def hardware(self) -> HardwareInfo:
        if self._hardware is not None:
            return self._hardware
        try:
            import torch
        except ImportError:
            self._hardware = HardwareInfo("unavailable", False, None, None)
            return self._hardware

        if self.force_device:
            active_device = self.force_device
        else:
            active_device = "cuda:0" if torch.cuda.is_available() else "cpu"

        if active_device.startswith("cuda") and torch.cuda.is_available():
            index = int(active_device.split(":")[1]) if ":" in active_device else 0
            properties = torch.cuda.get_device_properties(index)
            self._hardware = HardwareInfo(
                active_device=active_device,
                accelerator_available=True,
                gpu_name=torch.cuda.get_device_name(index),
                vram_total_mb=round(properties.total_memory / (1024 * 1024)),
            )
        else:
            self._hardware = HardwareInfo("cpu", False, None, None)
        return self._hardware

    @property
    def is_loaded(self) -> bool:
        return self._worker_has_loaded_model

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            multilingual=True,
            speed=True,
            supported_languages=("English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian", "Auto"),
        )

    @property
    def last_timings(self) -> dict[str, float]:
        return dict(self._last_timings)

    @property
    def last_effective_settings(self) -> dict[str, Any]:
        return dict(self._last_effective_settings)

    @staticmethod
    def _generation_kwargs(settings: dict[str, Any] | None) -> dict[str, Any]:
        settings = settings or {}
        mode = settings.get("_mode", "quality")
        kwargs = {"non_streaming_mode": True} if mode == "fast" else {}
        for name in (
            "temperature", "top_k", "top_p", "repetition_penalty",
            "subtalker_temperature", "subtalker_top_k", "subtalker_top_p", "max_new_tokens",
        ):
            if name in settings:
                kwargs[name] = settings[name]
        return kwargs

    def _safe_dtype(self, torch: Any, hardware: HardwareInfo) -> Any:
        if not hardware.accelerator_available:
            return torch.float32
        index = int(hardware.active_device.split(":")[1]) if ":" in hardware.active_device else 0
        major, _minor = torch.cuda.get_device_capability(index)
        return torch.bfloat16 if major >= 8 and torch.cuda.is_bf16_supported() else torch.float16

    def _local_snapshot_path(self) -> Path | None:
        repo_dir = (
            Path(os.environ["HF_HOME"])
            / "hub"
            / f"models--{self.model_id.replace('/', '--')}"
            / "snapshots"
        )
        for snapshot in sorted(repo_dir.glob("*"), reverse=True):
            if (
                snapshot.is_dir()
                and snapshot.joinpath("config.json").is_file()
                and snapshot.joinpath("model.safetensors").is_file()
            ):
                return snapshot.resolve()
        return None

    def _local_snapshot_available(self) -> bool:
        return self._local_snapshot_path() is not None

    def _ensure_worker(self) -> None:
        """Must be called with self._lock held."""
        if self._process is not None and self._process.is_alive():
            return
        ctx = mp.get_context("spawn")
        self._request_queue = ctx.Queue()
        self._response_queue = ctx.Queue()
        self._process = ctx.Process(
            target=_worker_main,
            args=(self.model_id, self.force_device, self._request_queue, self._response_queue),
            daemon=True,
        )
        self._process.start()
        self._worker_has_loaded_model = False

    def _kill_worker(self) -> None:
        """Must be called with self._lock held."""
        if self._process is not None:
            try:
                self._process.kill()
                self._process.join(timeout=5)
            except Exception:
                pass
        self._process = None
        self._request_queue = None
        self._response_queue = None
        self._worker_has_loaded_model = False

    def _send(self, kind: str, payload: dict[str, Any], timeout: float) -> Any:
        with self._lock:
            self._ensure_worker()
            self._request_counter += 1
            request_id = self._request_counter
            self._request_queue.put((request_id, kind, payload))
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill_worker()
                    raise EngineUnavailableError(
                        f"Generation timed out after {timeout:.0f}s with no response. This is "
                        "almost always a degenerate/runaway Qwen3-TTS generation (a documented "
                        "upstream issue: github.com/QwenLM/Qwen3-TTS/discussions/211), not a "
                        "problem with this app. The stuck worker was terminated; please try "
                        "generating again — a fresh attempt is a new random draw and often "
                        "succeeds. If it keeps happening on the same voice/text, that combination "
                        "may be a specific trigger worth avoiding."
                    )
                if self._process is None or not self._process.is_alive():
                    self._kill_worker()
                    raise EngineUnavailableError(
                        "The local synthesis worker exited unexpectedly. Please try generating again."
                    )
                try:
                    got_id, status, result = self._response_queue.get(timeout=min(1.0, remaining))
                except queue.Empty:
                    continue
                if got_id != request_id:
                    continue  # stale response from an already-abandoned prior request
                if status == "error":
                    raise EngineUnavailableError(f"Local voice synthesis failed: {result}")
                return result

    def load(self) -> None:
        with self._lock:
            self._ensure_worker()

    def unload(self) -> None:
        with self._lock:
            if self._process is not None and self._process.is_alive():
                try:
                    self._send("unload", {}, timeout=30.0)
                except EngineUnavailableError:
                    pass
            self._kill_worker()

    def clear_prompt(self, voice_id: str) -> None:
        with self._lock:
            if self._process is None or not self._process.is_alive():
                return
            try:
                self._send("clear_prompt", {"voice_id": voice_id}, timeout=10.0)
            except EngineUnavailableError:
                pass

    def synthesize(
        self,
        *,
        voice_id: str,
        reference_audio: Path,
        reference_text: str | None,
        text: str,
        language: str,
        output_path: Path,
        settings: dict[str, Any] | None = None,
    ) -> int:
        """Generate actual clone audio through the installed Qwen3-TTS Base model."""
        generation_kwargs = self._generation_kwargs(settings)
        max_tokens = generation_kwargs.get("max_new_tokens", 400)
        timeout = max(self.MIN_TIMEOUT_SECONDS, max_tokens * self.SECONDS_PER_TOKEN_TIMEOUT)
        payload = {
            "voice_id": voice_id,
            "reference_audio": str(reference_audio),
            "reference_text": reference_text,
            "text": text,
            "language": language,
            "output_path": str(output_path),
            "generation_kwargs": generation_kwargs,
        }
        result = self._send("synthesize", payload, timeout=timeout)
        self._worker_has_loaded_model = True
        self._last_timings = result["timings"]
        self._last_effective_settings = result["effective_settings"]
        return result["sample_rate"]
