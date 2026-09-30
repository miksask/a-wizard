"""Freshness signatures, digests, and stage contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a_wizard.domain.models import ProcessingMode, Project, StageStatus, Track

ALGORITHM_VERSION = "a-wizard-2"
ENERGY_ALGORITHM_VERSION = "a-wizard-2-energy-v1"


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


def content_fingerprint(path: Path, *, full_limit: int = 64 * 1024 * 1024) -> str:
    """Stable content identity: full SHA-256 when small; else sampled hash."""
    path = path.resolve()
    st = path.stat()
    size = int(st.st_size)
    if size <= full_limit:
        return f"sha256:{sha256_file(path)}"
    head = 1024 * 1024
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(head))
        if size > head:
            f.seek(max(0, size - head))
            h.update(f.read(head))
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
    return f"sampled:{size}:{mtime_ns}:{h.hexdigest()}"


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


@dataclass(frozen=True)
class StageContract:
    key: str
    signature_fn: Callable[[Project], str]
    required_outputs: tuple[str, ...]
    digest_aliases: dict[str, str]


def _extract_outputs(project: Project) -> tuple[str, ...]:
    n = int(project.source.get("audio_stream_count") or len(project.tracks) or 0)
    return tuple(f"tracks/track_{i}.wav" for i in range(n))


def _extract_aliases(project: Project) -> dict[str, str]:
    n = int(project.source.get("audio_stream_count") or len(project.tracks) or 0)
    return {f"track_{i}": f"tracks/track_{i}.wav" for i in range(n)}


def _mixdown_contract(project: Project) -> StageContract:
    return StageContract(
        key="mixdown",
        signature_fn=mixdown_signature,
        required_outputs=(project.mix.wav,),
        digest_aliases={"mix": project.mix.wav},
    )


def _mix_transcribe_contract(project: Project) -> StageContract:
    raw = "transcripts/mix.raw.json"
    return StageContract(
        key="transcribe:mix",
        signature_fn=mix_transcribe_signature,
        required_outputs=(raw,),
        digest_aliases={"raw": raw},
    )


def _attribute_contract(project: Project) -> StageContract:
    return StageContract(
        key="attribute",
        signature_fn=attribute_signature,
        required_outputs=(
            project.mix.segments,
            project.mix.transcript_txt,
            project.mix.attribution,
        ),
        digest_aliases={
            "segments": project.mix.segments,
            "txt": project.mix.transcript_txt,
            "report": project.mix.attribution,
        },
    )


def _merge_contract(project: Project) -> StageContract:
    return StageContract(
        key="merge",
        signature_fn=merge_signature,
        required_outputs=("dialog/dialog.json", "dialog/dialog.txt"),
        digest_aliases={
            "dialog_json": "dialog/dialog.json",
            "dialog_txt": "dialog/dialog.txt",
        },
    )


def _minimize_contract(project: Project) -> StageContract:
    return StageContract(
        key="minimize",
        signature_fn=minimize_signature,
        required_outputs=(
            "dialog/dialog.minimize.ts.txt",
            "dialog/dialog.minimize.txt",
            "dialog/transcript.txt",
        ),
        digest_aliases={"minimize": "dialog/dialog.minimize.txt"},
    )


def _transcribe_track_contract(project: Project, track: Track) -> StageContract:
    return StageContract(
        key=f"transcribe:{track.index}",
        signature_fn=lambda p, t=track: transcribe_signature(p, t),
        required_outputs=(track.segments, track.transcript_txt),
        digest_aliases={
            "segments": track.segments,
            "txt": track.transcript_txt,
        },
    )


def stage_contracts(project: Project) -> list[StageContract]:
    """Ordered contracts for stages that can be succeeded and verified."""
    contracts: list[StageContract] = [
        StageContract(
            key="extract",
            signature_fn=extract_signature,
            required_outputs=_extract_outputs(project),
            digest_aliases=_extract_aliases(project),
        )
    ]
    if project.processing_mode == ProcessingMode.MIXDOWN:
        contracts.extend(
            [
                _mixdown_contract(project),
                _mix_transcribe_contract(project),
                _attribute_contract(project),
            ]
        )
    else:
        for t in project.tracks:
            if t.mode.value == "skipped":
                continue
            contracts.append(_transcribe_track_contract(project, t))
    contracts.extend([_merge_contract(project), _minimize_contract(project)])
    return contracts


def resolve_digest_map(contract: StageContract, digests: dict[str, str]) -> dict[str, str]:
    """Map recorded digests to relative artifact paths."""
    out: dict[str, str] = {}
    for key, digest in (digests or {}).items():
        if key in contract.required_outputs:
            out[key] = digest
        elif key in contract.digest_aliases:
            out[contract.digest_aliases[key]] = digest
        else:
            # Unknown key: keep as-is if it looks like a path
            if "/" in key or key.endswith((".wav", ".json", ".txt", ".npy")):
                out[key] = digest
    return out


def path_digest_dict(paths_to_digests: dict[str, str]) -> dict[str, str]:
    """Normalize writer output to path-keyed digests."""
    return dict(paths_to_digests)


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
            stale("attribute")
        else:
            stale(f"transcribe:{idx}")
        stale("merge")
        stale("minimize")
    elif changed.startswith("speakers:"):
        stale("merge")
        stale("minimize")
        if project.processing_mode == ProcessingMode.MIXDOWN:
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
    elif changed == "asr_adapter":
        if project.processing_mode == ProcessingMode.MIXDOWN:
            stale("transcribe:mix")
            stale("attribute")
        else:
            for t in project.tracks:
                if t.mode.value != "skipped":
                    stale(f"transcribe:{t.index}")
        stale("merge")
        stale("minimize")
    elif changed == "diar_adapter":
        if project.processing_mode == ProcessingMode.MIXDOWN:
            stale("attribute")
        else:
            for t in project.tracks:
                if t.mode.value == "diarized":
                    stale(f"transcribe:{t.index}")
        stale("merge")
        stale("minimize")
    elif changed == "merge":
        stale("merge")
        stale("minimize")
    elif changed == "minimize":
        stale("minimize")
    elif changed.startswith("transcribe:"):
        # per-track transcription stage key
        stale(changed)
        stale("merge")
        stale("minimize")
    return invalidated


def invalidate_from_stage(project: Project, stage_key: str) -> list[str]:
    """Mark ``stage_key`` and dependents stale using the change-key graph."""
    if stage_key.startswith("transcribe:") and stage_key != "transcribe:mix":
        return mark_stale_downstream(project, stage_key)
    if stage_key in (
        "extract",
        "mixdown",
        "transcribe:mix",
        "attribute",
        "merge",
        "minimize",
        "asr_config",
        "asr_adapter",
        "diar_adapter",
        "skipped_set",
        "source",
    ):
        return mark_stale_downstream(project, stage_key)
    return mark_stale_downstream(project, stage_key)
