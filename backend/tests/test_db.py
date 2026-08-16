from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app import db


def configure_db(monkeypatch, tmp_path: Path) -> None:
    settings = SimpleNamespace(db_path=tmp_path / "studio.db")
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    db.init_db()


def test_foreign_keys_are_enabled_on_every_connection(monkeypatch, tmp_path: Path) -> None:
    configure_db(monkeypatch, tmp_path)
    with db.connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_voice_delete_cascades_generation_rows(monkeypatch, tmp_path: Path) -> None:
    configure_db(monkeypatch, tmp_path)
    voice = db.create_voice(
        voice_id="voice", name="Voice", reference_audio_path=tmp_path / "ref.wav",
        original_sample_paths=[tmp_path / "source.wav"], reference_text="hello",
        duration_seconds=4.0,
    )
    db.create_generation(
        generation_id="generation", voice_id=voice["id"], text="new words", language="English",
        speed=1.0, style_instruction=None, model_id="model", device="cpu",
        duration_seconds=1.0, generation_seconds=2.0, wav_path=tmp_path / "out.wav", mp3_path=None,
    )

    deleted = db.delete_voice("voice")

    assert deleted is not None
    assert [item["id"] for item in deleted[1]] == ["generation"]
    assert db.get_voice("voice") is None
    assert db.get_generation("generation") is None


def test_generation_benchmark_label_can_be_saved_and_updated(monkeypatch, tmp_path: Path) -> None:
    configure_db(monkeypatch, tmp_path)
    db.create_voice(
        voice_id="voice", name="Voice", reference_audio_path=tmp_path / "ref.wav",
        original_sample_paths=[tmp_path / "source.wav"], reference_text="hello",
        duration_seconds=4.0,
    )
    created = db.create_generation(
        generation_id="generation", voice_id="voice", text="new words", language="English",
        speed=1.0, style_instruction=None, model_id="model", device="cpu",
        duration_seconds=1.0, generation_seconds=2.0, wav_path=tmp_path / "out.wav", mp3_path=None,
        benchmark_label="Golden baseline · Neutral text · no performance preset",
    )
    assert created["benchmark_label"].startswith("Golden baseline")
    updated = db.update_generation_label("generation", "Golden baseline · Warm text · no performance preset")
    assert updated is not None
    assert updated["benchmark_label"] == "Golden baseline · Warm text · no performance preset"


def test_performance_reference_is_persisted_and_cascades_with_voice(monkeypatch, tmp_path: Path) -> None:
    configure_db(monkeypatch, tmp_path)
    db.create_voice(
        voice_id="voice", name="Voice", reference_audio_path=tmp_path / "ref.wav",
        original_sample_paths=[tmp_path / "source.wav"], reference_text="hello",
        duration_seconds=4.0,
    )
    created = db.create_performance_reference(
        reference_id="warm-reference", voice_id="voice", preset="warm",
        reference_audio_path=tmp_path / "warm.wav",
        original_sample_path=tmp_path / "warm.mp3",
        reference_text="Come sit with me for a moment.", duration_seconds=6.0,
    )
    assert created["preset"] == "warm"
    assert db.get_performance_reference("voice", "warm") == created

    db.delete_voice("voice")

    assert db.list_performance_references("voice") == []
