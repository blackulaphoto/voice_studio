from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineCapabilities:
    voice_cloning: bool = True
    multilingual: bool = False
    true_streaming: bool = False
    chunked_progressive: bool = False
    speed: bool = False
    temperature: bool = False
    seed: bool = False
    style: bool = False
    emotion: bool = False
    paralinguistic_tags: tuple[str, ...] = ()
    supported_languages: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TTSEngine(ABC):
    engine_id: str
    display_name: str
    model_id: str

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def capabilities(self) -> EngineCapabilities: ...

    @abstractmethod
    def hardware(self) -> Any: ...

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def unload(self) -> None: ...

    @abstractmethod
    def clear_prompt(self, voice_id: str) -> None: ...

    @abstractmethod
    def synthesize(self, *, voice_id: str, reference_audio: Path,
                   reference_text: str | None, text: str, language: str,
                   output_path: Path, settings: dict[str, Any] | None = None) -> int: ...
