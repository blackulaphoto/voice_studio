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

from .audio.processing import (
    AudioProcessingError,
    blend_breath,
    duration_seconds,
    export_mp3,
    find_degenerate_tail_start,
    preprocess_reference,
    rescale_internal_pauses,
    shape_energy,
    time_stretch,
    trim_outer_silence,
    truncate_at,
)
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
# Native Qwen sampling knobs (temperature/top_k/top_p/repetition_penalty/subtalker_*) drive
# pitch/rhythm variation the identity-safe way: it's still the model's own generation, nothing
# reshaped after the fact. pace/pause_scale/energy/breath are post-processing dials applied in
# backend/app/audio/processing.py (time_stretch, rescale_internal_pauses, shape_energy,
# blend_breath respectively) — see PROJECT_SCHEMA_AND_HANDOFF.md for the full pipeline order and
# why each stage must run where it does. All four are clamped server-side in synthesize() so a
# slider value (or a bad preset edit) cannot produce pathological audio.
PERFORMANCE_PRESETS = {
    "neutral": {},
    "warm": {
        "temperature": 0.85, "top_p": 0.90, "subtalker_temperature": 0.85,
        "pace": 0.96, "pause_scale": 1.1, "energy": 1.05,
    },
    "playful": {
        "temperature": 1.25, "top_k": 80, "top_p": 1.0, "subtalker_temperature": 1.20, "subtalker_top_k": 80,
        "pace": 1.08, "pause_scale": 0.70, "energy": 1.35,
    },
    "serious": {
        "temperature": 0.55, "top_p": 0.75, "repetition_penalty": 1.10, "subtalker_temperature": 0.55,
        "pace": 0.90, "pause_scale": 1.60, "energy": 0.75,
    },
    "soft": {
        "temperature": 0.72, "top_p": 0.85, "repetition_penalty": 1.06, "subtalker_temperature": 0.70,
        "pace": 0.92, "pause_scale": 1.25, "energy": 0.78, "breath": 0.20,
    },
    "excited": {
        "temperature": 1.30, "top_k": 85, "top_p": 1.0, "subtalker_temperature": 1.28, "subtalker_top_k": 85,
        "pace": 1.15, "pause_scale": 0.55, "energy": 1.50,
    },
    "concerned": {
        "temperature": 0.78, "top_p": 0.85, "repetition_penalty": 1.08, "subtalker_temperature": 0.75,
        "pace": 0.90, "pause_scale": 1.35, "energy": 0.85, "breath": 0.10,
    },
    "firm": {
        "temperature": 0.60, "top_p": 0.78, "repetition_penalty": 1.08, "subtalker_temperature": 0.58,
        "pace": 1.00, "pause_scale": 0.80, "energy": 1.20,
    },
    "intimate": {
        # repetition_penalty was 1.05 (golden default, the weakest in this whole preset set) and
        # ran away for 8+ minutes on the Phase 3 evaluation sentence — low temperature + weak
        # repetition_penalty is a classic degenerate-repeat-loop combo. Raised to 1.09, matching
        # the safety-margin pattern already used by every other low-temperature preset here.
        "temperature": 0.70, "top_p": 0.85, "repetition_penalty": 1.09, "subtalker_temperature": 0.68,
        "pace": 0.78, "pause_scale": 1.80, "energy": 0.62, "breath": 0.40,
    },
    "tired": {
        "temperature": 0.80, "top_p": 0.88, "repetition_penalty": 1.10, "subtalker_temperature": 0.76,
        "pace": 0.76, "pause_scale": 1.50, "energy": 0.65, "breath": 0.15,
    },
}
DELIVERY_BOUNDS = {
    "pace": (0.5, 1.6),
    "pause_scale": (0.3, 3.0),
    "energy": (0.5, 1.8),
    "breath": (0.0, 1.0),
}


def _clamped_delivery_dial(settings: dict, name: str, default: float) -> float:
    low, high = DELIVERY_BOUNDS[name]
    return max(low, min(float(settings.get(name, default)), high))


# Confirmed via upstream research (github.com/QwenLM/Qwen3-TTS PR #178): "without repetition
# penalty, the model can fall into a degenerate state where it keeps sampling the same codec
# tokens over and over" — exactly the failure mode behind the "Phase 4 follow-up 5" incidents.
# Original/Neutral delivery previously applied zero override (the bare model default, ~1.05 —
# the single weakest setting in this whole app). This is a small, defensive floor, not a
# character change: every built-in preset that already sets repetition_penalty already sits at
# or above this value except Intimate's original 1.05 (separately fixed to 1.09 after its own
# runaway — see PERFORMANCE_PRESETS). Applied everywhere, including Original delivery and
# Warm/Playful/Excited (which previously had no override at all); an explicit user/preset value
# still wins. Note this technically means Original delivery's effective settings are no longer
# literally "None" as recorded in docs/baseline.md's frozen Golden Baseline — this is a
# perceptible-risk trade-off made deliberately, not silently; flag it if Warm sounds different.
MIN_REPETITION_PENALTY = 1.08


