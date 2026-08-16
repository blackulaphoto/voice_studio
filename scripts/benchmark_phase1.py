"""Run resumable, matched QUALITY/FAST benchmarks against the local Golden Voice."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil
import requests

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "quality_samples" / "phase_1"
RESULTS = OUTPUT / "benchmark.json"
API = "http://127.0.0.1:8000/api"
VOICE_ID = "hillsry"

CASES = {
    "30_words": "Your appointment is August twenty-third at ten thirty-five in the morning. The balance is one hundred forty-seven dollars and sixty-two cents, and the confirmation number is four eight two seven.",
    "100_words": "By the time the rain finally stopped, the streetlights had already come on and every window reflected across the wet pavement. We walked home slowly, talking about small things because neither of us was ready to end the evening. At the corner, you paused and asked whether the new voice system could really preserve all the details people notice without realizing it: timing, rhythm, warmth, and those tiny changes that make a sentence feel personal. I said we would test it carefully, keep the version that sounded true, and refuse every shortcut that made the speaker sound like someone else entirely.",
}


def backend_process() -> psutil.Process | None:
    for connection in psutil.net_connections(kind="tcp"):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 8000 and connection.pid:
            return psutil.Process(connection.pid)
    return None


def save(data: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    health = requests.get(f"{API}/health", timeout=30)
    health.raise_for_status()
    data = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {
        "started_at": datetime.now(UTC).isoformat(), "voice_id": VOICE_ID, "results": {}
    }
    process = backend_process()
    for case_id, text in CASES.items():
        for mode in ("quality", "fast"):
            key = f"{case_id}_{mode}"
            if data["results"].get(key, {}).get("status") == "passed":
                print(f"SKIP {key}", flush=True)
                continue
            print(f"START {key} ({len(text.split())} words)", flush=True)
            started = time.perf_counter()
            response = requests.post(
                f"{API}/tts",
                json={
                    "voice_id": VOICE_ID,
                    "text": text,
                    "language": "English",
                    "speed": 1.0,
                    "mode": mode,
                    "engine_id": "qwen3",
                    "benchmark_label": f"Phase 1 · {case_id.replace('_', ' ')} · {mode.upper()}",
                },
                timeout=1800,
            )
            response.raise_for_status()
            result = response.json()
            data["results"][key] = {
                "status": "passed",
                "generation_id": result["id"],
                "mode": mode,
                "word_count": len(text.split()),
                "generation_seconds": result["generation_seconds"],
                "audio_seconds": result["duration_seconds"],
                "rtf": round(result["generation_seconds"] / result["duration_seconds"], 4),
                "phase_timings": result["settings"].get("phase_timings", {}),
                "backend_rss_mb": round(process.memory_info().rss / 1048576, 2) if process else None,
                "client_seconds": round(time.perf_counter() - started, 3),
            }
            save(data)
            print(json.dumps({key: data["results"][key]}, indent=2), flush=True)
    data["completed_at"] = datetime.now(UTC).isoformat()
    save(data)


if __name__ == "__main__":
    main()
