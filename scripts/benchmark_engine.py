"""Run reproducible real-inference measurements against an authorized reference.

This script never substitutes mock audio. It writes clips under quality_samples and a JSON
record under docs/benchmarks. A failed or unavailable model is recorded as a failure.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

from app.audio.processing import duration_seconds  # noqa: E402
from app.tts.qwen_engine import QwenVoiceCloneEngine  # noqa: E402

PHRASES = {
    "10-word": "Please bring the blue notebook when you come home tonight.",
    "30-word": "I thought carefully about your suggestion, and after reviewing the notes this morning, I agree that the quieter approach will probably sound more natural and remain easier to understand.",
    "100-word": "When the meeting ended, everyone stayed in the room for a moment, comparing notes and checking the schedule for the following week. The rain had started while we were talking, tapping softly against the windows and making the hallway seem unusually quiet. I packed my notebook, called the front desk, and asked whether the last train was still running. It was, but only just. We walked quickly through the lobby, laughing at how a simple afternoon discussion had turned into an unexpected race across town before the station closed for the night.",
}
PHRASES["500-word"] = " ".join([PHRASES["100-word"]] * 5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["qwen3"], required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text", required=True)
    parser.add_argument("--language", default="English")
    parser.add_argument("--device")
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()

    sample_root = PROJECT / "quality_samples" / args.engine / args.model.replace("/", "--") / args.run_id
    report_root = PROJECT / "docs" / "benchmarks"
    sample_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    engine = QwenVoiceCloneEngine(args.model, args.device)
    process = psutil.Process()
    report = {
        "run_id": args.run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "engine": args.engine,
        "model": args.model,
        "package_version": importlib.metadata.version("qwen-tts"),
        "device": engine.hardware().active_device,
        "reference": str(args.reference.resolve()),
        "method": "REAL MODEL INFERENCE",
        "cases": [],
    }
    load_started = time.perf_counter()
    try:
        engine.load()
        report["model_load_seconds"] = round(time.perf_counter() - load_started, 3)
        for label, text in PHRASES.items():
            output = sample_root / f"{label}.wav"
            before_ram = process.memory_info().rss
            started = time.perf_counter()
            try:
                engine.synthesize(
                    voice_id=f"benchmark-{args.run_id}", reference_audio=args.reference,
                    reference_text=args.reference_text, text=text, language=args.language,
                    output_path=output,
                )
                generation_seconds = time.perf_counter() - started
                audio_seconds = duration_seconds(output)
                case = {
                    "name": label, "status": "passed", "word_count": len(text.split()),
                    "generation_seconds": round(generation_seconds, 3),
                    "first_audio_seconds": round(generation_seconds, 3),
                    "first_audio_note": "Non-streaming adapter; file became playable only after generation completed.",
                    "audio_seconds": audio_seconds,
                    "real_time_factor": round(generation_seconds / audio_seconds, 4) if audio_seconds else None,
                    "ram_delta_mb": round((process.memory_info().rss - before_ram) / 1048576, 2),
                    "output": str(output.relative_to(PROJECT)),
                }
                try:
                    import torch
                    case["vram_peak_mb"] = round(torch.cuda.max_memory_allocated() / 1048576, 2) if torch.cuda.is_available() else 0
                except ImportError:
                    case["vram_peak_mb"] = None
            except Exception as exc:
                case = {"name": label, "status": "failed", "error": str(exc)}
            report["cases"].append(case)
    except Exception as exc:
        report["load_error"] = str(exc)
    finally:
        engine.unload()

    report_path = report_root / f"{args.run_id}-{args.engine}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path)
    if report.get("load_error") or any(case["status"] == "failed" for case in report["cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
