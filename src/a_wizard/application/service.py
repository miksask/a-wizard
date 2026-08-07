"""Core orchestration service for a-wizard."""

from __future__ import annotations

import json
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from a_wizard.adapters.asr.engines import resolve_asr_adapter
from a_wizard.adapters.diarization.engines import resolve_diar_adapter
from a_wizard.adapters.media.ffmpeg import FfmpegMediaAdapter
from a_wizard.adapters.persistence import (
    FileProjectLock,
    FsArtifactStore,
    JsonlRunObserver,
    YamlProjectRepository,
    project_dir_for_video,
)
from a_wizard.application.attribution import (
    assign_speakers_by_turns,
    attribute_words,
    load_or_compute_profiles,
    words_to_segments,
)
from a_wizard.application.dialog import (
    apply_speaker_map,
    default_speaker_glyph,
    merge_by_time,
    minimize_segments,
    safe_filename,
    segs_to_txt,
)
from a_wizard.domain.dag import ActionKind, NextAction, describe_action, detect_next_action
from a_wizard.domain.errors import AppError, BlockedError, ExitCode, UsageError
from a_wizard.domain.freshness import (
    attribute_signature,
    extract_signature,
    mark_stale_downstream,
    merge_signature,
    minimize_signature,
    mix_transcribe_signature,
    mixdown_signature,
    track_asr_config,
    transcribe_signature,
)
from a_wizard.domain.models import (
    VIDEO_SUFFIXES,
    ProcessingMode,
    Project,
    Segment,
    SpeakerTurn,
    StageStatus,
    TrackMode,
    TrackStatus,
    TranscriptResult,
    Word,
    canonical_plain_speaker,
    format_stage_timings,
    track_scoped_speaker,
    utc_now_iso,
)


def hf_token_available() -> bool:
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"))


def resolve_target(path: str | Path) -> tuple[Path | None, Path | None, bool]:
    """Return (project_dir, video_path, needs_init)."""
    p = Path(path).resolve()
    if p.is_dir() and (p / "manifest.yaml").is_file():
        return p, None, False
    if p.is_file() and p.name == "manifest.yaml":
        return p.parent, None, False
    if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES:
        project_dir = project_dir_for_video(p)
        if (project_dir / "manifest.yaml").is_file():
            return project_dir, p, False
        return project_dir, p, True
    raise UsageError(
        f"Not a video file or a-wizard project: {p}",
        code="target_invalid",
        next_step="pass .mkv/.mp4 or a .project directory",
    )


@dataclass
class ServiceConfig:
    asr_adapter: str = "auto"
    diar_adapter: str = "auto"
    media_adapter: str = "ffmpeg"
    use_mock_engines: bool = False
    processing_mode: ProcessingMode = ProcessingMode.MIXDOWN


