from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AudioProcessingError(RuntimeError):
    """Raised when ffmpeg cannot prepare or export audio."""


def _require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise AudioProcessingError(
            "FFmpeg was not found. Install FFmpeg, add it to PATH, and restart Athena Voice Studio."
        )
    return executable


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "Unknown FFmpeg error"
        raise AudioProcessingError(detail) from exc


def duration_seconds(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise AudioProcessingError("FFprobe was not found. Install FFmpeg and ensure ffprobe is on PATH.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return round(float(result.stdout.strip()), 2)


def preprocess_reference(samples: list[Path], output_path: Path) -> float:
    """Combine recordings then produce a clean 24 kHz mono WAV prompt for Qwen3-TTS.

    Original uploads are retained separately. The final prompt preserves spoken content while
    trimming leading/trailing silence, applying conservative loudness normalization, and
    resampling into the engine's preferred PCM WAV format.
    """
    if not samples:
        raise AudioProcessingError("At least one audio sample is required.")
    ffmpeg = _require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if len(samples) == 1:
        source_args = ["-i", str(samples[0])]
    else:
        concat_file = output_path.parent / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{sample.resolve().as_posix()}'\\n" for sample in samples), encoding="utf-8"
        )
        source_args = ["-f", "concat", "-safe", "0", "-i", str(concat_file)]

    filters = (
        "silenceremove=start_periods=1:start_duration=0.20:start_threshold=-60dB:"
        "stop_periods=1:stop_duration=0.35:stop_threshold=-60dB,"
        "loudnorm=I=-18:TP=-2:LRA=7"
    )
    _run(
        [
            ffmpeg,
            "-y",
            *source_args,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-af",
            filters,
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return duration_seconds(output_path)


def time_stretch(wav_path: Path, speed: float) -> None:
    """Apply FFmpeg's atempo filter in-place, preserving pitch while changing duration."""
    if speed == 1.0:
        return
    ffmpeg = _require_ffmpeg()
    temporary = wav_path.with_suffix(".stretched.wav")
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    filter_chain = ",".join(f"atempo={factor:.6f}" for factor in factors)
    _run([ffmpeg, "-y", "-i", str(wav_path), "-af", filter_chain, str(temporary)])
    temporary.replace(wav_path)


def export_mp3(wav_path: Path, mp3_path: Path) -> bool:
    """Export a high-quality MP3 alongside the canonical WAV when libmp3lame is available."""
    try:
        ffmpeg = _require_ffmpeg()
        _run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(wav_path),
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(mp3_path),
            ]
        )
        return mp3_path.exists()
    except AudioProcessingError:
        return False
