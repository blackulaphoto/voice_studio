from __future__ import annotations

import time
from types import SimpleNamespace
from pathlib import Path

import pytest

import app.tts.qwen_engine as qwen_engine_module
from app.tts.qwen_engine import EngineUnavailableError, HardwareInfo, QwenVoiceCloneEngine, _filter_prompt_cache


def _fake_worker_echo(model_id, force_device, request_queue, response_queue):
    """Standin for _worker_main: echoes the payload back immediately, or sleeps effectively
    forever if payload['hang'] is set, to exercise the timeout-and-kill path without needing
    the real (multi-GB) Qwen model. Must stay at module level: multiprocessing's Windows
    "spawn" start method pickles the target function by import path, not by value.
    """
    while True:
        message = request_queue.get()
        if message is None:
            break
        request_id, _kind, payload = message
        if payload.get("hang"):
            time.sleep(9999)
        response_queue.put((request_id, "ok", {"echo": payload}))


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


def test_quality_preserves_qwen_generation_defaults() -> None:
    assert QwenVoiceCloneEngine._generation_kwargs({"_mode": "quality"}) == {}


def test_fast_uses_qwen_non_streaming_text_path() -> None:
    assert QwenVoiceCloneEngine._generation_kwargs({"_mode": "fast"}) == {
        "non_streaming_mode": True
    }


def test_engine_forwards_only_supported_sampling_controls() -> None:
    assert QwenVoiceCloneEngine._generation_kwargs({
        "_mode": "quality", "temperature": 0.8, "top_p": 0.9,
        "pace": 0.95, "invented_control": "no",
    }) == {"temperature": 0.8, "top_p": 0.9}


def test_clear_prompt_removes_base_and_performance_conditioning() -> None:
    # The prompt cache itself now lives inside the worker subprocess (see qwen_engine.py's
    # module docstring for why), so this tests the pure filtering logic directly rather than
    # engine.clear_prompt(), which requires a live worker to exercise meaningfully.
    cache = {"voice": "base", "voice:performance:warm": "warm", "other": "untouched"}
    assert _filter_prompt_cache(cache, "voice") == {"other": "untouched"}


def test_clear_prompt_is_a_noop_without_a_running_worker() -> None:
    # Must not hang or raise just because no worker process has been started yet.
    QwenVoiceCloneEngine("model").clear_prompt("voice")


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


def test_send_round_trips_through_a_real_subprocess(monkeypatch) -> None:
    monkeypatch.setattr(qwen_engine_module, "_worker_main", _fake_worker_echo)
    engine = QwenVoiceCloneEngine("model")
    try:
        result = engine._send("synthesize", {"hang": False, "x": 1}, timeout=20.0)
        assert result == {"echo": {"hang": False, "x": 1}}
        assert engine._process is not None and engine._process.is_alive()
    finally:
        engine._kill_worker()


def test_send_kills_the_worker_and_raises_on_timeout(monkeypatch) -> None:
    # This is the actual fix for the incident: a hung generation must be forcibly terminated,
    # not left to run indefinitely, and the caller must get a clear error instead of hanging too.
    monkeypatch.setattr(qwen_engine_module, "_worker_main", _fake_worker_echo)
    engine = QwenVoiceCloneEngine("model")
    try:
        with pytest.raises(EngineUnavailableError, match="timed out"):
            engine._send("synthesize", {"hang": True}, timeout=2.0)
        assert engine._process is None  # confirms the stuck worker was actually killed
    finally:
        engine._kill_worker()


def test_worker_respawns_cleanly_after_a_timeout_kill(monkeypatch) -> None:
    monkeypatch.setattr(qwen_engine_module, "_worker_main", _fake_worker_echo)
    engine = QwenVoiceCloneEngine("model")
    try:
        with pytest.raises(EngineUnavailableError, match="timed out"):
            engine._send("synthesize", {"hang": True}, timeout=2.0)
        # The next request must work normally against a freshly spawned worker, not stay broken.
        result = engine._send("synthesize", {"hang": False, "y": 2}, timeout=20.0)
        assert result == {"echo": {"hang": False, "y": 2}}
    finally:
        engine._kill_worker()


def test_synthesize_timeout_scales_with_max_new_tokens(monkeypatch) -> None:
    engine = QwenVoiceCloneEngine("model")
    captured = {}

    def fake_send(kind, payload, timeout):
        captured["timeout"] = timeout
        return {"sample_rate": 24000, "effective_settings": {}, "timings": {}}

    monkeypatch.setattr(engine, "_send", fake_send)
    engine.synthesize(
        voice_id="v", reference_audio=Path("ref.wav"), reference_text=None,
        text="hello", language="English", output_path=Path("out.wav"),
        settings={"max_new_tokens": 1000},
    )
    # 1000 tokens * 1.3s/token = 1300s, well above the 90s floor.
    assert captured["timeout"] == pytest.approx(1300.0)


def test_synthesize_timeout_has_a_floor_for_short_text(monkeypatch) -> None:
    engine = QwenVoiceCloneEngine("model")
    captured = {}

    def fake_send(kind, payload, timeout):
        captured["timeout"] = timeout
        return {"sample_rate": 24000, "effective_settings": {}, "timings": {}}

    monkeypatch.setattr(engine, "_send", fake_send)
    engine.synthesize(
        voice_id="v", reference_audio=Path("ref.wav"), reference_text=None,
        text="hi", language="English", output_path=Path("out.wav"),
        settings={"max_new_tokens": 10},
    )
    # 10 tokens * 1.3s/token = 13s, well under the 90s floor — the floor must win.
    assert captured["timeout"] == pytest.approx(90.0)
