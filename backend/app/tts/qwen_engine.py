from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import EngineCapabilities, TTSEngine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / "storage" / "model-cache"))
PROJECT_SOX_DIR = PROJECT_ROOT / "tools" / "sox" / "sox-14.4.2"
if PROJECT_SOX_DIR.joinpath("sox.exe").is_file():
    os.environ["PATH"] = f"{PROJECT_SOX_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


class EngineUnavailableError(RuntimeError):
    """Raised when the selected local inference engine cannot be loaded."""


@dataclass(frozen=True)
class HardwareInfo:
    active_device: str
    accelerator_available: bool
    gpu_name: str | None
    vram_total_mb: int | None


class QwenVoiceCloneEngine(TTSEngine):
    """Lazy, process-wide wrapper around Qwen3-TTS Base voice-cloning inference.

    The model stays resident after its first generation. Reusable prompt features are cached by
    voice ID, avoiding repeated reference-audio encoding for persistent Athena responses.
    """

    def __init__(self, model_id: str, force_device: str | None = None) -> None:
        self.engine_id = "qwen3"
        self.display_name = "Qwen3-TTS Base"
        self.model_id = model_id
        self.force_device = force_device
        self._model: Any | None = None
        self._hardware: HardwareInfo | None = None
        self._prompt_cache: dict[str, Any] = {}
        self._last_timings: dict[str, float] = {}
        self._last_effective_settings: dict[str, Any] = {}
        self._lock = threading.RLock()

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
        return self._model is not None

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

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                import torch
                from qwen_tts import Qwen3TTSModel
            except ImportError as exc:
                raise EngineUnavailableError(
                    "Qwen3-TTS is not installed. Run the Windows setup script, then restart the application."
                ) from exc

            hardware = self.hardware()
            # Qwen's Base weights are large enough that float32 CPU loading is needlessly
            # memory-intensive. bfloat16 keeps the local 0.6B fallback practical on modern
            # CPUs while CUDA uses the same memory-efficient dtype.
            dtype = self._safe_dtype(torch, hardware)
            kwargs: dict[str, Any] = {
                "device_map": hardware.active_device,
                "dtype": dtype,
            }
            local_snapshot = self._local_snapshot_path()
            if local_snapshot:
                # Once a complete snapshot exists, normal synthesis is strictly local.
                # This also prevents Hugging Face metadata probes from breaking an
                # otherwise valid offline installation.
                kwargs["local_files_only"] = True
            # FlashAttention is optional and only selected on CUDA because it is not portable to CPU.
            if hardware.accelerator_available:
                try:
                    import flash_attn  # noqa: F401

                    kwargs["attn_implementation"] = "flash_attention_2"
                except ImportError:
                    pass
            try:
                model_source = str(local_snapshot) if local_snapshot else self.model_id
                self._model = Qwen3TTSModel.from_pretrained(model_source, **kwargs)
            except Exception as exc:  # pass framework/model errors as actionable API detail
                raise EngineUnavailableError(
                    f"Could not load local model '{self.model_id}' on {hardware.active_device}: {exc}"
                ) from exc

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._prompt_cache.clear()
            try:
                import gc
                import torch
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def clear_prompt(self, voice_id: str) -> None:
        with self._lock:
            for key in [key for key in self._prompt_cache if key == voice_id or key.startswith(f"{voice_id}:")]:
                self._prompt_cache.pop(key, None)

    def _prompt_for(
        self, voice_id: str, reference_audio: Path, reference_text: str | None
    ) -> Any:
        if voice_id in self._prompt_cache:
            return self._prompt_cache[voice_id]
        assert self._model is not None
        prompt = self._model.create_voice_clone_prompt(
            ref_audio=str(reference_audio),
            ref_text=reference_text or "",
            x_vector_only_mode=not bool(reference_text),
        )
        self._prompt_cache[voice_id] = prompt
        return prompt

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
        total_started = time.perf_counter()
        load_started = time.perf_counter()
        self.load()
        load_seconds = time.perf_counter() - load_started
        with self._lock:
            assert self._model is not None
            prompt_started = time.perf_counter()
            prompt = self._prompt_for(voice_id, reference_audio, reference_text)
            prompt_seconds = time.perf_counter() - prompt_started
            generation_kwargs = self._generation_kwargs(settings)
            try:
                import soundfile as sf

                inference_started = time.perf_counter()
                wavs, sample_rate = self._model.generate_voice_clone(
                    text=text,
                    language=language,
                    voice_clone_prompt=prompt,
                    **generation_kwargs,
                )
                inference_seconds = time.perf_counter() - inference_started
                write_started = time.perf_counter()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(output_path), wavs[0], sample_rate)
                write_seconds = time.perf_counter() - write_started
                self._last_effective_settings = generation_kwargs
                self._last_timings = {
                    "model_load_seconds": round(load_seconds, 3),
                    "voice_prompt_seconds": round(prompt_seconds, 3),
                    "inference_and_decode_seconds": round(inference_seconds, 3),
                    "wav_write_seconds": round(write_seconds, 3),
                    "engine_total_seconds": round(time.perf_counter() - total_started, 3),
                }
                return int(sample_rate)
            except Exception as exc:
                raise EngineUnavailableError(f"Local voice synthesis failed: {exc}") from exc
