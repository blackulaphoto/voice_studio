"""Capture the known-good voice configuration and real local synthesis samples.

The output directory is intentionally gitignored because it contains private reference
metadata, transcript text, and generated voice audio. Re-running the script resumes any
completed cases recorded in baseline.json.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import requests
import torch

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "quality_samples" / "golden_baseline"
API = "http://127.0.0.1:8000/api"
VOICE_ID = "hillsry"

CASES = {
    "neutral_30_words": "I reviewed everything this morning, and the plan still makes sense. We can take it one careful step at a time without rushing the parts that deserve attention.",
    "warm": "You did more than enough today. Come sit with me for a minute, take a breath, and let the rest of the evening be gentle.",
    "playful": "Oh, absolutely. Because apparently one quiet cup of coffee was too ordinary, and now we're redesigning the entire future before breakfast again.",
    "serious": "Listen carefully. We need to finish what we started, verify every important detail, and make the decision based on evidence rather than excitement.",
    "sexy": "Come a little closer. I want to tell you something quietly, without the noise, the interruptions, or anyone else listening in.",
    "short_conversational_10_words": "Wait, really? You actually got the cloned voice working perfectly.",
    "long_paragraph_100_words": "By the time the rain finally stopped, the streetlights had already come on and every window reflected across the wet pavement. We walked home slowly, talking about small things because neither of us was ready to end the evening. At the corner, you paused and asked whether the new voice system could really preserve all the details people notice without realizing it: timing, rhythm, warmth, and those tiny changes that make a sentence feel personal. I said we would test it carefully, keep the version that sounded true, and refuse every shortcut that made the speaker sound like someone else entirely.",
    "numbers_and_dates": "Your appointment is August twenty-third at ten thirty-five in the morning. The balance is one hundred forty-seven dollars and sixty-two cents, and the confirmation number is four eight two seven.",
}

DISPLAY_LABELS = {
    "neutral_30_words": "Neutral text",
    "warm": "Warm text",
    "playful": "Playful text",
    "serious": "Serious text",
    "sexy": "Sexy text",
    "short_conversational_10_words": "Short conversational text",
    "long_paragraph_100_words": "Long-form text",
    "numbers_and_dates": "Numbers and dates text",
}


def benchmark_label(case_id: str) -> str:
    return f"Golden baseline · {DISPLAY_LABELS[case_id]} · no performance preset"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_metadata(metadata: dict[str, Any]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "baseline.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def backend_process() -> psutil.Process | None:
    try:
        for connection in psutil.net_connections(kind="tcp"):
            if (
                connection.status == psutil.CONN_LISTEN
                and connection.laddr
                and connection.laddr.port == 8000
                and connection.pid
            ):
                return psutil.Process(connection.pid)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return None
    return None


def main() -> None:
    voice = requests.get(f"{API}/voices/{VOICE_ID}", timeout=30).json()
    reference = PROJECT / "storage" / "voices" / VOICE_ID / "reference.wav"
    source_dir = PROJECT / "storage" / "samples" / VOICE_ID
    sources = sorted(path for path in source_dir.iterdir() if path.is_file())
    process = backend_process()
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "engine": voice["engine_id"],
        "model": voice["model_id"],
        "model_package_version": importlib.metadata.version("qwen-tts"),
        "voice_id": voice["id"],
        "reference_audio": str(reference.relative_to(PROJECT)),
        "reference_sha256": sha256(reference),
        "source_files": [{"path": str(path.relative_to(PROJECT)), "sha256": sha256(path)} for path in sources],
        "reference_transcript": voice["reference_text"],
        "reference_duration_seconds": voice["duration_seconds"],
        "generation": {
            "mode": "quality",
            "language": "English",
            "speed": 1.0,
            "performance": None,
            "engine_settings": {},
            "seed": None,
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": "cpu",
            "dtype": "float32",
            "cuda_available": torch.cuda.is_available(),
            "system_ram_gb": round(psutil.virtual_memory().total / 1073741824, 2),
        },
        "audio_pipeline": {
            "reference_output": "24000 Hz mono PCM s16le WAV",
            "silence": "leading/trailing only; -60 dB detector; internal pauses preserved",
            "loudness": "FFmpeg loudnorm I=-18:TP=-2:LRA=7",
            "post_speed": "none at speed=1.0; FFmpeg atempo otherwise",
            "canonical_output": "WAV",
            "secondary_output": "MP3 libmp3lame quality 2",
        },
        "backend_pid": process.pid if process else None,
        "backend_rss_mb_before": round(process.memory_info().rss / 1048576, 2) if process else None,
        "cases": {},
    }
    existing_path = OUTPUT / "baseline.json"
    if existing_path.exists():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        metadata["cases"] = existing.get("cases", {})

    write_metadata(metadata)
    for label, text in CASES.items():
        if metadata["cases"].get(label, {}).get("status") == "passed":
            generation_id = metadata["cases"][label].get("id")
            if generation_id:
                response = requests.patch(
                    f"{API}/generations/{generation_id}",
                    json={"benchmark_label": benchmark_label(label)},
                    timeout=30,
                )
                response.raise_for_status()
                metadata["cases"][label]["benchmark_label"] = benchmark_label(label)
                write_metadata(metadata)
            print(f"SKIP {label}: already captured", flush=True)
            continue
        print(f"GENERATE {label} ({len(text.split())} words)", flush=True)
        started = time.perf_counter()
        response = requests.post(
            f"{API}/tts",
            json={
                "voice_id": VOICE_ID,
                "text": text,
                "language": "English",
                "speed": 1.0,
                "mode": "quality",
                "engine_id": "qwen3",
                "benchmark_label": benchmark_label(label),
            },
            timeout=1800,
        )
        response.raise_for_status()
        result = response.json()
        generation_dir = PROJECT / "storage" / "generations" / result["id"]
        wav_target = OUTPUT / f"{label}.wav"
        mp3_target = OUTPUT / f"{label}.mp3"
        shutil.copy2(generation_dir / "speech.wav", wav_target)
        if (generation_dir / "speech.mp3").exists():
            shutil.copy2(generation_dir / "speech.mp3", mp3_target)
        result.update({
            "status": "passed",
            "label": label,
            "word_count": len(text.split()),
            "client_elapsed_seconds": round(time.perf_counter() - started, 3),
            "real_time_factor": round(result["generation_seconds"] / result["duration_seconds"], 4),
            "wav": str(wav_target.relative_to(PROJECT)),
            "mp3": str(mp3_target.relative_to(PROJECT)) if mp3_target.exists() else None,
            "backend_rss_mb_after": round(process.memory_info().rss / 1048576, 2) if process else None,
        })
        metadata["cases"][label] = result
        write_metadata(metadata)
        print(
            f"DONE {label}: generation={result['generation_seconds']}s "
            f"audio={result['duration_seconds']}s rtf={result['real_time_factor']}",
            flush=True,
        )
    metadata["completed_at"] = datetime.now(UTC).isoformat()
    write_metadata(metadata)


if __name__ == "__main__":
    main()
