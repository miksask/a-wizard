"""Stage DAG planning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from a_wizard.domain.models import (
    ProcessingMode,
    Project,
    StageStatus,
    TrackMode,
    TrackStatus,
)


class ActionKind(str, Enum):
    INIT = "init"
    EXTRACT = "extract"
    MIXDOWN = "mixdown"
    CONFIGURE_PROMPT = "configure_prompt"
    CONFIGURE_TRACK = "configure_track"
    NEED_HF_TOKEN = "need_hf_token"
    TRANSCRIBE = "transcribe"
    TRANSCRIBE_MIX = "transcribe_mix"
    ATTRIBUTE = "attribute"
    EDIT_SPEAKERS = "edit_speakers"
    MERGE = "merge"
    MINIMIZE = "minimize"
    DONE = "done"


@dataclass(frozen=True)
class NextAction:
    kind: ActionKind
    track_index: int | None = None
    reason: str | None = None
    interactive: bool = False

    @property
    def stage_key(self) -> str:
        if self.kind == ActionKind.EXTRACT:
            return "extract"
        if self.kind == ActionKind.MIXDOWN:
            return "mixdown"
        if self.kind == ActionKind.TRANSCRIBE_MIX:
            return "transcribe:mix"
        if self.kind == ActionKind.ATTRIBUTE:
            return "attribute"
        if self.kind == ActionKind.TRANSCRIBE and self.track_index is not None:
            return f"transcribe:{self.track_index}"
        if self.kind == ActionKind.EDIT_SPEAKERS and self.track_index is not None:
            return f"speakers:{self.track_index}"
        if self.kind == ActionKind.MERGE:
            return "merge"
        if self.kind == ActionKind.MINIMIZE:
            return "minimize"
        return self.kind.value


def stage_succeeded(project: Project, key: str) -> bool:
    rec = project.stages.get(key)
    return rec is not None and rec.status == StageStatus.SUCCEEDED


def _diar_needs_hf(project: Project) -> bool:
    return project.adapters.get("diarization") == "pyannote-community-1"


def detect_next_action(
    project: Project | None,
    *,
    needs_init: bool = False,
    hf_token_available: bool = True,
    allow_raw_speakers: bool = False,
    skip_interactive: bool = False,
) -> NextAction:
    if needs_init or project is None:
        return NextAction(ActionKind.INIT, reason="project not initialized")

    if not stage_succeeded(project, "extract"):
        return NextAction(ActionKind.EXTRACT, reason="audio tracks not extracted")

    defaults = project.transcription_defaults or {}
    if not defaults.get("initial_prompt_reviewed") and not skip_interactive:
        return NextAction(
            ActionKind.CONFIGURE_PROMPT,
            interactive=True,
            reason="project initial_prompt not reviewed",
        )

    for t in project.tracks:
        if t.mode == TrackMode.PENDING:
            return NextAction(
                ActionKind.CONFIGURE_TRACK,
                track_index=t.index,
                interactive=True,
                reason=f"track {t.index} mode pending",
            )

    if project.processing_mode == ProcessingMode.MIXDOWN:
        return _detect_mixdown(
            project,
            hf_token_available=hf_token_available,
            allow_raw_speakers=allow_raw_speakers,
            skip_interactive=skip_interactive,
        )
    return _detect_per_track(
        project,
        hf_token_available=hf_token_available,
        allow_raw_speakers=allow_raw_speakers,
        skip_interactive=skip_interactive,
    )


def _detect_mixdown(
    project: Project,
    *,
    hf_token_available: bool,
    allow_raw_speakers: bool,
    skip_interactive: bool,
) -> NextAction:
    if not stage_succeeded(project, "mixdown"):
        return NextAction(ActionKind.MIXDOWN, reason="mix non-skipped tracks")

    if not stage_succeeded(project, "transcribe:mix"):
        return NextAction(ActionKind.TRANSCRIBE_MIX, reason="ASR on mix.wav")

    if not stage_succeeded(project, "attribute"):
        if _diar_needs_hf(project) and not hf_token_available:
            has_diar = any(t.mode == TrackMode.DIARIZED for t in project.tracks)
            if has_diar:
                return NextAction(
                    ActionKind.NEED_HF_TOKEN,
                    interactive=True,
                    reason="HF token required for pyannote-community-1",
                )
        return NextAction(ActionKind.ATTRIBUTE, reason="attribute speakers by channel energy")

    if not stage_succeeded(project, "merge"):
        return NextAction(ActionKind.MERGE, reason="merge dialog")

    if not stage_succeeded(project, "minimize"):
        return NextAction(ActionKind.MINIMIZE, reason="minimize dialog")

    return NextAction(ActionKind.DONE, reason="pipeline complete")


def _detect_per_track(
    project: Project,
    *,
    hf_token_available: bool,
    allow_raw_speakers: bool,
    skip_interactive: bool,
) -> NextAction:
    for t in project.tracks:
        if t.mode in (TrackMode.PLAIN, TrackMode.DIARIZED) and t.status != TrackStatus.TRANSCRIBED:
            if (
                t.mode == TrackMode.DIARIZED
                and _diar_needs_hf(project)
                and not hf_token_available
            ):
                return NextAction(
                    ActionKind.NEED_HF_TOKEN,
                    track_index=t.index,
                    interactive=True,
                    reason="HF token required for pyannote-community-1",
                )
            return NextAction(
                ActionKind.TRANSCRIBE,
                track_index=t.index,
                reason=f"transcribe track {t.index} ({t.mode.value})",
            )

    if not stage_succeeded(project, "merge"):
        return NextAction(ActionKind.MERGE, reason="merge dialog")

    if not stage_succeeded(project, "minimize"):
        return NextAction(ActionKind.MINIMIZE, reason="minimize dialog")

    return NextAction(ActionKind.DONE, reason="pipeline complete")


def describe_action(action: NextAction) -> str:
    if action.kind == ActionKind.DONE:
        return "Pipeline complete"
    if action.reason:
        return action.reason
    return action.kind.value
