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
    create_performance_reference,
    create_voice,
    delete_generation,
    delete_voice,
    delete_performance_reference,
    get_generation,
    get_voice,
    get_performance_reference,
    init_db,
    list_generations,
    list_voices,
    list_performance_references,
    update_voice,
    update_generation_label,
)
from .schemas import (
    DeviceInfo,
    GenerationListResponse,
    GenerationRequest,
    GenerationPatchRequest,
    GenerationResponse,
    HealthResponse,
    EngineInfo,
    EngineListResponse,
    VoiceCreatedResponse,
    VoiceListResponse,
    VoiceProfile,
    VoicePatchRequest,
    PerformanceReference,
    PerformanceReferenceList,
)
from .text.normalization import normalize_text
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
PERFORMANCE_PRESETS = {
    "neutral": {},
    "warm": {"temperature": 0.85, "top_p": 0.90, "subtalker_temperature": 0.85, "pace": 0.96},
    "playful": {"temperature": 1.05, "top_k": 60, "subtalker_temperature": 1.05, "pace": 1.03},
    "serious": {"temperature": 0.68, "top_p": 0.82, "repetition_penalty": 1.08, "subtalker_temperature": 0.68, "pace": 0.95},
    "soft": {"temperature": 0.76, "top_p": 0.86, "repetition_penalty": 1.08, "subtalker_temperature": 0.74, "pace": 0.94},
    "excited": {"temperature": 1.10, "top_k": 65, "subtalker_temperature": 1.10, "pace": 1.08},
    "concerned": {"pace": 0.92},
    "firm": {"temperature": 0.68, "top_p": 0.82, "repetition_penalty": 1.08, "subtalker_temperature": 0.68, "pace": 0.96},
    "intimate": {"temperature": 0.78, "top_p": 0.88, "repetition_penalty": 1.08, "subtalker_temperature": 0.76, "pace": 0.84},
    "tired": {"temperature": 0.82, "top_p": 0.90, "repetition_penalty": 1.10, "subtalker_temperature": 0.78, "pace": 0.82},
}


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
        engine_id=voice.get("engine_id", "qwen3"),
        model_id=voice.get("model_id"),
        language=voice.get("language", "English"),
        settings=voice.get("settings", {}),
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
        normalized_text=generation.get("normalized_text"),
        engine_id=generation.get("engine_id", "qwen3"),
        mode=generation.get("mode", "quality"),
        performance=generation.get("performance"),
        seed=generation.get("seed"),
        settings=generation.get("settings", {}),
        reference_set=generation.get("reference_set", []),
        benchmark_label=generation.get("benchmark_label"),
    )


