"""apply_configure invalidation without running media/ASR."""

from __future__ import annotations

import pytest

from a_wizard.application.service import ServiceConfig, WizardService
from a_wizard.domain.dag import ActionKind, detect_next_action
from a_wizard.domain.errors import UsageError
from a_wizard.domain.languages import stored_language
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


def _configure(p: Project, language: str):
    return _svc().apply_configure(
        p,
        language=language,
        initial_prompt=None,
        track_modes={0: "plain", 1: "skipped"},
    )


def test_apply_configure_other_language_normalized_and_stales_asr():
    p = _finished_mixdown()
    result = _configure(p, "German")
    assert result["changed"] is True
    assert result["language"] == "de"
    assert p.transcription_defaults["language"] == "de"
    assert p.tracks[0].language == "de"
    assert p.stage("transcribe:mix").status == StageStatus.STALE
    assert p.stage("extract").status == StageStatus.SUCCEEDED
    assert p.stage("mixdown").status == StageStatus.SUCCEEDED


def test_apply_configure_same_language_other_spelling_is_noop():
    p = _finished_mixdown()
    _configure(p, "de")
    for key in ("transcribe:mix", "attribute", "merge", "minimize"):
        p.stage(key).status = StageStatus.SUCCEEDED
    for spelling in ("De", "German", " german ", "немецкий"):
        result = _configure(p, spelling)
        assert result["changed"] is False
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        assert p.stage(key).status == StageStatus.SUCCEEDED
    assert detect_next_action(p, hf_token_available=True).kind == ActionKind.DONE


def test_apply_configure_auto_roundtrip_stales_asr():
    p = _finished_mixdown()
    assert _configure(p, "auto")["changed"] is True
    assert p.transcription_defaults["language"] == "auto"
    assert p.stage("transcribe:mix").status == StageStatus.STALE
    p.stage("transcribe:mix").status = StageStatus.SUCCEEDED
    assert _configure(p, "ru")["changed"] is True
    assert p.stage("transcribe:mix").status == StageStatus.STALE


def test_apply_configure_unsupported_language_leaves_project_untouched():
    p = _finished_mixdown()
    with pytest.raises(UsageError) as exc:
        _configure(p, "klingon")
    assert exc.value.code == "bad_language"
    assert p.transcription_defaults["language"] == "ru"
    assert p.stage("transcribe:mix").status == StageStatus.SUCCEEDED


def test_new_project_defaults_to_auto_and_legacy_reads_ru():
    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=1)
    assert p.transcription_defaults["language"] == "auto"
    legacy = Project.from_dict({**p.to_dict(), "transcription_defaults": {"model": "x"}})
    assert stored_language(legacy.transcription_defaults) == "ru"
