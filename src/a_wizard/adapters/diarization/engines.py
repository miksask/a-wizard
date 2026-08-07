"""Diarization adapters: mock and pure diarize backends."""

from __future__ import annotations

import os
from pathlib import Path

from a_wizard.domain.errors import AppError, BlockedError
from a_wizard.domain.models import SpeakerTurn


class MockDiarAdapter:
    adapter_id = "mock-diar"

    def __init__(
        self,
        turns: list[SpeakerTurn] | None = None,
        *,
        segments: list | None = None,
    ) -> None:
        if turns is not None and turns and hasattr(turns[0], "text"):
            # backwards-compat: list[Segment] passed positionally
            segments = list(turns)
            turns = None
        if turns is not None:
            self._turns = turns
        elif segments is not None:
            self._turns = [
                SpeakerTurn(s.start_ms, s.end_ms, s.speaker) for s in segments
            ]
        else:
            self._turns = None

    def diarize(
        self,
        wav: Path,
        *,
        num_speakers: int | None = None,
        threshold: float | None = None,
        hf_token: str | None = None,
    ) -> list[SpeakerTurn]:
        if self._turns is not None:
            return list(self._turns)
        return [
            SpeakerTurn(0, 1500, "SPEAKER_00"),
            SpeakerTurn(1600, 3000, "SPEAKER_01"),
        ]


class PyannoteCommunity1Adapter:
    """Optional Python quality fallback (not default)."""

    adapter_id = "pyannote-community-1"

    def diarize(
        self,
        wav: Path,
        *,
        num_speakers: int | None = None,
        threshold: float | None = None,
        hf_token: str | None = None,
    ) -> list[SpeakerTurn]:
        try:
            from pyannote.audio import Pipeline
        except ImportError as e:
            raise AppError(
                "pyannote.audio is not installed. Run: uv sync --extra diar-pyannote",
                code="diar_dep_missing",
                next_step="uv sync --extra diar-pyannote",
                cause=e,
            ) from e

        token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if not token:
            raise BlockedError(
                "HF_TOKEN required for pyannote-community-1",
                code="hf_token_missing",
                next_step="export HF_TOKEN=... and accept community-1 model terms",
            )

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-community-1",
            token=token,
        )
        diarization = pipeline(str(wav), num_speakers=num_speakers)
        turns: list[SpeakerTurn] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(SpeakerTurn.from_seconds(float(turn.start), float(turn.end), str(speaker)))
        return turns


def resolve_diar_adapter(name: str = "auto"):
    from a_wizard.adapters.diarization.fluidaudio import FluidAudioDiarAdapter, fluidaudio_bin
    from a_wizard.adapters.diarization.sherpa import SherpaOnnxDiarAdapter
    from a_wizard.adapters.diarization.speakrs import SpeakrsDiarAdapter

    key = (name or "auto").lower()
    if key in ("mock", "mock-diar"):
        return MockDiarAdapter()
    if key == "fluidaudio":
        return FluidAudioDiarAdapter()
    if key in ("sherpa-onnx", "sherpa"):
        return SherpaOnnxDiarAdapter()
    if key in ("speakrs-coreml", "speakrs"):
        return SpeakrsDiarAdapter()
    if key in ("pyannote-community-1", "pyannote"):
        return PyannoteCommunity1Adapter()
    if key == "auto":
        if fluidaudio_bin():
            return FluidAudioDiarAdapter()
        try:
            import sherpa_onnx  # noqa: F401

            return SherpaOnnxDiarAdapter()
        except ImportError:
            pass
        raise AppError(
            "No diarization adapter available. Install FluidAudio CLI "
            "(fluidaudio on PATH) or: uv sync --extra diar-onnx",
            code="diar_adapter_missing",
            next_step="install fluidaudio or uv sync --extra diar-onnx",
        )
    raise AppError(f"Unknown diarization adapter: {name}", code="unknown_diar_adapter")
