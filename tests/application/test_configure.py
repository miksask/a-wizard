"""apply_configure invalidation without running media/ASR."""

from __future__ import annotations

from a_wizard.application.service import ServiceConfig, WizardService
from a_wizard.domain.dag import ActionKind, detect_next_action
from a_wizard.domain.models import ProcessingMode, Project, StageStatus, TrackMode, TrackStatus


def _finished_mixdown() -> Project:
    p = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=2,
        processing_mode=ProcessingMode.MIXDOWN,
    )
    p.transcription_defaults["language"] = "ru"
    p.transcription_defaults["initial_prompt"] = None
    p.transcription_defaults["initial_prompt_reviewed"] = True
    p.tracks[0].mode = TrackMode.PLAIN
    p.tracks[0].plain_speaker = "SPEAKER_T0"
    p.tracks[0].status = TrackStatus.TRANSCRIBED
    p.tracks[1].mode = TrackMode.SKIPPED
    p.tracks[1].status = TrackStatus.SKIPPED
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        p.stage(key).status = StageStatus.SUCCEEDED
    return p


def _svc() -> WizardService:
    return WizardService(config=ServiceConfig(use_mock_engines=True))


def test_apply_configure_language_stales_asr_keeps_extract():
    p = _finished_mixdown()
    result = _svc().apply_configure(
        p,
        language="en",
        initial_prompt=None,
        track_modes={0: "plain", 1: "skipped"},
    )
    assert result["changed"] is True
    assert p.transcription_defaults["language"] == "en"
    assert p.stage("transcribe:mix").status == StageStatus.STALE
    assert p.stage("attribute").status == StageStatus.STALE
    assert p.stage("extract").status == StageStatus.SUCCEEDED
    assert p.stage("mixdown").status == StageStatus.SUCCEEDED
    action = detect_next_action(p, hf_token_available=True)
    assert action.kind == ActionKind.TRANSCRIBE_MIX


def test_apply_configure_plain_to_diarized_keeps_mix_asr():
    p = _finished_mixdown()
    result = _svc().apply_configure(
        p,
        language="ru",
        initial_prompt=None,
        track_modes={0: "diarized", 1: "skipped"},
    )
    assert result["changed"] is True
    assert p.tracks[0].mode == TrackMode.DIARIZED
    assert p.stage("transcribe:mix").status == StageStatus.SUCCEEDED
    assert p.stage("attribute").status == StageStatus.STALE
    assert p.stage("merge").status == StageStatus.STALE


def test_apply_configure_noop_leaves_stages():
    p = _finished_mixdown()
    result = _svc().apply_configure(
        p,
        language="ru",
        initial_prompt=None,
        track_modes={0: "plain", 1: "skipped"},
    )
    assert result["changed"] is False
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        assert p.stage(key).status == StageStatus.SUCCEEDED
    action = detect_next_action(p, hf_token_available=True)
    assert action.kind == ActionKind.DONE
