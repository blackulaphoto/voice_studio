"""Generate the resumable same-text Phase 2 performance listening suite."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import requests

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "quality_samples" / "phase_2"
RESULTS = OUTPUT / "benchmark.json"
API = "http://127.0.0.1:8000/api"
VOICE_ID = "hillsry"
TEXT = "Brandon, come here for a second. I need to tell you something."
PRESETS = ("neutral", "warm", "playful", "serious", "soft", "excited", "concerned", "firm", "intimate", "tired")


def save(data: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    existing_generations = requests.get(f"{API}/generations", timeout=30).json()["generations"]
    existing_by_preset = {
        item.get("performance"): item
        for item in existing_generations
        if (item.get("benchmark_label") or "").startswith("Phase 2")
    }
    data = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {
        "started_at": datetime.now(UTC).isoformat(), "voice_id": VOICE_ID,
        "text": TEXT, "results": {},
    }
    for preset in PRESETS:
        if data["results"].get(preset, {}).get("status") == "passed":
            print(f"SKIP {preset}: already captured", flush=True)
            continue
        if preset in existing_by_preset:
            result = existing_by_preset[preset]
            print(f"ADOPT {preset}: {result['id']}", flush=True)
        else:
            print(f"GENERATE {preset}", flush=True)
            response = requests.post(
                f"{API}/tts",
                json={
                    "voice_id": VOICE_ID, "text": TEXT, "language": "English",
                    "speed": 1.0, "mode": "quality", "engine_id": "qwen3",
                    "performance": preset,
                    "benchmark_label": f"Phase 2 · {preset.upper()} · built-in no-upload preset",
                },
                timeout=1800,
            )
            response.raise_for_status()
            result = response.json()
        data["results"][preset] = {
            "status": "passed", "generation_id": result["id"],
            "generation_seconds": result["generation_seconds"],
            "audio_seconds": result["duration_seconds"],
            "rtf": round(result["generation_seconds"] / result["duration_seconds"], 4),
            "parameters": result["settings"].get("performance_parameters", {}),
            "effective_speed": result["settings"].get("effective_speed", result["speed"]),
        }
        save(data)
        print(json.dumps({preset: data["results"][preset]}, indent=2), flush=True)
    data["completed_at"] = datetime.now(UTC).isoformat()
    save(data)


if __name__ == "__main__":
    main()
