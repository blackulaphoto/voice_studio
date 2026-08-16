from __future__ import annotations

import re
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


def trim_outer_silence(
    wav_path: Path, *, threshold_db: float = -60.0, start_duration: float = 0.20, end_duration: float = 0.35
) -> float:
    """Trim only leading/trailing silence from a generated WAV in place.

    Uses stop_periods=0 on both the forward and reversed pass, so internal pauses
    (intentional delivery timing between sentences) are never touched. Threshold matches
    the proven-safe value already used for voice references in preprocess_reference.

    Critically, start_silence is set equal to start_duration on each pass. FFmpeg's
    silenceremove needs to observe start_duration worth of continuous non-silence before
    it trusts audio has resumed, and unconditionally discards (start_duration - start_silence)
    even when there was no silence at all to begin with. An earlier version with a smaller
    start_silence than start_duration paid that forced "warm-up cost" on every generation,
    clipping into real speech regardless of threshold (e.g. the "B" in "Brandon", the
    trailing "g" in "something"). Matching them makes the forced loss ~0 on clean audio.
    Returns the number of seconds removed so callers can log it as honest evidence.
    """
    ffmpeg = _require_ffmpeg()
    before = duration_seconds(wav_path)
    temporary = wav_path.with_suffix(".trimmed.wav")
    filters = (
        f"silenceremove=start_periods=1:start_duration={start_duration}:start_threshold={threshold_db}dB:"
        f"start_silence={start_duration}:stop_periods=0,"
        "areverse,"
        f"silenceremove=start_periods=1:start_duration={end_duration}:start_threshold={threshold_db}dB:"
        f"start_silence={end_duration}:stop_periods=0,"
        "areverse"
    )
    _run([ffmpeg, "-y", "-i", str(wav_path), "-af", filters, "-c:a", "pcm_s16le", str(temporary)])
    temporary.replace(wav_path)
    after = duration_seconds(wav_path)
    return round(max(before - after, 0.0), 3)


def _detect_silences(path: Path, *, threshold_db: float, min_duration: float) -> list[tuple[float, float]]:
    """Return closed (start, end) silence intervals via ffmpeg's silencedetect.

    Intervals still open at end-of-file (a silence_start with no matching silence_end) are
    dropped, since callers only want fully-bounded gaps.
    """
    ffmpeg = _require_ffmpeg()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af",
         f"silencedetect=noise={threshold_db}dB:duration={min_duration}", "-f", "null", "NUL"],
        capture_output=True, text=True,
    )
    log = result.stderr
    starts = [float(value) for value in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", log)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*(-?\d+(?:\.\d+)?)", log)]
    return list(zip(starts, ends))


