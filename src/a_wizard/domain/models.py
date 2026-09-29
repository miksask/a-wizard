"""Domain models for a-wizard projects."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = 2
DEFAULT_GLYPHS = {"__EMPLOYEE__": "Δ", "__MANAGER__": "Ψ"}
VIDEO_SUFFIXES = {".mkv", ".mp4", ".mov", ".webm", ".avi", ".m4v"}
DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-turbo"

_DIAR_SPEAKER_RE = re.compile(r"^SPEAKER_(\d+)$")
_CANONICAL_PLAIN_RE = re.compile(r"^SPEAKER_T(\d+)$")
_CANONICAL_DIAR_RE = re.compile(r"^SPEAKER_T(\d+)D(\d+)$")
_LEGACY_SCOPED_RE = re.compile(r"^T(\d+)/SPEAKER_(\d+)$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ProcessingMode(str, Enum):
    MIXDOWN = "mixdown"
    PER_TRACK = "per_track"


class TrackMode(str, Enum):
    PENDING = "pending"
    PLAIN = "plain"
    DIARIZED = "diarized"
    SKIPPED = "skipped"


class TrackStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    TRANSCRIBED = "transcribed"
    SKIPPED = "skipped"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STALE = "stale"
    INTERRUPTED = "interrupted"


@dataclass
class Word:
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None
    channel: int | None = None
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError("invalid word timing")
        if not self.text.strip():
            raise ValueError("word text must be non-empty")

    @classmethod
    def from_seconds(cls, start: float, end: float, text: str, **kwargs: Any) -> Word:
        return cls(int(round(start * 1000)), int(round(end * 1000)), text.strip(), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Word:
        if "start_ms" in data:
            return cls(
                int(data["start_ms"]),
                int(data["end_ms"]),
                str(data["text"]),
                speaker=data.get("speaker"),
                channel=data.get("channel"),
                ambiguous=bool(data.get("ambiguous", False)),
            )
        return cls.from_seconds(
            float(data["start"]),
            float(data["end"]),
            str(data["text"]),
            speaker=data.get("speaker"),
            channel=data.get("channel"),
            ambiguous=bool(data.get("ambiguous", False)),
        )


@dataclass
class SpeakerTurn:
    start_ms: int
    end_ms: int
    speaker: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError("invalid turn timing")
        if not self.speaker:
            raise ValueError("speaker required")

    @classmethod
    def from_seconds(cls, start: float, end: float, speaker: str) -> SpeakerTurn:
        return cls(int(round(start * 1000)), int(round(end * 1000)), speaker)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeakerTurn:
        if "start_ms" in data:
            return cls(int(data["start_ms"]), int(data["end_ms"]), str(data["speaker"]))
        return cls.from_seconds(float(data["start"]), float(data["end"]), str(data["speaker"]))


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str
    speaker: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError("invalid segment timing")
        if not self.text.strip():
            raise ValueError("segment text must be non-empty")
        if not self.speaker:
            raise ValueError("segment speaker required")

    @classmethod
    def from_seconds(cls, start: float, end: float, text: str, speaker: str) -> Segment:
        return cls(int(round(start * 1000)), int(round(end * 1000)), text.strip(), speaker)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Segment:
        if "start_ms" in data:
            return cls(
                int(data["start_ms"]),
                int(data["end_ms"]),
                str(data["text"]),
                str(data["speaker"]),
            )
        return cls.from_seconds(
            float(data["start"]),
            float(data["end"]),
            str(data["text"]),
            str(data["speaker"]),
        )


@dataclass
class TranscriptResult:
    segments: list[Segment]
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class MixRefs:
    wav: str = "tracks/mix.wav"
    segments: str = "transcripts/mix.segments.json"
    transcript_txt: str = "transcripts/mix.txt"
    attribution: str = "meta/attribution.json"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MixRefs:
        data = data or {}
        return cls(
            wav=str(data.get("wav") or "tracks/mix.wav"),
            segments=str(data.get("segments") or "transcripts/mix.segments.json"),
            transcript_txt=str(data.get("transcript_txt") or "transcripts/mix.txt"),
            attribution=str(data.get("attribution") or "meta/attribution.json"),
        )


@dataclass
class StageRecord:
    status: StageStatus = StageStatus.PENDING
    signature: str | None = None
    attempt_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    adapter_id: str | None = None
    adapter_version: str | None = None
    model_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    output_digests: dict[str, str] = field(default_factory=dict)
    log_rel: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "signature": self.signature,
            "attempt_id": self.attempt_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "model_id": self.model_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "output_digests": dict(self.output_digests),
            "log_rel": self.log_rel,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StageRecord:
        data = data or {}
        return cls(
            status=StageStatus(data.get("status", "pending")),
            signature=data.get("signature"),
            attempt_id=data.get("attempt_id"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            adapter_id=data.get("adapter_id"),
            adapter_version=data.get("adapter_version"),
            model_id=data.get("model_id"),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            output_digests=dict(data.get("output_digests") or {}),
            log_rel=data.get("log_rel"),
        )


@dataclass
class Track:
    index: int
    wav: str
    mode: TrackMode = TrackMode.PENDING
    status: TrackStatus = TrackStatus.PENDING
    language: str = "ru"
    plain_speaker: str | None = None
    skip_reason: str | None = None
    initial_prompt: Any = field(default=...)  # Ellipsis = inherit; None = disabled
    speaker_map: dict[str, str] = field(default_factory=dict)
    speaker_map_reviewed: bool = False
    segments: str = ""
    transcript_txt: str = ""

    def __post_init__(self) -> None:
        if not self.segments:
            self.segments = f"transcripts/track_{self.index}.segments.json"
        if not self.transcript_txt:
            self.transcript_txt = f"transcripts/track_{self.index}.txt"

    def has_explicit_prompt(self) -> bool:
        return self.initial_prompt is not ...

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "index": self.index,
            "wav": self.wav,
            "mode": self.mode.value,
            "status": self.status.value,
            "language": self.language,
            "plain_speaker": self.plain_speaker,
            "skip_reason": self.skip_reason,
            "speaker_map": dict(self.speaker_map),
            "speaker_map_reviewed": self.speaker_map_reviewed,
            "segments": self.segments,
            "transcript_txt": self.transcript_txt,
        }
        if self.has_explicit_prompt():
            d["initial_prompt"] = self.initial_prompt
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Track:
        prompt: Any = ...
        if "initial_prompt" in data:
            prompt = data.get("initial_prompt")
        return cls(
            index=int(data["index"]),
            wav=str(data.get("wav") or f"tracks/track_{data['index']}.wav"),
            mode=TrackMode(data.get("mode", "pending")),
            status=TrackStatus(data.get("status", "pending")),
            language=str(data.get("language") or "ru"),
            plain_speaker=data.get("plain_speaker"),
            skip_reason=data.get("skip_reason"),
            initial_prompt=prompt,
            speaker_map=dict(data.get("speaker_map") or {}),
            speaker_map_reviewed=bool(data.get("speaker_map_reviewed")),
            segments=str(data.get("segments") or ""),
            transcript_txt=str(data.get("transcript_txt") or ""),
        )

    def is_merge_ready(self) -> bool:
        if self.mode == TrackMode.SKIPPED:
            return True
        if self.mode == TrackMode.PENDING:
            return False
        return self.status == TrackStatus.TRANSCRIBED


@dataclass
class Project:
    schema_version: int
    project_id: str
    created_at: str
    updated_at: str
    source: dict[str, Any]
    tracks: list[Track]
    transcription_defaults: dict[str, Any]
    stages: dict[str, StageRecord]
    speaker_glyphs: dict[str, str]
    adapters: dict[str, str]
    processing_mode: ProcessingMode = ProcessingMode.MIXDOWN
    mix: MixRefs = field(default_factory=MixRefs)

    @classmethod
    def new(
        cls,
        *,
        source_path: str,
        basename: str,
        audio_stream_count: int,
        duration_ms: int | None = None,
        fingerprint: str | None = None,
        processing_mode: ProcessingMode = ProcessingMode.MIXDOWN,
    ) -> Project:
        tracks = [
            Track(index=i, wav=f"tracks/track_{i}.wav") for i in range(audio_stream_count)
        ]
        now = utc_now_iso()
        return cls(
            schema_version=SCHEMA_VERSION,
            project_id=str(uuid4()),
            created_at=now,
            updated_at=now,
            source={
                "path": source_path,
                "basename": basename,
                "duration_ms": duration_ms,
                "audio_stream_count": audio_stream_count,
                "content_fingerprint": fingerprint,
            },
            tracks=tracks,
            transcription_defaults={
                "model": DEFAULT_MLX_MODEL,
                "language": "ru",
                "compute_type": "int8",
                "device": "auto",
                "initial_prompt": None,
                "initial_prompt_reviewed": False,
            },
            stages={},
            speaker_glyphs=dict(DEFAULT_GLYPHS),
            adapters={
                "media": "ffmpeg",
                "asr": "mlx-whisper",
                "diarization": "fluidaudio",
            },
            processing_mode=processing_mode,
            mix=MixRefs(),
        )

    def get_track(self, index: int) -> Track:
        for t in self.tracks:
            if t.index == index:
                return t
        raise KeyError(f"track {index} not found")

    def stage(self, key: str) -> StageRecord:
        if key not in self.stages:
            self.stages[key] = StageRecord()
        return self.stages[key]

    def active_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.mode != TrackMode.SKIPPED]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "processing_mode": self.processing_mode.value,
            "source": dict(self.source),
            "tracks": [t.to_dict() for t in self.tracks],
            "transcription_defaults": dict(self.transcription_defaults),
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "speaker_glyphs": dict(self.speaker_glyphs),
            "adapters": dict(self.adapters),
            "mix": self.mix.to_dict(),
            "extract": {"status": self.stage("extract").status.value},
            "merge": {
                "status": self.stage("merge").status.value,
                "dialog_txt": "dialog/dialog.txt",
                "dialog_json": "dialog/dialog.json",
            },
            "minimize": {
                "status": self.stage("minimize").status.value,
                "dialog_minimize_ts_txt": "dialog/dialog.minimize.ts.txt",
                "dialog_minimize_txt": "dialog/dialog.minimize.txt",
                "transcript_txt": "dialog/transcript.txt",
                "speaker_glyphs": dict(self.speaker_glyphs),
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        version = int(data.get("schema_version") or data.get("version") or 0)
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported manifest schema_version={version}; expected {SCHEMA_VERSION}"
            )
        stages_raw = data.get("stages") or {}
        if not stages_raw:
            for key in ("extract", "merge", "minimize"):
                st = (data.get(key) or {}).get("status")
                if st == "done":
                    stages_raw[key] = {"status": "succeeded"}
        mode_raw = data.get("processing_mode") or ProcessingMode.PER_TRACK.value
        # older manifests without processing_mode behave as per_track
        if "processing_mode" not in data and "mix" not in data:
            mode_raw = ProcessingMode.PER_TRACK.value
        return cls(
            schema_version=version,
            project_id=str(data.get("project_id") or uuid4()),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            source=dict(data.get("source") or {}),
            tracks=[Track.from_dict(t) for t in (data.get("tracks") or [])],
            transcription_defaults=dict(data.get("transcription_defaults") or {}),
            stages={k: StageRecord.from_dict(v) for k, v in stages_raw.items()},
            speaker_glyphs=dict(
                (data.get("speaker_glyphs") or (data.get("minimize") or {}).get("speaker_glyphs"))
                or DEFAULT_GLYPHS
            ),
            adapters=dict(
                data.get("adapters")
                or {
                    "media": "ffmpeg",
                    "asr": "mlx-whisper",
                    "diarization": "fluidaudio",
                }
            ),
            processing_mode=ProcessingMode(mode_raw),
            mix=MixRefs.from_dict(data.get("mix")),
        )


def canonical_plain_speaker(track_index: int) -> str:
    """Fixed plain-channel label: SPEAKER_T{track_index} (0-based)."""
    return f"SPEAKER_T{track_index}"


def track_scoped_speaker(track_index: int, speaker: str) -> str:
    """Map diarizer raw labels to SPEAKER_T{track}D{voice} (0-based indices)."""
    if _CANONICAL_DIAR_RE.match(speaker) or _CANONICAL_PLAIN_RE.match(speaker):
        return speaker
    legacy = _LEGACY_SCOPED_RE.match(speaker)
    if legacy:
        return f"SPEAKER_T{legacy.group(1)}D{int(legacy.group(2))}"
    diar = _DIAR_SPEAKER_RE.match(speaker)
    if diar:
        return f"SPEAKER_T{track_index}D{int(diar.group(1))}"
    if speaker.isdigit():
        return f"SPEAKER_T{track_index}D{int(speaker)}"
    return speaker


def short_speaker_id(canonical: str) -> str:
    """Short glyph id: SPEAKER_T0D1 → ST0D1, SPEAKER_T2 → ST2."""
    m = _CANONICAL_DIAR_RE.match(canonical)
    if m:
        return f"ST{m.group(1)}D{m.group(2)}"
    m = _CANONICAL_PLAIN_RE.match(canonical)
    if m:
        return f"ST{m.group(1)}"
    legacy = _LEGACY_SCOPED_RE.match(canonical)
    if legacy:
        return f"ST{legacy.group(1)}D{int(legacy.group(2))}"
    return canonical


def raw_speaker_label(speaker: str) -> str:
    m = _CANONICAL_DIAR_RE.match(speaker)
    if m:
        return f"SPEAKER_{int(m.group(2)):02d}"
    if "/" in speaker and speaker.startswith("T"):
        return speaker.split("/", 1)[1]
    return speaker


def stage_durations(project: Project) -> list[tuple[str, float]]:
    """Wall times for stages with both started_at and finished_at (succeeded/failed)."""
    rows: list[tuple[str, float]] = []
    for key in sorted(project.stages.keys()):
        rec = project.stages[key]
        if rec.status not in (StageStatus.SUCCEEDED, StageStatus.FAILED):
            continue
        if not rec.started_at or not rec.finished_at:
            continue
        try:
            start = datetime.fromisoformat(rec.started_at)
            end = datetime.fromisoformat(rec.finished_at)
        except ValueError:
            continue
        secs = (end - start).total_seconds()
        if secs >= 0:
            rows.append((key, secs))
    return rows


def format_stage_timings(project: Project) -> str:
    rows = stage_durations(project)
    if not rows:
        return ""
    lines = ["--- Timing ---"]
    total = 0.0
    for key, secs in rows:
        lines.append(f"{key}  {secs:.1f}s")
        total += secs
    lines.append(f"total  {total:.1f}s")
    return "\n".join(lines)