def _performance_response(reference: dict) -> PerformanceReference:
    return PerformanceReference(
        id=reference["id"], voice_id=reference["voice_id"], preset=reference["preset"],
        reference_text=reference["reference_text"], duration_seconds=reference["duration_seconds"],
        created_at=datetime.fromisoformat(reference["created_at"]),
        preview_url=f"{settings.api_prefix}/voices/{reference['voice_id']}/performances/{reference['preset']}/preview",
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


@app.get(f"{settings.api_prefix}/engines", response_model=EngineListResponse)
def get_engines() -> EngineListResponse:
    return EngineListResponse(engines=[EngineInfo(
        id=engine.engine_id,
        name=engine.display_name,
        model_id=engine.model_id,
        loaded=engine.is_loaded,
        capabilities=engine.capabilities().to_dict(),
    )])


@app.get(f"{settings.api_prefix}/models", response_model=EngineListResponse)
def get_models() -> EngineListResponse:
    return get_engines()


@app.get(f"{settings.api_prefix}/voices", response_model=VoiceListResponse)
def get_voices() -> VoiceListResponse:
    return VoiceListResponse(voices=[_voice_response(voice) for voice in list_voices()], device=_device_info())


@app.get(f"{settings.api_prefix}/voices/{{voice_id}}", response_model=VoiceProfile)
def get_voice_profile(voice_id: str) -> VoiceProfile:
    voice = get_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    return _voice_response(voice)


@app.patch(f"{settings.api_prefix}/voices/{{voice_id}}", response_model=VoiceProfile)
def patch_voice_profile(voice_id: str, payload: VoicePatchRequest) -> VoiceProfile:
    voice = update_voice(voice_id, name=payload.name, language=payload.language, settings=payload.settings)
    if voice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    return _voice_response(voice)


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
            model_id=settings.qwen_model_id,
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


@app.get(f"{settings.api_prefix}/voices/{{voice_id}}/performances", response_model=PerformanceReferenceList)
def get_voice_performances(voice_id: str) -> PerformanceReferenceList:
    if get_voice(voice_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    return PerformanceReferenceList(
        performances=[_performance_response(item) for item in list_performance_references(voice_id)]
    )


@app.post(f"{settings.api_prefix}/voices/{{voice_id}}/performances", response_model=PerformanceReference, status_code=status.HTTP_201_CREATED)
def post_voice_performance(
    voice_id: str,
    preset: str = Form(...),
    reference_text: str = Form(..., min_length=1, max_length=2000),
    authorization_acknowledged: bool = Form(...),
    file: UploadFile = File(...),
) -> PerformanceReference:
    if get_voice(voice_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    preset = preset.strip().lower()
    if preset not in PERFORMANCE_PRESETS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown performance preset.")
    if not authorization_acknowledged:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirm permission to reproduce this voice.")
    if get_performance_reference(voice_id, preset):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"The {preset} performance already exists. Delete it before replacing it.")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported audio format.")
    performance_dir = settings.voices_dir / voice_id / "performances" / preset
    performance_dir.mkdir(parents=True, exist_ok=False)
    original = performance_dir / f"source{extension}"
    processed = performance_dir / "reference.wav"
    try:
        with original.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        if original.stat().st_size > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"The sample must be at most {settings.max_upload_mb} MB.")
        measured_duration = preprocess_reference([original], processed)
        if measured_duration < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The processed performance reference is under 2 seconds.")
        reference = create_performance_reference(
            reference_id=uuid.uuid4().hex, voice_id=voice_id, preset=preset,
            reference_audio_path=processed, original_sample_path=original,
            reference_text=reference_text.strip(), duration_seconds=measured_duration,
        )
        engine.clear_prompt(voice_id)
        return _performance_response(reference)
    except HTTPException:
        shutil.rmtree(performance_dir, ignore_errors=True)
        raise
    except AudioProcessingError as exc:
        shutil.rmtree(performance_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(performance_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    finally:
        file.file.close()


@app.get(f"{settings.api_prefix}/voices/{{voice_id}}/performances/{{preset}}/preview")
def preview_voice_performance(voice_id: str, preset: str) -> FileResponse:
    reference = get_performance_reference(voice_id, preset)
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Performance reference not found.")
    return FileResponse(_path_for_record(reference["reference_audio_path"]), media_type="audio/wav")


@app.delete(f"{settings.api_prefix}/voices/{{voice_id}}/performances/{{preset}}", status_code=status.HTTP_204_NO_CONTENT)
def remove_voice_performance(voice_id: str, preset: str) -> None:
    reference = delete_performance_reference(voice_id, preset)
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Performance reference not found.")
    engine.clear_prompt(voice_id)
    shutil.rmtree(settings.voices_dir / voice_id / "performances" / preset, ignore_errors=True)


@app.delete(f"{settings.api_prefix}/voices/{{voice_id}}", status_code=status.HTTP_204_NO_CONTENT)
def remove_voice(voice_id: str) -> None:
    deleted = delete_voice(voice_id)
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    voice, generations = deleted
    engine.clear_prompt(voice_id)
    for generation in generations:
        shutil.rmtree(settings.generations_dir / generation["id"], ignore_errors=True)
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
    if payload.engine_id != engine.engine_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Engine '{payload.engine_id}' is not installed.")
    spoken_text = normalize_text(payload.text.strip(), payload.pronunciation_overrides) if payload.normalize_text else payload.text.strip()
    if payload.performance and payload.performance not in PERFORMANCE_PRESETS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown performance preset.")
    performance_reference = None
    performance_settings = PERFORMANCE_PRESETS.get(payload.performance or "neutral", {})
    if payload.performance:
        performance_reference = get_performance_reference(voice["id"], payload.performance)
    active_reference_audio = Path(performance_reference["reference_audio_path"]) if performance_reference else Path(voice["reference_audio_path"])
    active_reference_text = performance_reference["reference_text"] if performance_reference else voice["reference_text"]
    prompt_key = f"{voice['id']}:performance:{payload.performance}" if performance_reference else voice["id"]
    try:
        engine.synthesize(
            voice_id=prompt_key,
            reference_audio=active_reference_audio,
            reference_text=active_reference_text,
            text=spoken_text,
            language=payload.language,
            output_path=wav_path,
            settings={**performance_settings, **payload.engine_settings, "_mode": payload.mode},
        )
        synthesis_finished = time.perf_counter()
        effective_speed = payload.speed * float(performance_settings.get("pace", 1.0))
        time_stretch(wav_path, effective_speed)
        stretch_finished = time.perf_counter()
        exported_mp3 = export_mp3(wav_path, mp3_path)
        export_finished = time.perf_counter()
        measured_duration = duration_seconds(wav_path)
        probe_finished = time.perf_counter()
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
            duration_seconds=measured_duration,
            generation_seconds=elapsed,
            wav_path=wav_path,
            mp3_path=mp3_path if exported_mp3 else None,
            normalized_text=spoken_text,
            engine_id=payload.engine_id,
            mode=payload.mode,
            performance=payload.performance,
            seed=payload.seed,
            settings={
                "normalize_text": payload.normalize_text,
                "speed": payload.speed,
                **payload.engine_settings,
                "performance_parameters": performance_settings,
                "effective_speed": effective_speed,
                **engine.last_effective_settings,
                "phase_timings": {
                    **engine.last_timings,
                    "post_speed_seconds": round(stretch_finished - synthesis_finished, 3),
                    "mp3_export_seconds": round(export_finished - stretch_finished, 3),
                    "duration_probe_seconds": round(probe_finished - export_finished, 3),
                    "request_total_seconds": elapsed,
                },
            },
            reference_set=([performance_reference["original_sample_path"]] if performance_reference else list(voice["original_sample_paths"])),
            benchmark_label=payload.benchmark_label,
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


@app.get(f"{settings.api_prefix}/generations/{{generation_id}}", response_model=GenerationResponse)
def get_generation_detail(generation_id: str) -> GenerationResponse:
    generation = get_generation(generation_id)
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    return _generation_response(generation)


@app.patch(f"{settings.api_prefix}/generations/{{generation_id}}", response_model=GenerationResponse)
def patch_generation(generation_id: str, payload: GenerationPatchRequest) -> GenerationResponse:
    generation = update_generation_label(generation_id, payload.benchmark_label)
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    return _generation_response(generation)


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


@app.delete(f"{settings.api_prefix}/generations/{{generation_id}}", status_code=status.HTTP_204_NO_CONTENT)
def remove_generation(generation_id: str) -> None:
    generation = delete_generation(generation_id)
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    shutil.rmtree(settings.generations_dir / generation_id, ignore_errors=True)