def _estimate_max_tokens(text: str) -> int:
    """Bound worst-case generation length for one engine call.

    2026-08-16/17: a plain Original-delivery generation stalled for 11+ minutes with no crash —
    a degenerate repeat-loop (same failure mode as the earlier Intimate/Concerned incidents),
    except this one was never actually bounded: Qwen's own max_new_tokens default is 2048, which
    on CPU can take many minutes to exhaust even when the extra tokens are pure repetition. This
    was always a latent risk on every single-call generation, not something Phase 4's
    phrase-segmented synthesis introduced — it just multiplied the number of independent calls
    (and therefore independent chances of hitting it) from one to several per request.

    First cap (80 tokens/word) was a blind guess and turned out to be drastically oversized: a
    real runaway hit the 1800-token ceiling and produced ~149s of audio — only ~29s of which was
    real speech, the rest degenerate noise/squeaks. 1800 tokens / 149s ≈ 12.08 tokens/sec, which
    lines up almost exactly with "Qwen3-TTS-**12Hz**" — i.e. max_new_tokens counts acoustic
    frames at the model's native 12Hz rate, not some larger multi-codebook token count. At a
    conservative (slow) 1.6 words/sec speaking floor, that's ~7.5 tokens/word; a 2x safety
    multiplier over that — generous headroom for slow/dramatic delivery and internal pauses,
    without leaving room for another two minutes of garbage after real content ends — gives ~15
    tokens/word. Floored at 200, capped at 1400 (≈117s of audio-equivalent ceiling; a legitimately
    long paragraph can still hit this, in which case retry with shorter text). This bounds
    worst-case latency AND worst-case garbage-tail length per call. See also the raw-duration
    sanity check right after the engine call in synthesize() — this cap alone does not guarantee
    clean output, only a bounded one; that check is what actually rejects a degenerate run instead
    of silently shipping it.
    """
    words = max(1, len(text.split()))
    return max(200, min(1400, round(words * 15)))


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


