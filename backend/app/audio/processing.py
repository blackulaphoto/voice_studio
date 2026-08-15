from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path
from typing import Any


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


def _probe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise AudioProcessingError("FFprobe was not found. Install FFmpeg and ensure ffprobe is on PATH.")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", "") or "FFprobe could not inspect this audio file."
        raise AudioProcessingError(str(detail).strip()) from exc


def duration_seconds(path: Path) -> float:
    return round(float(_probe(path).get("format", {}).get("duration", 0)), 2)


def analyze_audio(path: Path) -> dict[str, Any]:
    """Return deterministic, local signal metadata and conservative quality guidance."""
    probe = _probe(path)
    streams = [item for item in probe.get("streams", []) if item.get("codec_type") == "audio"]
    if not streams:
        raise AudioProcessingError("The file does not contain a decodable audio stream.")
    stream = streams[0]
    ffmpeg = _require_ffmpeg()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "NUL"],
        capture_output=True, text=True,
    )
    log = result.stderr
    def metric(name: str) -> float | None:
        import re
        match = re.search(rf"{name}:\s*(-?(?:inf|\d+(?:\.\d+)?)) dB", log)
        return None if not match or match.group(1) == "-inf" else float(match.group(1))
    peak = metric("max_volume")
    mean = metric("mean_volume")
    duration = float(probe.get("format", {}).get("duration", 0))
    clipping = peak is not None and peak > -0.1
    if duration >= 10 and not clipping and (mean is None or mean > -35):
        rating = "excellent"
        suggestion = "Strong reference length and level. Keep the transcript exact for best identity."
    elif duration >= 3 and not clipping:
        rating = "usable"
        suggestion = "Usable reference. Ten to thirty seconds of clean single-speaker audio may improve the clone."
    else:
        rating = "caution"
        suggestion = "This reference may reduce clone quality; add longer clean speech and avoid clipped peaks."
    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": int(stream.get("channels", 0)),
        "bit_depth": int(stream.get("bits_per_sample") or stream.get("bits_per_raw_sample") or 0) or None,
        "peak_dbfs": peak,
        "mean_dbfs": mean,
        "clipping_detected": clipping,
        "quality_rating": rating,
        "suggestion": suggestion,
    }


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

    for sample in samples:
        if not sample.is_file():
            raise AudioProcessingError(f"Reference audio is unavailable: {sample.name}")
        analyze_audio(sample)

    filters = (
        "silenceremove=start_periods=1:start_duration=0.20:start_threshold=-60dB:"
        "stop_periods=0,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0.35:start_threshold=-60dB:"
        "stop_periods=0,"
        "areverse,"
        "loudnorm=I=-18:TP=-2:LRA=7"
    )
    args = [ffmpeg, "-y"]
    for sample in samples:
        args.extend(["-i", str(sample)])
    if len(samples) == 1:
        args.extend(["-vn", "-ac", "1", "-ar", "24000", "-af", filters])
    else:
        # Normalize every input before concat. This supports mixed codecs, rates, layouts,
        # bit depths, spaces, apostrophes, and Unicode without a concat manifest.
        stages = []
        labels = []
        for index in range(len(samples)):
            stages.append(f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[a{index}]")
            labels.append(f"[a{index}]")
        stages.append(f"{''.join(labels)}concat=n={len(samples)}:v=0:a=1,{filters}[out]")
        args.extend(["-filter_complex", ";".join(stages), "-map", "[out]"])
    args.extend(["-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(output_path)])
    _run(args)
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
