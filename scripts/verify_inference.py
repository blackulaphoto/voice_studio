"""Exercise the actual Qwen3-TTS local voice-clone adapter.

This verification uses the reference clip and transcript published in Qwen3-TTS's own
voice-cloning example. It is not shipped as an application profile and is only used to
validate that the local inference path can write new generated audio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

from app.tts.qwen_engine import QwenVoiceCloneEngine  # noqa: E402

REFERENCE_URL = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone.wav"
REFERENCE_TEXT = "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you."
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"


def main() -> None:
    fixture_dir = PROJECT / "storage" / "verification"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    reference_path = fixture_dir / "qwen-official-reference.wav"
    output_path = fixture_dir / "actual-local-clone.wav"

    if not reference_path.exists():
        response = requests.get(REFERENCE_URL, timeout=60)
        response.raise_for_status()
        reference_path.write_bytes(response.content)

    engine = QwenVoiceCloneEngine(MODEL_ID, force_device="cpu")
    print(f"Loading {MODEL_ID} on {engine.hardware().active_device} ...", flush=True)
    sample_rate = engine.synthesize(
        voice_id="qwen-official-verification",
        reference_audio=reference_path,
        reference_text=REFERENCE_TEXT,
        text="This sentence was generated locally through Athena Voice Studio's Qwen voice-cloning engine.",
        language="English",
        output_path=output_path,
    )
    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise RuntimeError("Inference did not produce a valid audio file.")
    print(f"Generated {output_path} at {sample_rate} Hz ({output_path.stat().st_size} bytes).", flush=True)


if __name__ == "__main__":
    main()
