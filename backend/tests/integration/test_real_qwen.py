from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.tts.qwen_engine import QwenVoiceCloneEngine


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("AVS_REAL_REFERENCE"), reason="Set AVS_REAL_REFERENCE to authorized audio")
def test_real_qwen_voice_clone(tmp_path: Path) -> None:
    reference = Path(os.environ["AVS_REAL_REFERENCE"])
    transcript = os.environ.get("AVS_REAL_REFERENCE_TEXT", "")
    model = os.environ.get("AVS_QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    output = tmp_path / "real-clone.wav"
    engine = QwenVoiceCloneEngine(model, os.environ.get("AVS_DEVICE"))
    engine.synthesize(
        voice_id="integration-authorized", reference_audio=reference,
        reference_text=transcript, text="This is a real local integration test.",
        language="English", output_path=output,
    )
    assert output.stat().st_size > 1024
