from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    active_device: str
    accelerator_available: bool
    gpu_name: str | None = None
    vram_total_mb: int | None = None
    model_id: str
    model_loaded: bool


class VoiceProfile(BaseModel):
    id: str
    name: str
    duration_seconds: float
    reference_text: str | None = None
    created_at: datetime
    updated_at: datetime
    preview_url: str
    original_sample_count: int


class VoiceListResponse(BaseModel):
    voices: list[VoiceProfile]
    device: DeviceInfo


class VoiceCreatedResponse(BaseModel):
    voice: VoiceProfile
    message: str


class GenerationRequest(BaseModel):
    voice_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=5000)
    language: Literal[
        "English",
        "Chinese",
        "Japanese",
        "Korean",
        "German",
        "French",
        "Russian",
        "Portuguese",
        "Spanish",
        "Italian",
        "Auto",
    ] = "English"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class GenerationResponse(BaseModel):
    id: str
    voice_id: str
    text: str
    language: str
    speed: float
    model_id: str
    device: str
    duration_seconds: float | None
    generation_seconds: float
    created_at: datetime
    audio_url: str
    wav_download_url: str
    mp3_download_url: str | None = None


class GenerationListResponse(BaseModel):
    generations: list[GenerationResponse]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    device: DeviceInfo