@app.get(f"{settings.api_prefix}/performance-presets")
def get_performance_presets() -> dict:
    """Preset defaults plus slider bounds, so the UI never duplicates PERFORMANCE_PRESETS."""
    return {"presets": PERFORMANCE_PRESETS, "bounds": DELIVERY_BOUNDS}


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
    merged_settings = {**performance_settings, **payload.engine_settings}
    if payload.performance:
        performance_reference = get_performance_reference(voice["id"], payload.performance)
    active_reference_audio = Path(performance_reference["reference_audio_path"]) if performance_reference else Path(voice["reference_audio_path"])
    active_reference_text = performance_reference["reference_text"] if performance_reference else voice["reference_text"]
    prompt_key = f"{voice['id']}:performance:{payload.performance}" if performance_reference else voice["id"]
    pace = _clamped_delivery_dial(merged_settings, "pace", 1.0)
    pause_scale = _clamped_delivery_dial(merged_settings, "pause_scale", 1.0)
    energy = _clamped_delivery_dial(merged_settings, "energy", 1.0)
    breath = _clamped_delivery_dial(merged_settings, "breath", 0.0)
    engine_settings_for_call = {"repetition_penalty": MIN_REPETITION_PENALTY, **merged_settings, "_mode": payload.mode}
    try:
        # Phase 4's phrase-segmented synthesis (separate model call per clause, reassembled with
        # constructed pauses) is DISABLED as of 2026-08-17 per direct user feedback: it produced
        # unnatural results (5-second dead gaps between phrases in one attempt, every phrase
        # reading as a new, disconnected sentence rather than a continuous conversational line in
        # another) even after fixing the bugs found along the way (tempo-artifact "underwater"
        # sound, unbounded per-call runaway, internal silence bloat within a segment). Reverted to
        # single-call synthesis — the original "words run together" complaint this was meant to
        # fix is back, by the user's explicit choice, until a better approach is found. The
        # segment_phrases/concatenate_with_pauses machinery (text/segmentation.py,
        # audio/processing.py) is left in place, tested, and unused — do not wire it back into
        # this endpoint without the user asking; read the Phase 4 section in
        # PROJECT_SCHEMA_AND_HANDOFF.md first for exactly what went wrong.
        #
        # max_new_tokens IS kept from that work — it's a real, independent bug fix (an unbounded
        # single call can still run away in wall-clock time; this was true since Phase 0, not
        # something Phase 4 introduced) and has nothing to do with the phrasing/cadence problem.
        call_settings = {"max_new_tokens": _estimate_max_tokens(spoken_text), **engine_settings_for_call}
        engine.synthesize(
            voice_id=prompt_key,
            reference_audio=active_reference_audio,
            reference_text=active_reference_text,
            text=spoken_text,
            language=payload.language,
            output_path=wav_path,
            settings=call_settings,
        )
        engine_timings = engine.last_timings
        # A bounded token budget stops a degenerate run from taking forever, but does nothing to
        # stop the garbage it produces from being shipped as if it were valid speech. Two layers:
        #
        # Layer 1 — detect and SALVAGE. Discovered for real (twice): a run that should have been
        # ~20-29s of speech instead came out 88-150s, with 60-120s of quiet, spiky "noise/
        # squeaks" appended after the real content ended, silently baked into the WAV. Plain
        # silencedetect cannot catch this — the garbage is quiet-but-not-silent and transient,
        # never accumulating a continuous silent run — so find_degenerate_tail_start instead
        # tracks each window's RMS against the loudest window seen so far and looks for a
        # sustained drop. When found, truncate right there and keep the good part instead of
        # discarding the whole take — the user is trying to A/B-compare delivery settings and
        # losing a otherwise-good take to a full retry is real cost, not just an inconvenience.
        degenerate_tail_start = find_degenerate_tail_start(wav_path)
        if degenerate_tail_start is not None:
            truncate_at(wav_path, degenerate_tail_start)
        # Layer 2 — backstop for shapes Layer 1 doesn't catch (e.g. loud repetition with no
        # energy drop at all). Floor of 4.0s so very short text (with legitimate natural pause/
        # breath padding) is never false-flagged; otherwise (word_count / 1.6 words/sec) * 2.0
        # safety multiplier — see _estimate_max_tokens for where those numbers come from. Runs
        # on the post-truncation duration, so a Layer-1 salvage that left a plausible amount of
        # real content passes cleanly here.
        raw_duration = duration_seconds(wav_path)
        spoken_word_count = max(1, len(spoken_text.split()))
        plausible_ceiling = max(4.0, (spoken_word_count / 1.6) * 2.0)
        if raw_duration > plausible_ceiling:
            raise EngineUnavailableError(
                f"Generation produced {raw_duration:.1f}s of audio for {spoken_word_count} words "
                f"of text (plausible ceiling {plausible_ceiling:.1f}s) — almost certainly a "
                "degenerate run (noise or repetition after the real content ends), not valid "
                "speech. Please try generating again."
            )
        synthesis_finished = time.perf_counter()
        # Order matters: trim edges before pause-rescaling so every detected gap is genuinely
        # internal; rescale pauses before the uniform tempo change so pace still scales the
        # reshaped gaps along with speech; blend breath only after both silence-detection
        # passes, since a noise floor would defeat them; shape_energy runs last so its
        # loudnorm pass sets the final envelope including any added breath texture. See
        # PROJECT_SCHEMA_AND_HANDOFF.md for the full rationale.
        trimmed_seconds = trim_outer_silence(wav_path)
        trim_finished = time.perf_counter()
        pause_seconds_added = rescale_internal_pauses(wav_path, pause_scale=pause_scale)
        pause_finished = time.perf_counter()
        effective_speed = payload.speed * pace
        time_stretch(wav_path, effective_speed)
        stretch_finished = time.perf_counter()
        blend_breath(wav_path, breath)
        breath_finished = time.perf_counter()
        shape_energy(wav_path, energy)
        energy_finished = time.perf_counter()
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
                # Flat (not nested) so restoring/regenerating a saved generation — which sends
                # this whole settings dict back as engine_settings — reproduces the exact same
                # pace/pause_scale/energy/breath rather than silently falling back to the
                # preset's defaults for them.
                "pace": pace, "pause_scale": pause_scale, "energy": energy, "breath": breath,
                "effective_speed": effective_speed,
                "outer_trim_seconds_removed": trimmed_seconds,
                "pause_seconds_added": pause_seconds_added,
                "degenerate_tail_trimmed_at_seconds": degenerate_tail_start,
                **engine.last_effective_settings,
                "phase_timings": {
                    **engine_timings,
                    "outer_trim_seconds": round(trim_finished - synthesis_finished, 3),
                    "pause_rescale_seconds": round(pause_finished - trim_finished, 3),
                    "post_speed_seconds": round(stretch_finished - pause_finished, 3),
                    "breath_seconds": round(breath_finished - stretch_finished, 3),
                    "energy_shape_seconds": round(energy_finished - breath_finished, 3),
                    "mp3_export_seconds": round(export_finished - energy_finished, 3),
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
