from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.processing import (
    AudioProcessingError,
    analyze_audio,
    blend_breath,
    duration_seconds,
    preprocess_reference,
    rescale_internal_pauses,
    shape_energy,
    trim_outer_silence,
)


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


def test_trim_outer_silence_removes_trailing_silence_only(tmp_path: Path) -> None:
    source = tmp_path / "speech with trailing silence.wav"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=1.2",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000:duration=1.0",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=1.2",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000:duration=5.0",
            "-filter_complex", "[0:a][1:a][2:a][3:a]concat=n=4:v=0:a=1[out]",
            "-map", "[out]", str(source),
        ],
        check=True,
        capture_output=True,
    )

    removed = trim_outer_silence(source)
    remaining = duration_seconds(source)

    # Only the ~5s trailing silence should be gone; the ~1s internal pause between
    # the two speech segments must survive untouched.
    assert removed >= 4.0
    assert remaining >= 3.0


def test_trim_outer_silence_preserves_quiet_onset(tmp_path: Path) -> None:
    """A -50 dB pre-burst (e.g. a plosive's closure/onset) must survive trimming.

    Regression for a real defect: an earlier -45 dB threshold with no padding trimmed
    into actual speech, clipping the "B" of "Brandon" and the trailing "g" of "something".
    -60 dB plus a keep-padding cushion must leave quiet-but-real audio like this intact.
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    silence = tmp_path / "silence.wav"
    quiet = tmp_path / "quiet.wav"
    loud = tmp_path / "loud.wav"
    source = tmp_path / "speech with quiet onset.wav"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i",
         "anullsrc=channel_layout=mono:sample_rate=24000:duration=1.0", str(silence)],
        check=True, capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000:duration=0.3",
            # lavfi's default sine already peaks near -18 dBFS, so -32dB of attenuation
            # lands this "onset" at roughly -50 dBFS peak: quiet but clearly above the
            # -60 dB silence threshold, like a real plosive/nasal onset or decay.
            "-af", "volume=-32dB", str(quiet),
        ],
        check=True, capture_output=True,
    )
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=1.2", str(loud)],
        check=True, capture_output=True,
    )
    # Concatenating pre-rendered files (rather than mixing an in-graph volume filter
    # directly into a concat filtergraph) avoids an unrelated ffmpeg channel-layout
    # negotiation quirk that otherwise crushes the quiet segment to near-silence.
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(silence), "-i", str(quiet), "-i", str(loud),
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
            "-map", "[out]", str(source),
        ],
        check=True, capture_output=True,
    )

    trim_outer_silence(source)
    remaining = duration_seconds(source)

    # The quiet 0.3s onset plus the 1.2s loud segment must both survive almost exactly;
    # only the leading 1.0s of true digital silence should be gone.
    assert remaining >= 1.45


def test_trim_outer_silence_costs_nothing_on_fully_non_silent_audio(tmp_path: Path) -> None:
    """Regression for the actual root cause: FFmpeg's silenceremove needs start_duration
    worth of continuous non-silence before it trusts audio has resumed, and unconditionally
    discards (start_duration - start_silence) even when there was no silence to begin with.
    A mismatched start_silence forced that "warm-up cost" on every generation regardless of
    threshold. start_silence must equal start_duration so clean audio loses ~nothing.
    """
    source = tmp_path / "no silence anywhere.wav"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=2.0",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    trim_outer_silence(source)
    remaining = duration_seconds(source)

    assert remaining >= 1.95


def _tone_silence_tone(tmp_path: Path, name: str, *, gap: float = 1.0) -> Path:
    source = tmp_path / name
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=1.0",
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=mono:sample_rate=24000:duration={gap}",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=1.0",
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
            "-map", "[out]", str(source),
        ],
        check=True,
        capture_output=True,
    )
    return source


def test_rescale_internal_pauses_noop_at_scale_one(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "noop.wav")
    before = duration_seconds(source)

    removed = rescale_internal_pauses(source, pause_scale=1.0)

    assert removed == 0.0
    assert duration_seconds(source) == before


def test_rescale_internal_pauses_stretches_gap_only(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "stretch.wav")

    rescale_internal_pauses(source, pause_scale=2.0)
    after = duration_seconds(source)

    # Speech segments (2.0s total) must survive untouched; only the 1.0s gap should roughly
    # double to ~2.0s, giving ~4.0s total instead of the original 3.0s.
    assert 3.7 <= after <= 4.3


def test_rescale_internal_pauses_compresses_gap_only(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "compress.wav")

    rescale_internal_pauses(source, pause_scale=0.3)
    after = duration_seconds(source)

    # The 1.0s gap should shrink toward ~0.3s, giving ~2.3s total instead of 3.0s, while the
    # 2.0s of speech content survives.
    assert 2.0 <= after <= 2.6


def test_shape_energy_noop_at_one(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "energy_noop.wav")
    before = duration_seconds(source)

    shape_energy(source, 1.0)

    assert duration_seconds(source) == before


def test_shape_energy_runs_without_corrupting_audio(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "energy.wav")
    before = duration_seconds(source)

    shape_energy(source, 1.6)
    details = analyze_audio(source)

    # loudnorm's single-pass lookahead can nudge length slightly; content must survive intact.
    assert abs(duration_seconds(source) - before) < 0.5
    assert details["sample_rate"] == 24000
    assert details["channels"] == 1


def test_blend_breath_noop_at_zero(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "breath_noop.wav")
    before = duration_seconds(source)

    blend_breath(source, 0.0)

    assert duration_seconds(source) == before


def test_blend_breath_raises_noise_floor_during_the_gap(tmp_path: Path) -> None:
    source = _tone_silence_tone(tmp_path, "breath.wav", gap=1.0)
    silence_only = tmp_path / "gap_only.wav"
    subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", str(source), "-af", "atrim=1.0:2.0", str(silence_only)],
        check=True, capture_output=True,
    )
    before_level = analyze_audio(silence_only)["mean_dbfs"] or -91.0

    blend_breath(source, 1.0)
    after = duration_seconds(source)
    gap_after = tmp_path / "gap_after.wav"
    subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", str(source), "-af", "atrim=1.0:2.0", str(gap_after)],
        check=True, capture_output=True,
    )
    after_level = analyze_audio(gap_after)["mean_dbfs"] or -91.0

    # Duration must be unchanged (amix duration=first); the previously-silent gap must now
    # measurably carry the breath noise bed.
    assert abs(after - 3.0) < 0.2
    assert after_level > before_level + 10
