"""Ports (Protocols) for external dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from a_wizard.domain.models import Project, SpeakerTurn, TranscriptResult


class ProjectRepository(Protocol):
    def load(self, project_dir: Path) -> Project: ...

    def save(self, project_dir: Path, project: Project) -> None: ...

    def exists(self, project_dir: Path) -> bool: ...


class ArtifactStore(Protocol):
    def write_text(self, project_dir: Path, rel: str, text: str) -> str: ...

    def write_json(self, project_dir: Path, rel: str, data: Any) -> str: ...

    def write_bytes(self, project_dir: Path, rel: str, data: bytes) -> str: ...

    def read_text(self, project_dir: Path, rel: str) -> str: ...

    def digest(self, project_dir: Path, rel: str) -> str: ...


class ProjectLock(Protocol):
    def acquire(self, project_dir: Path) -> None: ...

    def release(self, project_dir: Path) -> None: ...


class MediaProbe(Protocol):
    def probe(self, video: Path) -> dict[str, Any]: ...


class AudioExtractor(Protocol):
    def extract_all(self, video: Path, project_dir: Path, *, force: bool = False) -> list[Path]: ...

    def mixdown(
        self,
        wavs: list[Path],
        out: Path,
        *,
        force: bool = False,
    ) -> Path: ...


class TranscriptionEngine(Protocol):
    adapter_id: str

    def transcribe(
        self,
        wav: Path,
        *,
        speaker: str | None = None,
        model: str = "large-v3",
        language: str = "ru",
        compute_type: str = "int8",
        device: str = "auto",
        initial_prompt: str | None = None,
    ) -> TranscriptResult: ...


class DiarizationEngine(Protocol):
    adapter_id: str

    def diarize(
        self,
        wav: Path,
        *,
        num_speakers: int | None = None,
        threshold: float | None = None,
        hf_token: str | None = None,
    ) -> list[SpeakerTurn]: ...


class ChannelEnergyProfiler(Protocol):
    def profile(self, wav: Path, *, window_ms: int = 20) -> Any: ...


class RunObserver(Protocol):
    def event(self, name: str, **fields: Any) -> None: ...
