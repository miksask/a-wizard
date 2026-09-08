"""Freshness signatures and digests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from a_wizard.domain.models import ProcessingMode, Project, StageStatus, Track


ALGORITHM_VERSION = "a-wizard-2"


def sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def signature(*parts: Any) -> str:
    payload = canonical_json([ALGORITHM_VERSION, *parts])
    return sha256_bytes(payload.encode("utf-8"))


def track_asr_config(project: Project, track: Track) -> dict[str, Any]:
    """ASR options for a track — language/prompt always from project defaults."""
    defaults = project.transcription_defaults or {}
    return {
        "model": defaults.get("model", "large-v3"),
        "language": defaults.get("language", "ru"),
        "compute_type": defaults.get("compute_type", "int8"),
        "device": defaults.get("device", "auto"),
        "initial_prompt": defaults.get("initial_prompt"),
        "mode": track.mode.value,
        "plain_speaker": track.plain_speaker,
        "adapter": project.adapters.get("asr"),
        "diar_adapter": project.adapters.get("diarization"),
    }


def mix_asr_config(project: Project) -> dict[str, Any]:
    defaults = project.transcription_defaults or {}
    return {
        "model": defaults.get("model"),
        "language": defaults.get("language", "ru"),
        "compute_type": defaults.get("compute_type", "int8"),
        "device": defaults.get("device", "auto"),
        "initial_prompt": defaults.get("initial_prompt"),
        "adapter": project.adapters.get("asr"),
    }


def channel_roles(project: Project) -> list[dict[str, Any]]:
    return [
        {
            "index": t.index,
            "mode": t.mode.value,
            "plain_speaker": t.plain_speaker,
        }
        for t in project.tracks
    ]


def extract_signature(project: Project) -> str:
    return signature(
        "extract",
        project.source.get("path"),
        project.source.get("content_fingerprint"),
        project.source.get("audio_stream_count"),
        project.adapters.get("media"),
    )


def mixdown_signature(project: Project) -> str:
    active = [t.index for t in project.tracks if t.mode.value != "skipped"]
    return signature(
        "mixdown",
        project.mix.wav,
        active,
        project.stage("extract").output_digests,
        project.adapters.get("media"),
    )


def mix_transcribe_signature(project: Project) -> str:
    return signature(
        "transcribe:mix",
        project.mix.wav,
        mix_asr_config(project),
        project.stage("mixdown").output_digests,
    )


def attribute_signature(project: Project) -> str:
    return signature(
        "attribute",
        channel_roles(project),
        project.adapters.get("diarization"),
        project.stage("transcribe:mix").output_digests,
        project.stage("mixdown").output_digests,
    )


def transcribe_signature(project: Project, track: Track) -> str:
    return signature("transcribe", track.index, track.wav, track_asr_config(project, track))


def merge_signature(project: Project) -> str:
    if project.processing_mode == ProcessingMode.MIXDOWN:
        return signature(
            "merge",
            "mixdown",
            project.mix.segments,
            channel_roles(project),
            project.stage("attribute").output_digests,
        )
    parts = []
    for t in project.tracks:
        if t.mode.value == "skipped":
            parts.append({"index": t.index, "mode": "skipped"})
            continue
        parts.append(
            {
                "index": t.index,
                "mode": t.mode.value,
                "plain_speaker": t.plain_speaker,
                "segments": t.segments,
                "status": t.status.value,
            }
        )
    return signature("merge", parts)


def minimize_signature(project: Project) -> str:
    return signature(
        "minimize",
        project.speaker_glyphs,
        "dialog/dialog.json",
        project.stage("merge").output_digests,
    )


def mark_stale_downstream(project: Project, changed: str) -> list[str]:
    """Mark dependent stages stale. Returns list of invalidated keys."""
    invalidated: list[str] = []

    def stale(key: str) -> None:
        rec = project.stage(key)
        if rec.status.value in ("succeeded", "running", "failed", "interrupted"):
            rec.status = StageStatus.STALE
            invalidated.append(key)

    if changed in ("source", "extract"):
        stale("extract")
        stale("mixdown")
        stale("transcribe:mix")
        stale("attribute")
        for t in project.tracks:
            stale(f"transcribe:{t.index}")
        stale("merge")
        stale("minimize")
    elif changed == "mixdown":
        stale("mixdown")
        stale("transcribe:mix")
        stale("attribute")
        stale("merge")
        stale("minimize")
    elif changed == "transcribe:mix":
        stale("transcribe:mix")
        stale("attribute")
        stale("merge")
        stale("minimize")
    elif changed in ("channel_roles", "attribute"):
        # Role changes invalidate attribution but keep mix ASR.
        stale("attribute")
        stale("merge")
        stale("minimize")
    elif changed == "skipped_set":
        stale("mixdown")
        stale("transcribe:mix")
        stale("attribute")
        stale("merge")
        stale("minimize")
    elif changed.startswith("track:"):
        idx = int(changed.split(":")[1])
        if project.processing_mode == ProcessingMode.MIXDOWN:
            # Channel role change keeps mix ASR; re-attribute only.
            stale("attribute")
        else:
            stale(f"transcribe:{idx}")
        stale("merge")
        stale("minimize")
    elif changed.startswith("speakers:"):
        stale("merge")
        stale("minimize")
        if project.processing_mode == ProcessingMode.MIXDOWN:
            # Reviewed map applied at merge; attribute output stays.
            pass
    elif changed == "glyphs":
        stale("minimize")
    elif changed == "asr_config":
        if project.processing_mode == ProcessingMode.MIXDOWN:
            stale("transcribe:mix")
            stale("attribute")
        else:
            for t in project.tracks:
                if t.mode.value != "skipped":
                    stale(f"transcribe:{t.index}")
        stale("merge")
        stale("minimize")
    elif changed == "merge":
        stale("merge")
        stale("minimize")
    return invalidated
