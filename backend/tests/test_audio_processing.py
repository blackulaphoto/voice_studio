from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.processing import AudioProcessingError, analyze_audio, preprocess_reference


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg unavailable")


def make_tone(path: Path, *, rate: int, channels: int, codec: str | None = None) -> None:
    args = [
        shutil.which("ffmpeg") or "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"sine=frequency=330:sample_rate={rate}:duration=1.2", "-ac", str(channels),
    ]
    if codec:
        args.extend(["-c:a", codec])
    args.append(str(path))
    subprocess.run(args, check=True, capture_output=True)


@pytest.mark.parametrize(
    ("first_suffix", "second_suffix", "first_rate", "second_rate", "first_channels", "second_channels", "codec"),
    [
        (".wav", ".wav", 44100, 24000, 2, 1, None),
        (".wav", ".mp3", 48000, 22050, 1, 2, "libmp3lame"),
    ],
)
def test_preprocess_mixed_references(
    tmp_path: Path, first_suffix: str, second_suffix: str, first_rate: int,
    second_rate: int, first_channels: int, second_channels: int, codec: str | None,
) -> None:
    first = tmp_path / f"first sample{first_suffix}"
    second = tmp_path / f"voix d'été_日本語{second_suffix}"
    make_tone(first, rate=first_rate, channels=first_channels)
    make_tone(second, rate=second_rate, channels=second_channels, codec=codec)
    output = tmp_path / "processed" / "reference.wav"

    duration = preprocess_reference([first, second], output)
    details = analyze_audio(output)

    assert output.is_file()
    assert duration >= 1.8
    assert details["sample_rate"] == 24000
    assert details["channels"] == 1


def test_invalid_audio_is_actionable(tmp_path: Path) -> None:
    invalid = tmp_path / "not audio.wav"
    invalid.write_text("not audio", encoding="utf-8")
    with pytest.raises(AudioProcessingError):
        preprocess_reference([invalid], tmp_path / "out.wav")


def test_internal_silence_does_not_truncate_later_speech(tmp_path: Path) -> None:
    source = tmp_path / "speech with pause.wav"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=1.2",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000:duration=1.0",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=1.2",
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
            "-map", "[out]", str(source),
        ],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "processed.wav"

    duration = preprocess_reference([source], output)

    # The detector windows trim some material at the two outer edges, but the
    # result must retain audio after the one-second internal pause. The former
    # stop_periods=1 pipeline returned only the first ~1.2-second segment.
    assert duration >= 2.5
