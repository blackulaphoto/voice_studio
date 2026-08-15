from __future__ import annotations

import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .audio.processing import AudioProcessingError, duration_seconds, export_mp3, preprocess_reference, time_stretch
from .config import get_settings
from .db import (
    create_generation,
    create_voice,
    delete_voice,
    get_generation,
    get_voice,
    init_db,
    list_generations,
    list_voices,
)
from .schemas import (
    DeviceInfo,
    GenerationListResponse,
    GenerationRequest,
    GenerationResponse,
    HealthResponse,
    VoiceCreatedResponse,
    VoiceListResponse,
    VoiceProfile,
)
from .tts.qwen_engine import EngineUnavailableError, QwenVoiceCloneEngine

settings = get_settings()
engine = QwenVoiceCloneEngine(settings.qwen_model_id, settings.force_device)
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}


@app.on_event("startup")
def startup() -> None:
    init_db()


def _device_info() -> DeviceInfo:
    hardware = engine.hardware()
    return DeviceInfo(
        active_device=hardware.active_device,
        accelerator_available=hardware.accelerator_available,
        gpu_name=hardware.gpu_name,
        vram_total_mb=hardware.vram_total_mb,
        model_id=settings.qwen_model_id,
        model_loaded=engine.is_loaded,
    )


def _voice_response(voice: dict) -> VoiceProfile:
    return VoiceProfile(
        id=voice["id"],
        name=voice["name"],
        duration_seconds=voice["duration_seconds"],
        reference_text=voice["reference_text"],
        created_at=datetime.fromisoformat(voice["created_at"]),
        updated_at=datetime.fromisoformat(voice["updated_at"]),
        preview_url=f"{settings.api_prefix}/voices/{voice['id']}/preview",
        original_sample_count=len(voice["original_sample_paths"]),
    )


def _generation_response(generation: dict) -> GenerationResponse:
    return GenerationResponse(
        id=generation["id"],
        voice_id=generation["voice_id"],
        text=generation["text"],
        language=generation["language"],
        speed=float(generation.get("speed", 1.0)),
        model_id=generation["model_id"],
        device=generation["device"],
        duration_seconds=generation["duration_seconds"],
        generation_seconds=float(generation["generation_seconds"]),
        created_at=datetime.fromisoformat(generation["created_at"]),
        audio_url=f"{settings.api_prefix}/generations/{generation['id']}/audio",
        wav_download_url=f"{settings.api_prefix}/generations/{generation['id']}/download/wav",
        mp3_download_url=(
            f"{settings.api_prefix}/generations/{generation['id']}/download/mp3"
            if generation["mp3_path"]
            else None
        ),
    )


def _safe_voice_id(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return normalized[:64] or "voice"


def _path_for_record(path_text: str | None) -> Path:
    if not path_text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file is unavailable.")
    path = Path(path_text).resolve()
    storage_root = settings.storage_root.resolve()
    if storage_root not in path.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file is unavailable.")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file is unavailable.")
    return path


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", device=_device_info())


@app.get(f"{settings.api_prefix}/voices", response_model=VoiceListResponse)
def get_voices() -> VoiceListResponse:
    return VoiceListResponse(voices=[_voice_response(voice) for voice in list_voices()], device=_device_info())