class WizardService:
    def __init__(
        self,
        *,
        config: ServiceConfig | None = None,
        asr: Any | None = None,
        diar: Any | None = None,
        media: Any | None = None,
    ) -> None:
        self.config = config or ServiceConfig()
        self.repo = YamlProjectRepository()
        self.store = FsArtifactStore()
        self.lock = FileProjectLock()
        self.media = media or FfmpegMediaAdapter()
        if asr is not None:
            self.asr = asr
        elif self.config.use_mock_engines or self.config.asr_adapter in ("mock", "mock-asr"):
            self.asr = resolve_asr_adapter("mock-asr")
        else:
            self.asr = resolve_asr_adapter(self.config.asr_adapter)
        if diar is not None:
            self.diar = diar
        elif self.config.use_mock_engines or self.config.diar_adapter in ("mock", "mock-diar"):
            self.diar = resolve_diar_adapter("mock-diar")
        else:
            self.diar = resolve_diar_adapter(self.config.diar_adapter)
        self._interrupted = False

    def _setup_sigint(self, on_interrupt: Callable[[], None] | None = None) -> None:
        def handler(signum: int, frame: object) -> None:
            self._interrupted = True
            if on_interrupt:
                on_interrupt()
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handler)

    def _hf_ok(self) -> bool:
        if getattr(self.diar, "adapter_id", "") == "mock-diar":
            return True
        if getattr(self.diar, "adapter_id", "") != "pyannote-community-1":
            return True
        return hf_token_available()

    def init_project(
        self,
        video: Path,
        *,
        force: bool = False,
        processing_mode: ProcessingMode | None = None,
    ) -> Path:
        video = video.resolve()
        project_dir = project_dir_for_video(video)
        if self.repo.exists(project_dir) and not force:
            return project_dir
        meta = self.media.probe(video)
        if int(meta["audio_stream_count"]) == 0:
            raise UsageError(f"No audio streams in {video}", code="no_audio")
        for sub in ("tracks", "transcripts", "dialog", "meta", "logs"):
            (project_dir / sub).mkdir(parents=True, exist_ok=True)
        self.store.write_json(project_dir, "meta/source.json", meta)
        mode = processing_mode or self.config.processing_mode
        project = Project.new(
            source_path=str(video),
            basename=video.name,
            audio_stream_count=int(meta["audio_stream_count"]),
            duration_ms=meta.get("duration_ms"),
            fingerprint=meta.get("content_fingerprint"),
            processing_mode=mode,
        )
        project.adapters["asr"] = getattr(self.asr, "adapter_id", self.config.asr_adapter)
        project.adapters["diarization"] = getattr(self.diar, "adapter_id", self.config.diar_adapter)
        project.adapters["media"] = getattr(self.media, "adapter_id", "ffmpeg")
        self.repo.save(project_dir, project)
        return project_dir

    def load(self, project_dir: Path) -> Project:
        return self.repo.load(project_dir)

    def status_text(self, project_dir: Path, project: Project) -> str:
        lines = [
            f"Project: {project_dir}",
            f"Video:   {project.source.get('path', '?')}",
            f"Mode:    {project.processing_mode.value}",
            "",
        ]
        extract_ok = project.stage("extract").status == StageStatus.SUCCEEDED
        lines.append(f"[{'x' if extract_ok else ' '}] Extract tracks")
        if project.processing_mode == ProcessingMode.MIXDOWN:
            mix_ok = project.stage("mixdown").status == StageStatus.SUCCEEDED
            asr_ok = project.stage("transcribe:mix").status == StageStatus.SUCCEEDED
            attr_ok = project.stage("attribute").status == StageStatus.SUCCEEDED
            lines.append(f"[{'x' if mix_ok else ' '}] Mixdown")
            lines.append(f"[{'x' if asr_ok else ' '}] Transcribe mix")
            lines.append(f"[{'x' if attr_ok else ' '}] Attribute speakers")
        for t in project.tracks:
            done = t.is_merge_ready()
            extra = f" ({t.skip_reason})" if t.mode == TrackMode.SKIPPED and t.skip_reason else ""
            lines.append(
                f"[{'x' if done else ' '}] Track {t.index}: mode={t.mode.value}, "
                f"status={t.status.value}{extra}"
            )
        merge_ok = project.stage("merge").status == StageStatus.SUCCEEDED
        min_ok = project.stage("minimize").status == StageStatus.SUCCEEDED
        lines.append(f"[{'x' if merge_ok else ' '}] Merge dialog")
        lines.append(f"[{'x' if min_ok else ' '}] Minimize")
        action = detect_next_action(project, hf_token_available=self._hf_ok())
        lines.append("\n--- Next ---")
        lines.append(describe_action(action))
        if min_ok:
            lines.append(f"\nMinimized dialog: {project_dir / 'dialog' / 'dialog.minimize.txt'}")
        timings = format_stage_timings(project)
        if timings:
            lines.append("")
            lines.append(timings)
        return "\n".join(lines)

    def plan_dict(self, project: Project) -> dict[str, Any]:
        action = detect_next_action(project, hf_token_available=self._hf_ok())
        stages = [
            {
                "key": "extract",
                "status": project.stage("extract").status.value,
                "signature": project.stage("extract").signature,
            }
        ]
        if project.processing_mode == ProcessingMode.MIXDOWN:
            for key in ("mixdown", "transcribe:mix", "attribute"):
                stages.append({"key": key, "status": project.stage(key).status.value})
        else:
            for t in project.tracks:
                stages.append(
                    {
                        "key": f"transcribe:{t.index}",
                        "status": (
                            "succeeded"
                            if t.status == TrackStatus.TRANSCRIBED
                            else ("skipped" if t.mode == TrackMode.SKIPPED else "pending")
                        ),
                        "mode": t.mode.value,
                    }
                )
        stages.append({"key": "merge", "status": project.stage("merge").status.value})
        stages.append({"key": "minimize", "status": project.stage("minimize").status.value})
        return {
            "processing_mode": project.processing_mode.value,
            "next": {
                "kind": action.kind.value,
                "track_index": action.track_index,
                "reason": action.reason,
            },
            "stages": stages,
        }

    def apply_preset(self, project: Project, preset: str) -> None:
        if preset != "obs-interview":
            raise UsageError(f"unknown preset: {preset}", code="unknown_preset")
        for t in project.tracks:
            if t.mode != TrackMode.PENDING:
                continue
            if t.index == 0:
                t.mode = TrackMode.PLAIN
                t.plain_speaker = canonical_plain_speaker(t.index)
                if t.status == TrackStatus.PENDING:
                    t.status = TrackStatus.EXTRACTED
            else:
                t.mode = TrackMode.DIARIZED
                t.plain_speaker = None
                if t.status == TrackStatus.PENDING:
                    t.status = TrackStatus.EXTRACTED
        project.transcription_defaults["initial_prompt_reviewed"] = True

    def set_track_mode(
        self,
        project: Project,
        track_index: int,
        *,
        mode: str,
        speaker: str | None = None,
        language: str | None = None,
        reason: str | None = None,
        initial_prompt: Any = ...,
    ) -> None:
        track = project.get_track(track_index)
        prev_mode = track.mode
        m = TrackMode(mode)
        track.mode = m
        # Language is project-level; keep track.language in sync for legacy manifests only.
        defaults = project.transcription_defaults or {}
        track.language = language or defaults.get("language", "ru")
        if m == TrackMode.PLAIN:
            track.plain_speaker = speaker or canonical_plain_speaker(track_index)
            track.skip_reason = None
            if track.status in (TrackStatus.TRANSCRIBED, TrackStatus.SKIPPED):
                track.status = TrackStatus.EXTRACTED
            if prev_mode == TrackMode.SKIPPED:
                mark_stale_downstream(project, "skipped_set")
            else:
                mark_stale_downstream(project, f"track:{track_index}")
        elif m == TrackMode.DIARIZED:
            track.plain_speaker = None
            track.skip_reason = None
            if track.status in (TrackStatus.TRANSCRIBED, TrackStatus.SKIPPED):
                track.status = TrackStatus.EXTRACTED
            if prev_mode == TrackMode.SKIPPED:
                mark_stale_downstream(project, "skipped_set")
            else:
                mark_stale_downstream(project, f"track:{track_index}")
        elif m == TrackMode.SKIPPED:
            track.status = TrackStatus.SKIPPED
            track.plain_speaker = None
            track.skip_reason = reason
            mark_stale_downstream(project, "skipped_set")
        else:
            track.status = TrackStatus.PENDING
            mark_stale_downstream(project, f"track:{track_index}")
        # Track-level prompt overrides are ignored for ASR; accept but do not require.
        if initial_prompt is not ...:
            track.initial_prompt = initial_prompt

    def map_speakers(
        self,
        project: Project,
        track_index: int,
        mapping: dict[str, str],
        *,
        reviewed: bool = True,
    ) -> None:
        track = project.get_track(track_index)
        track.speaker_map.update(mapping)
        track.speaker_map_reviewed = reviewed
        for role in mapping.values():
            if role not in project.speaker_glyphs:
                used = set(project.speaker_glyphs.values())
                project.speaker_glyphs[role] = default_speaker_glyph(role, len(used), used)
        mark_stale_downstream(project, f"speakers:{track_index}")

    def _begin_stage(self, project: Project, key: str, signature: str, adapter_id: str) -> None:
        rec = project.stage(key)
        rec.status = StageStatus.RUNNING
        rec.attempt_id = str(uuid4())
        rec.started_at = utc_now_iso()
        rec.finished_at = None
        rec.signature = signature
        rec.adapter_id = adapter_id
        rec.error_code = None
        rec.error_message = None

    def _succeed_stage(
        self, project: Project, key: str, digests: dict[str, str] | None = None
    ) -> None:
        rec = project.stage(key)
        rec.status = StageStatus.SUCCEEDED
        rec.finished_at = utc_now_iso()
        if digests:
            rec.output_digests = digests

    def _fail_stage(self, project: Project, key: str, err: Exception) -> None:
        rec = project.stage(key)
        rec.status = StageStatus.FAILED
        rec.finished_at = utc_now_iso()
        if isinstance(err, AppError):
            rec.error_code = err.code
            rec.error_message = err.message
        else:
            rec.error_code = "internal"
            rec.error_message = str(err)

    def run_extract(self, project_dir: Path, project: Project, *, force: bool = False) -> None:
        video = Path(project.source["path"])
        sig = extract_signature(project)
        self._begin_stage(project, "extract", sig, getattr(self.media, "adapter_id", "ffmpeg"))
        self.repo.save(project_dir, project)
        try:
            paths = self.media.extract_all(video, project_dir, force=force)
            digests = {}
            for i, p in enumerate(paths):
                digests[f"track_{i}"] = self.store.digest(project_dir, f"tracks/track_{i}.wav")
                t = project.get_track(i)
                t.wav = f"tracks/track_{i}.wav"
                if t.status == TrackStatus.PENDING:
                    t.status = TrackStatus.EXTRACTED
            self._succeed_stage(project, "extract", digests)
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, "extract", e)
            self.repo.save(project_dir, project)
            raise

    def run_mixdown(self, project_dir: Path, project: Project, *, force: bool = False) -> None:
        active = [t for t in project.tracks if t.mode != TrackMode.SKIPPED]
        if not active:
            raise UsageError("No non-skipped tracks to mix", code="mixdown_empty")
        # pending modes still included until configured; after configure only plain/diarized
        wavs = []
        for t in project.tracks:
            if t.mode == TrackMode.SKIPPED:
                continue
            if t.mode == TrackMode.PENDING:
                raise UsageError(
                    f"track {t.index} still pending; configure modes before mixdown",
                    code="track_pending",
                )
            path = project_dir / t.wav
            if not path.is_file():
                raise UsageError(f"WAV missing: {path}", code="wav_missing")
            wavs.append(path)
        sig = mixdown_signature(project)
        self._begin_stage(project, "mixdown", sig, getattr(self.media, "adapter_id", "ffmpeg"))
        self.repo.save(project_dir, project)
        try:
            out = project_dir / project.mix.wav
            self.media.mixdown(wavs, out, force=force or True)
            digest = self.store.digest(project_dir, project.mix.wav)
            self._succeed_stage(project, "mixdown", {"mix": digest})
            mark_stale_downstream(project, "transcribe:mix")
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, "mixdown", e)
            self.repo.save(project_dir, project)
            raise

    def run_transcribe_mix(self, project_dir: Path, project: Project) -> None:
        wav = project_dir / project.mix.wav
        if not wav.is_file():
            raise UsageError("mix.wav missing; run mixdown first", code="mix_missing")
        defaults = project.transcription_defaults or {}
        key = "transcribe:mix"
        sig = mix_transcribe_signature(project)
        self._begin_stage(project, key, sig, getattr(self.asr, "adapter_id", "asr"))
        self.repo.save(project_dir, project)
        try:
            result: TranscriptResult = self.asr.transcribe(
                wav,
                speaker=None,
                model=defaults.get("model", "large-v3"),
                language=defaults.get("language", "ru"),
                compute_type=defaults.get("compute_type", "int8"),
                device=defaults.get("device", "auto"),
                initial_prompt=defaults.get("initial_prompt"),
            )
            # Store raw ASR before attribution
            payload = {
                "segments": [s.to_dict() for s in result.segments],
                "words": [w.to_dict() for w in result.words],
            }
            d1 = self.store.write_json(project_dir, "transcripts/mix.raw.json", payload)
            self._succeed_stage(project, key, {"raw": d1})
            mark_stale_downstream(project, "attribute")
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, key, e)
            self.repo.save(project_dir, project)
            raise

    def run_attribute(self, project_dir: Path, project: Project) -> None:
        raw_path = project_dir / "transcripts" / "mix.raw.json"
        if not raw_path.is_file():
            raise UsageError("mix.raw.json missing; run transcribe:mix first", code="asr_missing")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        words = [Word.from_dict(w) for w in raw.get("words") or []]
        if not words:
            words = [
                Word(s["start_ms"], s["end_ms"], s["text"])
                for s in raw.get("segments") or []
                if s.get("text")
            ]

        key = "attribute"
        sig = attribute_signature(project)
        self._begin_stage(
            project, key, sig, getattr(self.diar, "adapter_id", "diar")
        )
        self.repo.save(project_dir, project)
        try:
            profiles = load_or_compute_profiles(project_dir, project.tracks)
            channel_turns: dict[int, list[SpeakerTurn]] = {}
            for t in project.tracks:
                if t.mode != TrackMode.DIARIZED:
                    continue
                turns = self.diar.diarize(project_dir / t.wav)
                channel_turns[t.index] = turns
                # cache turns
                self.store.write_json(
                    project_dir,
                    f"meta/diar/track_{t.index}.json",
                    [tr.to_dict() for tr in turns],
                )

            result = attribute_words(words, project.tracks, profiles, channel_turns)
            payload = {
                "segments": [s.to_dict() for s in result.segments],
                "words": [w.to_dict() for w in result.words],
            }
            d1 = self.store.write_json(project_dir, project.mix.segments, payload)
            d2 = self.store.write_text(
                project_dir, project.mix.transcript_txt, segs_to_txt(result.segments)
            )
            d3 = self.store.write_json(project_dir, project.mix.attribution, result.report)
            for t in project.tracks:
                if t.mode in (TrackMode.PLAIN, TrackMode.DIARIZED):
                    t.status = TrackStatus.TRANSCRIBED
            mark_stale_downstream(project, "merge")
            self._succeed_stage(project, key, {"segments": d1, "txt": d2, "report": d3})
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, key, e)
            self.repo.save(project_dir, project)
            raise

    def run_transcribe(self, project_dir: Path, project: Project, track_index: int) -> None:
        track = project.get_track(track_index)
        wav = project_dir / track.wav
        if not wav.is_file():
            raise UsageError(
                f"WAV not found: {wav}. Run extract first.",
                code="wav_missing",
                next_step="a-wizard stage run --project ... --stage extract",
            )
        opts = track_asr_config(project, track)
        key = f"transcribe:{track_index}"
        sig = transcribe_signature(project, track)
        adapter_id = getattr(self.asr, "adapter_id", "asr")
        self._begin_stage(project, key, sig, adapter_id)
        self.repo.save(project_dir, project)
        try:
            if track.mode == TrackMode.PLAIN:
                result = self.asr.transcribe(
                    wav,
                    speaker=track.plain_speaker,
                    model=opts["model"],
                    language=opts["language"],
                    compute_type=opts["compute_type"],
                    device=opts["device"],
                    initial_prompt=opts.get("initial_prompt"),
                )
                segs = [
                    Segment(
                        s.start_ms,
                        s.end_ms,
                        s.text,
                        track.plain_speaker or canonical_plain_speaker(track_index),
                    )
                    for s in result.segments
                ]
            elif track.mode == TrackMode.DIARIZED:
                result = self.asr.transcribe(
                    wav,
                    speaker=None,
                    model=opts["model"],
                    language=opts["language"],
                    compute_type=opts["compute_type"],
                    device=opts["device"],
                    initial_prompt=opts.get("initial_prompt"),
                )
                turns = self.diar.diarize(wav)
                words = assign_speakers_by_turns(result.words, turns, track_index=track_index)
                segs = words_to_segments(words)
                if not segs and result.segments:
                    # fallback: assign by segment midpoint
                    segs = []
                    for s in result.segments:
                        mid = (s.start_ms + s.end_ms) // 2
                        raw = "SPEAKER_00"
                        for tr in turns:
                            if tr.start_ms <= mid < tr.end_ms:
                                raw = tr.speaker
                                break
                        segs.append(
                            Segment(
                                s.start_ms,
                                s.end_ms,
                                s.text,
                                track_scoped_speaker(track_index, raw),
                            )
                        )
            else:
                raise UsageError(
                    f"track {track_index} mode {track.mode.value} cannot be transcribed",
                    code="bad_mode",
                )

            payload = [s.to_dict() for s in segs]
            d1 = self.store.write_json(project_dir, track.segments, payload)
            d2 = self.store.write_text(project_dir, track.transcript_txt, segs_to_txt(segs))
            track.status = TrackStatus.TRANSCRIBED
            mark_stale_downstream(project, "merge")
            self._succeed_stage(project, key, {"segments": d1, "txt": d2})
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, key, e)
            self.repo.save(project_dir, project)
            raise

    def run_merge(self, project_dir: Path, project: Project, *, allow_raw_speakers: bool = False) -> None:
        if project.processing_mode == ProcessingMode.MIXDOWN:
            if project.stage("attribute").status != StageStatus.SUCCEEDED:
                raise UsageError("Attribute not done", code="attribute_required")
        elif not all(t.is_merge_ready() for t in project.tracks):
            raise UsageError(
                "Not all tracks are transcribed or skipped",
                code="tracks_incomplete",
            )
        # Fixed SPEAKER_Tn / SPEAKER_TnDm labels are merge-ready; optional legacy
        # speaker_map still applied when present. allow_raw_speakers kept for CLI compat.
        _ = allow_raw_speakers
        sig = merge_signature(project)
        self._begin_stage(project, "merge", sig, "merge-v1")
        self.repo.save(project_dir, project)
        try:
            if project.processing_mode == ProcessingMode.MIXDOWN:
                raw = json.loads(self.store.read_text(project_dir, project.mix.segments))
                segs = [Segment.from_dict(x) for x in raw.get("segments") or raw]
                # apply legacy speaker maps from diarized tracks if any
                maps: dict[str, str] = {}
                for t in project.tracks:
                    if t.mode == TrackMode.DIARIZED and t.speaker_map:
                        maps.update(t.speaker_map)
                if maps:
                    segs = apply_speaker_map(segs, maps)
                merged = segs
            else:
                lists: list[list[Segment]] = []
                for t in project.tracks:
                    if t.mode == TrackMode.SKIPPED:
                        continue
                    raw = json.loads(self.store.read_text(project_dir, t.segments))
                    segs = [Segment.from_dict(x) for x in raw]
                    if t.mode == TrackMode.PLAIN:
                        spk = t.plain_speaker or canonical_plain_speaker(t.index)
                        segs = [Segment(s.start_ms, s.end_ms, s.text, spk) for s in segs]
                    elif t.speaker_map:
                        segs = apply_speaker_map(segs, t.speaker_map)
                    lists.append(segs)
                merged = merge_by_time(*lists) if lists else []
            payload = [s.to_dict() for s in merged]
            d_json = self.store.write_json(project_dir, "dialog/dialog.json", payload)
            d_txt = self.store.write_text(project_dir, "dialog/dialog.txt", segs_to_txt(merged))
            by_spk: dict[str, list[Segment]] = {}
            for s in merged:
                by_spk.setdefault(s.speaker, []).append(s)
            for spk, spk_segs in by_spk.items():
                self.store.write_text(
                    project_dir,
                    f"dialog/spk_{safe_filename(spk)}.txt",
                    segs_to_txt(spk_segs),
                )
            self._succeed_stage(project, "merge", {"dialog_json": d_json, "dialog_txt": d_txt})
            project.stage("minimize").status = StageStatus.STALE
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, "merge", e)
            self.repo.save(project_dir, project)
            raise

    def run_minimize(self, project_dir: Path, project: Project) -> None:
        if project.stage("merge").status != StageStatus.SUCCEEDED:
            raise UsageError("Merge not done", code="merge_required")
        sig = minimize_signature(project)
        self._begin_stage(project, "minimize", sig, "minimize-v1")
        self.repo.save(project_dir, project)
        try:
            raw = json.loads(self.store.read_text(project_dir, "dialog/dialog.json"))
            segs = [Segment.from_dict(x) for x in raw]
            text = minimize_segments(segs, project.speaker_glyphs)
            digest = self.store.write_text(project_dir, "dialog/dialog.minimize.txt", text)
            self._succeed_stage(project, "minimize", {"minimize": digest})
            self.repo.save(project_dir, project)
        except Exception as e:
            self._fail_stage(project, "minimize", e)
            self.repo.save(project_dir, project)
            raise

    def run_action(
        self,
        project_dir: Path,
        project: Project,
        action: NextAction,
        *,
        allow_raw_speakers: bool = False,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            return
        if action.kind == ActionKind.EXTRACT:
            self.run_extract(project_dir, project)
        elif action.kind == ActionKind.MIXDOWN:
            self.run_mixdown(project_dir, project)
        elif action.kind == ActionKind.TRANSCRIBE_MIX:
            self.run_transcribe_mix(project_dir, project)
        elif action.kind == ActionKind.ATTRIBUTE:
            self.run_attribute(project_dir, project)
        elif action.kind == ActionKind.TRANSCRIBE:
            assert action.track_index is not None
            self.run_transcribe(project_dir, project, action.track_index)
        elif action.kind == ActionKind.MERGE:
            self.run_merge(project_dir, project, allow_raw_speakers=allow_raw_speakers)
        elif action.kind == ActionKind.MINIMIZE:
            self.run_minimize(project_dir, project)
        elif action.kind == ActionKind.NEED_HF_TOKEN:
            raise BlockedError(
                "The pyannote-community-1 adapter requires a Hugging Face token. "
                "export HF_TOKEN=...",
                code="hf_token_missing",
                next_step="export HF_TOKEN=hf_... then re-run",
            )
        else:
            raise UsageError(
                f"action {action.kind.value} requires interactive handling",
                code="interactive_required",
            )

    def run_until_blocked(
        self,
        target: str | Path,
        *,
        preset: str | None = None,
        allow_raw_speakers: bool = False,
        dry_run: bool = False,
        status_only: bool = False,
        processing_mode: ProcessingMode | None = None,
        interactive_handler: Callable[[Path, Project, NextAction], bool] | None = None,
        print_fn: Callable[[str], None] | None = None,
    ) -> int:
        out = print_fn or (lambda s: None)
        project_dir, video, needs_init = resolve_target(target)
        assert project_dir is not None

        def on_interrupt() -> None:
            out("\nInterrupted.")
            out(f"Resume: a-wizard run {target}")

        self._setup_sigint(on_interrupt)

        try:
            self.lock.acquire(project_dir)
        except Exception:
            raise

        observer = JsonlRunObserver(project_dir if self.repo.exists(project_dir) else None)
        try:
            if needs_init:
                if dry_run:
                    out("[dry-run] Would initialize project")
                    return ExitCode.SUCCESS
                assert video is not None
                out(f"Initializing project for {video}")
                project_dir = self.init_project(video, processing_mode=processing_mode)
                observer = JsonlRunObserver(project_dir)
                observer.event("init", video=str(video))

            project = self.repo.load(project_dir)
            out(self.status_text(project_dir, project))
            if status_only:
                return ExitCode.SUCCESS

            if preset:
                self.apply_preset(project, preset)
                self.repo.save(project_dir, project)

            skip_interactive = preset is not None and interactive_handler is None

            while True:
                action = detect_next_action(
                    project,
                    hf_token_available=self._hf_ok(),
                    allow_raw_speakers=allow_raw_speakers,
                    skip_interactive=skip_interactive,
                )
                if action.kind == ActionKind.DONE:
                    out(self.status_text(project_dir, project))
                    out("Done.")
                    return ExitCode.SUCCESS

                out(f"\n>> {describe_action(action)}")
                if dry_run:
                    out(f"[dry-run] Would run: {action.kind.value}")
                    return ExitCode.SUCCESS

                if action.interactive:
                    if interactive_handler and interactive_handler(project_dir, project, action):
                        project = self.repo.load(project_dir)
                        continue
                    if action.kind == ActionKind.NEED_HF_TOKEN:
                        self.run_action(project_dir, project, action)
                    raise BlockedError(
                        f"Interactive step required: {describe_action(action)}",
                        code="human_gate",
                        next_step="run without --preset or complete the step interactively",
                    )

                observer.event("stage_start", kind=action.kind.value, track=action.track_index)
                self.run_action(
                    project_dir,
                    project,
                    action,
                    allow_raw_speakers=allow_raw_speakers,
                )
                project = self.repo.load(project_dir)
                observer.event("stage_done", kind=action.kind.value)
        except KeyboardInterrupt:
            return ExitCode.INTERRUPTED
        finally:
            self.lock.release(project_dir)
