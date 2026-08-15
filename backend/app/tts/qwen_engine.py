from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EngineUnavailableError(RuntimeError):
    """Raised when the selected local inference engine cannot be loaded."""


@dataclass(frozen=True)
class HardwareInfo:
    active_device: str
    accelerator_available: bool
    gpu_name: str | None
    vram_total_mb: int | None


class QwenVoiceCloneEngine:
    """Lazy, process-wide wrapper around Qwen3-TTS Base voice-cloning inference.

    The model stays resident after its first generation. Reusable prompt features are cached by
    voice ID, avoiding repeated reference-audio encoding for persistent Athena responses.
    """

    def __init__(self, model_id: str, force_device: str | None = None) -> None:
        self.model_id = model_id
        self.force_device = force_device
        self._model: Any | None = None
        self._hardware: HardwareInfo | None = None
        self._prompt_cache: dict[str, Any] = {}
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
            dtype = torch.bfloat16
            kwargs: dict[str, Any] = {
                "device_map": hardware.active_device,
                "dtype": dtype,
            }
            # FlashAttention is optional and only selected on CUDA because it is not portable to CPU.
            if hardware.accelerator_available:
                try:
                    import flash_attn  # noqa: F401

                    kwargs["attn_implementation"] = "flash_attention_2"
                except ImportError:
                    pass
            try:
                self._model = Qwen3TTSModel.from_pretrained(self.model_id, **kwargs)
            except Exception as exc:  # pass framework/model errors as actionable API detail
                raise EngineUnavailableError(
                    f"Could not load local model '{self.model_id}' on {hardware.active_device}: {exc}"
                ) from exc

    def clear_prompt(self, voice_id: str) -> None:
        with self._lock:
            self._prompt_cache.pop(voice_id, None)

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
    ) -> int:
        """Generate actual clone audio through the installed Qwen3-TTS Base model."""
        self.load()
        with self._lock:
            assert self._model is not None
            prompt = self._prompt_for(voice_id, reference_audio, reference_text)
            try:
                import soundfile as sf

                wavs, sample_rate = self._model.generate_voice_clone(
                    text=text,
                    language=language,
                    voice_clone_prompt=prompt,
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(output_path), wavs[0], sample_rate)
                return int(sample_rate)
            except Exception as exc:
                raise EngineUnavailableError(f"Local voice synthesis failed: {exc}") from exc
