from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db_path = get_settings().db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS voices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                reference_audio_path TEXT NOT NULL,
                original_sample_paths TEXT NOT NULL,
                reference_text TEXT,
                duration_seconds REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY,
                voice_id TEXT NOT NULL,
                text TEXT NOT NULL,
                language TEXT NOT NULL,
                speed REAL NOT NULL DEFAULT 1.0,
                style_instruction TEXT,
                model_id TEXT NOT NULL,
                device TEXT NOT NULL,
                duration_seconds REAL,
                generation_seconds REAL NOT NULL,
                wav_path TEXT NOT NULL,
                mp3_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (voice_id) REFERENCES voices(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS performance_references (
                id TEXT PRIMARY KEY,
                voice_id TEXT NOT NULL,
                preset TEXT NOT NULL,
                reference_audio_path TEXT NOT NULL,
                original_sample_path TEXT NOT NULL,
                reference_text TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (voice_id, preset),
                FOREIGN KEY (voice_id) REFERENCES voices(id) ON DELETE CASCADE
            );
            """
        )
        _ensure_columns(conn, "voices", {
            "engine_id": "TEXT NOT NULL DEFAULT 'qwen3'",
            "model_id": "TEXT",
            "language": "TEXT NOT NULL DEFAULT 'English'",
            "settings_json": "TEXT NOT NULL DEFAULT '{}'",
        })
        _ensure_columns(conn, "generations", {
            "benchmark_label": "TEXT",
            "normalized_text": "TEXT",
            "engine_id": "TEXT NOT NULL DEFAULT 'qwen3'",
            "mode": "TEXT NOT NULL DEFAULT 'quality'",
            "performance": "TEXT",
            "seed": "INTEGER",
            "settings_json": "TEXT NOT NULL DEFAULT '{}'",
            "reference_set_json": "TEXT NOT NULL DEFAULT '[]'",
        })


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _row_to_voice(row: sqlite3.Row) -> dict[str, Any]:
    import json

    return {
        "id": row["id"],
        "name": row["name"],
        "reference_audio_path": row["reference_audio_path"],
        "original_sample_paths": json.loads(row["original_sample_paths"]),
        "reference_text": row["reference_text"],
        "duration_seconds": row["duration_seconds"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "engine_id": row["engine_id"],
        "model_id": row["model_id"],
        "language": row["language"],
        "settings": json.loads(row["settings_json"] or "{}"),
    }


def list_voices() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM voices ORDER BY created_at DESC").fetchall()
    return [_row_to_voice(row) for row in rows]


def get_voice(voice_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM voices WHERE id = ?", (voice_id,)).fetchone()
    return _row_to_voice(row) if row else None


def create_voice(
    *,
    voice_id: str,
    name: str,
    reference_audio_path: Path,
    original_sample_paths: list[Path],
    reference_text: str | None,
    duration_seconds: float,
    engine_id: str = "qwen3",
    model_id: str | None = None,
    language: str = "English",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import json

    now = utc_now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO voices (
                id, name, reference_audio_path, original_sample_paths, reference_text,
                duration_seconds, created_at, updated_at, engine_id, model_id, language, settings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                voice_id,
                name,
                str(reference_audio_path),
                json.dumps([str(path) for path in original_sample_paths]),
                reference_text or None,
                duration_seconds,
                now,
                now,
                engine_id,
                model_id,
                language,
                json.dumps(settings or {}),
            ),
        )
    voice = get_voice(voice_id)
    if voice is None:
        raise RuntimeError("Voice profile was not persisted.")
    return voice


def delete_voice(voice_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    voice = get_voice(voice_id)
    if voice is None:
        return None
    with connection() as conn:
        generation_rows = conn.execute(
            "SELECT * FROM generations WHERE voice_id = ?", (voice_id,)
        ).fetchall()
        conn.execute("DELETE FROM voices WHERE id = ?", (voice_id,))
    return voice, [dict(row) for row in generation_rows]


def create_generation(
    *,
    generation_id: str,
    voice_id: str,
    text: str,
    language: str,
    speed: float,
    style_instruction: str | None,
    model_id: str,
    device: str,
    duration_seconds: float | None,
    generation_seconds: float,
    wav_path: Path,
    mp3_path: Path | None,
    normalized_text: str | None = None,
    engine_id: str = "qwen3",
    mode: str = "quality",
    performance: str | None = None,
    seed: int | None = None,
    settings: dict[str, Any] | None = None,
    reference_set: list[str] | None = None,
    benchmark_label: str | None = None,
) -> dict[str, Any]:
    import json
    now = utc_now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO generations (
                id, voice_id, text, language, speed, style_instruction, model_id, device,
                duration_seconds, generation_seconds, wav_path, mp3_path, created_at,
                normalized_text, engine_id, mode, performance, seed, settings_json, reference_set_json,
                benchmark_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generation_id,
                voice_id,
                text,
                language,
                speed,
                style_instruction or None,
                model_id,
                device,
                duration_seconds,
                generation_seconds,
                str(wav_path),
                str(mp3_path) if mp3_path else None,
                now,
                normalized_text,
                engine_id,
                mode,
                performance,
                seed,
                json.dumps(settings or {}),
                json.dumps(reference_set or []),
                benchmark_label,
            ),
        )
    return get_generation(generation_id)  # type: ignore[return-value]


def get_generation(generation_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM generations WHERE id = ?", (generation_id,)).fetchone()
    return _row_to_generation(row) if row else None


def list_generations(limit: int = 100) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM generations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_generation(row) for row in rows]


def _row_to_generation(row: sqlite3.Row) -> dict[str, Any]:
    import json
    result = dict(row)
    result["settings"] = json.loads(result.pop("settings_json", "{}") or "{}")
    result["reference_set"] = json.loads(result.pop("reference_set_json", "[]") or "[]")
    return result


def update_voice(voice_id: str, *, name: str | None = None, language: str | None = None,
                 settings: dict[str, Any] | None = None) -> dict[str, Any] | None:
    import json
    voice = get_voice(voice_id)
    if voice is None:
        return None
    with connection() as conn:
        conn.execute(
            "UPDATE voices SET name = ?, language = ?, settings_json = ?, updated_at = ? WHERE id = ?",
            (name or voice["name"], language or voice["language"], json.dumps(settings if settings is not None else voice["settings"]), utc_now(), voice_id),
        )
    return get_voice(voice_id)


def delete_generation(generation_id: str) -> dict[str, Any] | None:
    generation = get_generation(generation_id)
    if generation is None:
        return None
    with connection() as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (generation_id,))
    return generation


def list_performance_references(voice_id: str | None = None) -> list[dict[str, Any]]:
    with connection() as conn:
        if voice_id is None:
            rows = conn.execute(
                "SELECT * FROM performance_references ORDER BY voice_id, preset"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM performance_references WHERE voice_id = ? ORDER BY preset",
                (voice_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def get_performance_reference(voice_id: str, preset: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM performance_references WHERE voice_id = ? AND preset = ?",
            (voice_id, preset),
        ).fetchone()
    return dict(row) if row else None


def create_performance_reference(
    *, reference_id: str, voice_id: str, preset: str, reference_audio_path: Path,
    original_sample_path: Path, reference_text: str, duration_seconds: float,
) -> dict[str, Any]:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO performance_references (
                id, voice_id, preset, reference_audio_path, original_sample_path,
                reference_text, duration_seconds, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (reference_id, voice_id, preset, str(reference_audio_path), str(original_sample_path),
             reference_text, duration_seconds, utc_now()),
        )
    reference = get_performance_reference(voice_id, preset)
    if reference is None:
        raise RuntimeError("Performance reference was not persisted.")
    return reference


def delete_performance_reference(voice_id: str, preset: str) -> dict[str, Any] | None:
    reference = get_performance_reference(voice_id, preset)
    if reference is None:
        return None
    with connection() as conn:
        conn.execute(
            "DELETE FROM performance_references WHERE voice_id = ? AND preset = ?",
            (voice_id, preset),
        )
    return reference


def update_generation_label(generation_id: str, benchmark_label: str | None) -> dict[str, Any] | None:
    if get_generation(generation_id) is None:
        return None
    with connection() as conn:
        conn.execute(
            "UPDATE generations SET benchmark_label = ? WHERE id = ?",
            (benchmark_label or None, generation_id),
        )
    return get_generation(generation_id)