def rescale_internal_pauses(
    wav_path: Path, *, pause_scale: float, threshold_db: float = -45.0, min_gap: float = 0.15
) -> float:
    """Stretch or compress only the internal silence gaps of a WAV; speech is untouched.

    Must run after trim_outer_silence, so every detected gap is genuinely internal (never at
    the very start or unclosed at end-of-file — both are defensively excluded again here).
    Rebuilds the file as alternating speech/silence segments, replacing each gap with
    pause_scale times its original duration of true digital silence. Each new gap is bounded
    to [0.02s, min(4x original, 4.0s)] so a slider value cannot produce pathological silence.
    Returns the net seconds added (positive) or removed (negative).
    """
    if abs(pause_scale - 1.0) < 1e-6:
        return 0.0
    ffmpeg = _require_ffmpeg()
    total = duration_seconds(wav_path)
    gaps = _detect_silences(wav_path, threshold_db=threshold_db, min_duration=min_gap)
    internal = [(start, end) for start, end in gaps if start > 0.01 and end < total - 0.01]
    if not internal:
        return 0.0

    targets = [max(0.02, min((end - start) * pause_scale, (end - start) * 4.0, 4.0)) for start, end in internal]
    total_silence_needed = sum(targets) + 1.0

    filter_stages: list[str] = []
    concat_labels: list[str] = []
    cursor = 0.0
    silence_cursor = 0.0
    segment = 0

    for (start, end), target_gap in zip(internal, targets):
        if cursor < start - 1e-6:
            label = f"sp{segment}"
            segment += 1
            filter_stages.append(f"[0:a]atrim={cursor:.6f}:{start:.6f},asetpts=PTS-STARTPTS[{label}]")
            concat_labels.append(f"[{label}]")
        silence_label = f"si{segment}"
        segment += 1
        filter_stages.append(
            f"[1:a]atrim={silence_cursor:.6f}:{silence_cursor + target_gap:.6f},"
            f"asetpts=PTS-STARTPTS[{silence_label}]"
        )
        concat_labels.append(f"[{silence_label}]")
        silence_cursor += target_gap
        cursor = end

    if cursor < total - 1e-6:
        label = f"sp{segment}"
        filter_stages.append(f"[0:a]atrim={cursor:.6f}:{total:.6f},asetpts=PTS-STARTPTS[{label}]")
        concat_labels.append(f"[{label}]")

    filter_stages.append(f"{''.join(concat_labels)}concat=n={len(concat_labels)}:v=0:a=1[out]")

    temporary = wav_path.with_suffix(".paused.wav")
    _run([
        ffmpeg, "-y",
        "-i", str(wav_path),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=mono:sample_rate=24000:duration={total_silence_needed:.3f}",
        "-filter_complex", ";".join(filter_stages),
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(temporary),
    ])
    temporary.replace(wav_path)
    after = duration_seconds(wav_path)
    return round(after - total, 3)


def shape_energy(wav_path: Path, energy: float) -> None:
    """Reshape the overall loudness contour in place via a second loudnorm pass.

    energy=1.0 is neutral (skipped). Values below 1 narrow the target loudness range for a
    flatter, calmer contour; values above 1 widen it and lift the target level for a livelier,
    more dynamic one. Uses ffmpeg's EBU R128 loudnorm filter — the same proven, single-pass
    filter already used for reference preprocessing — rather than a hand-tuned compressor
    curve, since loudnorm is not prone to audible pumping artifacts.
    """
    if abs(energy - 1.0) < 1e-6:
        return
    energy = max(0.5, min(energy, 1.8))
    ffmpeg = _require_ffmpeg()
    lra = round(3.0 + (energy - 0.5) / 1.3 * 9.0, 2)
    integrated = round(-22.0 + (energy - 0.5) / 1.3 * 8.0, 2)
    temporary = wav_path.with_suffix(".energy.wav")
    _run([
        ffmpeg, "-y", "-i", str(wav_path),
        "-af", f"loudnorm=I={integrated}:TP=-1.5:LRA={lra}",
        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
        str(temporary),
    ])
    temporary.replace(wav_path)


def blend_breath(wav_path: Path, amount: float) -> None:
    """Blend a very low-level, band-limited noise bed under the speech, in place.

    Experimental: approximates aspiration/air texture, not a literal breath model. amount=0
    is a no-op. Noise is confined to roughly 750 Hz-5.25 kHz (the fricative/breath range) and
    mixed far below the speech (-34 dB at amount=0, -22 dB at amount=1), so at low amounts it
    should read as air/warmth rather than hiss. Must run after trim_outer_silence and
    rescale_internal_pauses — the added noise floor would otherwise defeat their silence
    detection. The user must judge whether this sounds natural or synthetic by ear.
    """
    if amount <= 0.0:
        return
    amount = max(0.0, min(amount, 1.0))
    ffmpeg = _require_ffmpeg()
    total = duration_seconds(wav_path)
    noise_gain_db = -34.0 + (amount * 12.0)
    temporary = wav_path.with_suffix(".breath.wav")
    filter_complex = (
        f"[1:a]bandpass=f=3000:width_type=h:w=4500,volume={noise_gain_db}dB[breath];"
        "[0:a][breath]amix=inputs=2:duration=first:dropout_transition=0[out]"
    )
    _run([
        ffmpeg, "-y",
        "-i", str(wav_path),
        "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=1:duration={total + 0.5:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
        str(temporary),
    ])
    temporary.replace(wav_path)


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
