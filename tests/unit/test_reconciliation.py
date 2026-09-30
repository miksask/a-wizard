"""Tests for stage reconciliation freshness."""

from __future__ import annotations

from pathlib import Path

from a_wizard.adapters.persistence.store import FsArtifactStore, YamlProjectRepository
from a_wizard.application.reconciliation import apply_adapter_identity, reconcile_project
from a_wizard.domain.dag import ActionKind, detect_next_action
from a_wizard.domain.models import ProcessingMode, Project, StageStatus, TrackMode, TrackStatus


def _completed_mixdown(project_dir: Path) -> Project:
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("tracks", "transcripts", "dialog", "meta"):
        (project_dir / sub).mkdir(exist_ok=True)
    store = FsArtifactStore()
    p = Project.new(
        source_path=str(project_dir / "missing.mkv"),
        basename="missing.mkv",
        audio_stream_count=2,
        processing_mode=ProcessingMode.MIXDOWN,
        fingerprint="sha256:deadbeef",
    )
    p.transcription_defaults["initial_prompt_reviewed"] = True
    p.tracks[0].mode = TrackMode.PLAIN
    p.tracks[0].plain_speaker = "SPEAKER_T0"
    p.tracks[0].status = TrackStatus.TRANSCRIBED
    p.tracks[1].mode = TrackMode.DIARIZED
    p.tracks[1].status = TrackStatus.TRANSCRIBED

    digests: dict[str, dict[str, str]] = {}
    for i in range(2):
        rel = f"tracks/track_{i}.wav"
        digests.setdefault("extract", {})[rel] = store.write_bytes(
            project_dir, rel, b"RIFF" + bytes(i)
        )
    digests["mixdown"] = {
        p.mix.wav: store.write_bytes(project_dir, p.mix.wav, b"mix-bytes")
    }
    digests["transcribe:mix"] = {
        "transcripts/mix.raw.json": store.write_json(
            project_dir,
            "transcripts/mix.raw.json",
            {"segments": [], "words": [{"start_ms": 0, "end_ms": 10, "text": "hi"}]},
        )
    }
    digests["attribute"] = {
        p.mix.segments: store.write_json(
            project_dir,
            p.mix.segments,
            {
                "segments": [
                    {"start_ms": 0, "end_ms": 10, "text": "hi", "speaker": "SPEAKER_T0"}
                ],
                "words": [],
            },
        ),
        p.mix.transcript_txt: store.write_text(project_dir, p.mix.transcript_txt, "hi\n"),
        p.mix.attribution: store.write_json(project_dir, p.mix.attribution, {"ok": True}),
    }
    digests["merge"] = {
        "dialog/dialog.json": store.write_json(
            project_dir,
            "dialog/dialog.json",
            [{"start_ms": 0, "end_ms": 10, "text": "hi", "speaker": "SPEAKER_T0"}],
        ),
        "dialog/dialog.txt": store.write_text(project_dir, "dialog/dialog.txt", "hi\n"),
    }
    digests["minimize"] = {
        "dialog/dialog.minimize.txt": store.write_text(
            project_dir, "dialog/dialog.minimize.txt", "ST0: SPEAKER_T0\n\nST0: hi\n"
        ),
        "dialog/dialog.minimize.ts.txt": store.write_text(
            project_dir,
            "dialog/dialog.minimize.ts.txt",
            "ST0: SPEAKER_T0\n\n[00:00:00.000] ST0: hi\n",
        ),
        "dialog/transcript.txt": store.write_text(
            project_dir, "dialog/transcript.txt", "ST0: SPEAKER_T0\n\nST0: hi\n"
        ),
    }
    for key, d in digests.items():
        rec = p.stage(key)
        rec.status = StageStatus.SUCCEEDED
        rec.output_digests = d
        # signatures filled by reconcile backfill or left empty
    YamlProjectRepository().save(project_dir, p)
    return YamlProjectRepository().load(project_dir)


def test_reconcile_missing_artifact_stales(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    p = _completed_mixdown(project_dir)
    (project_dir / "transcripts" / "mix.raw.json").unlink()
    result = reconcile_project(project_dir, p, refresh_fingerprint=False)
    assert result.changed
    assert p.stage("transcribe:mix").status == StageStatus.STALE
    assert p.stage("attribute").status == StageStatus.STALE
    action = detect_next_action(p, hf_token_available=True)
    assert action.kind == ActionKind.TRANSCRIBE_MIX


def test_reconcile_digest_mismatch_stales(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    p = _completed_mixdown(project_dir)
    (project_dir / "tracks" / "mix.wav").write_bytes(b"tampered")
    result = reconcile_project(project_dir, p, refresh_fingerprint=False)
    assert result.changed
    assert p.stage("mixdown").status == StageStatus.STALE
    assert "mixdown" in result.reasons


def test_reconcile_noop_idempotent(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    p = _completed_mixdown(project_dir)
    reconcile_project(project_dir, p, refresh_fingerprint=False)
    YamlProjectRepository().save(project_dir, p)
    p2 = YamlProjectRepository().load(project_dir)
    before = (project_dir / "manifest.yaml").read_bytes()
    r2 = reconcile_project(project_dir, p2, refresh_fingerprint=False)
    assert r2.changed is False
    assert r2.invalidated == []
    assert detect_next_action(p2, hf_token_available=True).kind == ActionKind.DONE
    assert (project_dir / "manifest.yaml").read_bytes() == before


def test_legacy_digest_aliases(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    p = _completed_mixdown(project_dir)
    # rewrite mixdown digests to legacy semantic key
    p.stage("mixdown").output_digests = {"mix": p.stage("mixdown").output_digests[p.mix.wav]}
    result = reconcile_project(project_dir, p, refresh_fingerprint=False)
    assert p.stage("mixdown").status == StageStatus.SUCCEEDED
    assert "mixdown" not in result.reasons


def test_adapter_identity_invalidation():
    p = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=1,
        processing_mode=ProcessingMode.MIXDOWN,
    )
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        p.stage(key).status = StageStatus.SUCCEEDED
    p.adapters["asr"] = "mock-asr"
    p.adapters["diarization"] = "mock-diar"
    keys = apply_adapter_identity(p, asr_id="mlx-whisper", diar_id="mock-diar")
    assert "transcribe:mix" in keys
    assert p.stage("transcribe:mix").status == StageStatus.STALE
    assert p.stage("extract").status == StageStatus.SUCCEEDED

    p2 = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=1,
        processing_mode=ProcessingMode.MIXDOWN,
    )
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        p2.stage(key).status = StageStatus.SUCCEEDED
    p2.adapters["asr"] = "mock-asr"
    p2.adapters["diarization"] = "mock-diar"
    keys2 = apply_adapter_identity(p2, asr_id="mock-asr", diar_id="sherpa-onnx")
    assert "attribute" in keys2
    assert p2.stage("transcribe:mix").status == StageStatus.SUCCEEDED
    assert p2.stage("attribute").status == StageStatus.STALE