@app.post(f"{settings.api_prefix}/voices", response_model=VoiceCreatedResponse, status_code=status.HTTP_201_CREATED)
def post_voice(
    name: str = Form(..., min_length=1, max_length=80),
    reference_text: str | None = Form(default=None, max_length=2000),
    authorization_acknowledged: bool = Form(...),
    files: list[UploadFile] = File(...),
) -> VoiceCreatedResponse:
    """Store source recordings and create a clean local reference prompt.

    `authorization_acknowledged` is deliberately required: users may only create profiles from
    voices they own or have explicit permission to reproduce.
    """
    if not authorization_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must confirm that you own this voice or have explicit permission to clone it.",
        )
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload at least one audio sample.")

    voice_id = _safe_voice_id(name)
    if get_voice(voice_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A voice profile with this name already exists. Choose a different name.",
        )
    voice_dir = settings.voices_dir / voice_id
    sample_dir = settings.samples_dir / voice_id
    voice_dir.mkdir(parents=True, exist_ok=False)
    sample_dir.mkdir(parents=True, exist_ok=False)
    originals: list[Path] = []

    try:
        for index, upload in enumerate(files, start=1):
            extension = Path(upload.filename or "").suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported sample format '{extension or 'unknown'}'. Use WAV, MP3, M4A, FLAC, OGG, AAC, or WebM.",
                )
            destination = sample_dir / f"sample-{index}{extension}"
            with destination.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            if destination.stat().st_size > settings.max_upload_mb * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Each sample must be at most {settings.max_upload_mb} MB.",
                )
            originals.append(destination)

        reference_path = voice_dir / "reference.wav"
        total_duration = preprocess_reference(originals, reference_path)
        if total_duration < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The processed reference is under 2 seconds. Upload a longer, clean speaking sample.",
            )
        voice = create_voice(
            voice_id=voice_id,
            name=name.strip(),
            reference_audio_path=reference_path,
            original_sample_paths=originals,
            reference_text=(reference_text or "").strip() or None,
            duration_seconds=total_duration,
        )
        return VoiceCreatedResponse(
            voice=_voice_response(voice),
            message="Voice profile saved. The local model will build and reuse its clone prompt on the first synthesis.",
        )
    except HTTPException:
        shutil.rmtree(voice_dir, ignore_errors=True)
        shutil.rmtree(sample_dir, ignore_errors=True)
        raise
    except AudioProcessingError as exc:
        shutil.rmtree(voice_dir, ignore_errors=True)
        shutil.rmtree(sample_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(voice_dir, ignore_errors=True)
        shutil.rmtree(sample_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    finally:
        for upload in files:
            upload.file.close()


@app.get(f"{settings.api_prefix}/voices/{{voice_id}}/preview")
def preview_voice(voice_id: str) -> FileResponse:
    voice = get_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    path = _path_for_record(voice["reference_audio_path"])
    return FileResponse(path, media_type="audio/wav", filename=f"{voice_id}-reference.wav")


@app.delete(f"{settings.api_prefix}/voices/{{voice_id}}", status_code=status.HTTP_204_NO_CONTENT)
def remove_voice(voice_id: str) -> None:
    voice = delete_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    engine.clear_prompt(voice_id)
    shutil.rmtree(settings.voices_dir / voice_id, ignore_errors=True)
    shutil.rmtree(settings.samples_dir / voice_id, ignore_errors=True)


@app.post(f"{settings.api_prefix}/tts", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
def synthesize(payload: GenerationRequest) -> GenerationResponse:
    voice = get_voice(payload.voice_id)
    if voice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")

    generation_id = uuid.uuid4().hex
    generation_dir = settings.generations_dir / generation_id
    wav_path = generation_dir / "speech.wav"
    mp3_path = generation_dir / "speech.mp3"
    started = time.perf_counter()
    try:
        engine.synthesize(
            voice_id=voice["id"],
            reference_audio=Path(voice["reference_audio_path"]),
            reference_text=voice["reference_text"],
            text=payload.text.strip(),
            language=payload.language,
            output_path=wav_path,
        )
        time_stretch(wav_path, payload.speed)
        exported_mp3 = export_mp3(wav_path, mp3_path)
        elapsed = round(time.perf_counter() - started, 3)
        generation = create_generation(
            generation_id=generation_id,
            voice_id=voice["id"],
            text=payload.text.strip(),
            language=payload.language,
            speed=payload.speed,
            style_instruction=None,
            model_id=settings.qwen_model_id,
            device=engine.hardware().active_device,
            duration_seconds=duration_seconds(wav_path),
            generation_seconds=elapsed,
            wav_path=wav_path,
            mp3_path=mp3_path if exported_mp3 else None,
        )
        return _generation_response(generation)
    except (EngineUnavailableError, AudioProcessingError) as exc:
        shutil.rmtree(generation_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(generation_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/generations", response_model=GenerationListResponse)
def get_generations() -> GenerationListResponse:
    return GenerationListResponse(generations=[_generation_response(item) for item in list_generations()])


@app.get(f"{settings.api_prefix}/generations/{{generation_id}}/audio")
def generation_audio(generation_id: str) -> FileResponse:
    generation = get_generation(generation_id)
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    return FileResponse(_path_for_record(generation["wav_path"]), media_type="audio/wav")


@app.get(f"{settings.api_prefix}/generations/{{generation_id}}/download/{{format_name}}")
def download_generation(generation_id: str, format_name: str) -> FileResponse:
    if format_name not in {"wav", "mp3"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested format is unavailable.")
    generation = get_generation(generation_id)
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    path = _path_for_record(generation["wav_path"] if format_name == "wav" else generation["mp3_path"])
    media_type = "audio/wav" if format_name == "wav" else "audio/mpeg"
    return FileResponse(path, media_type=media_type, filename=f"athena-{generation_id}.{format_name}")
