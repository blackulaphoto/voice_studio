from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from app.tts.qwen_engine import HardwareInfo, QwenVoiceCloneEngine


class FakeCuda:
    def __init__(self, major: int, bf16: bool) -> None:
        self.major = major
        self.bf16 = bf16

    def get_device_capability(self, _index: int):
        return self.major, 0

    def is_bf16_supported(self):
        return self.bf16


def fake_torch(major: int = 8, bf16: bool = True):
    return SimpleNamespace(cuda=FakeCuda(major, bf16), float32="fp32", float16="fp16", bfloat16="bf16")


def test_cpu_uses_fp32() -> None:
    engine = QwenVoiceCloneEngine("model")
    assert engine._safe_dtype(fake_torch(), HardwareInfo("cpu", False, None, None)) == "fp32"


def test_pre_ampere_cuda_uses_fp16() -> None:
    engine = QwenVoiceCloneEngine("model")
    assert engine._safe_dtype(fake_torch(7), HardwareInfo("cuda:0", True, "GPU", 8000)) == "fp16"


def test_ampere_cuda_uses_bf16_only_when_supported() -> None:
    engine = QwenVoiceCloneEngine("model")
    assert engine._safe_dtype(fake_torch(8, True), HardwareInfo("cuda:0", True, "GPU", 8000)) == "bf16"
    assert engine._safe_dtype(fake_torch(8, False), HardwareInfo("cuda:0", True, "GPU", 8000)) == "fp16"


def test_capabilities_do_not_advertise_fake_controls() -> None:
    capabilities = QwenVoiceCloneEngine("model").capabilities()
    assert capabilities.voice_cloning is True
    assert capabilities.speed is True
    assert capabilities.temperature is False
    assert capabilities.emotion is False
    assert capabilities.true_streaming is False


def test_complete_local_snapshot_enables_offline_loading(monkeypatch, tmp_path: Path) -> None:
    model_id = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    snapshot = tmp_path / "hub" / "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base" / "snapshots" / "revision"
    snapshot.mkdir(parents=True)
    snapshot.joinpath("config.json").write_text("{}", encoding="utf-8")
    snapshot.joinpath("model.safetensors").write_bytes(b"weights")
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    engine = QwenVoiceCloneEngine(model_id)
    assert engine._local_snapshot_available() is True
    assert engine._local_snapshot_path() == snapshot.resolve()


def test_incomplete_snapshot_does_not_force_offline_loading(monkeypatch, tmp_path: Path) -> None:
    snapshot = tmp_path / "hub" / "models--Qwen--model" / "snapshots" / "revision"
    snapshot.mkdir(parents=True)
    snapshot.joinpath("config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    assert QwenVoiceCloneEngine("Qwen/model")._local_snapshot_available() is False
