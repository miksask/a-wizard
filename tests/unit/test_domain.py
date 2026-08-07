"""Unit tests for domain models and DAG."""

from __future__ import annotations

import pytest

from a_wizard.domain.dag import ActionKind, detect_next_action
from a_wizard.domain.freshness import mark_stale_downstream, signature
from a_wizard.domain.models import (
    Project,
    Segment,
    StageStatus,
    TrackMode,
    TrackStatus,
    canonical_plain_speaker,
    format_stage_timings,
    short_speaker_id,
    stage_durations,
    track_scoped_speaker,
)


def test_segment_validation():
    with pytest.raises(ValueError):
        Segment(10, 5, "x", "A")
    with pytest.raises(ValueError):
        Segment(0, 1, "  ", "A")


def test_track_scoped_speaker():
    assert track_scoped_speaker(1, "SPEAKER_00") == "SPEAKER_T1D0"
    assert track_scoped_speaker(1, "SPEAKER_T1D0") == "SPEAKER_T1D0"
    assert track_scoped_speaker(0, "SPEAKER_01") == "SPEAKER_T0D1"
    assert track_scoped_speaker(2, "T2/SPEAKER_03") == "SPEAKER_T2D3"
    assert track_scoped_speaker(0, "__MANAGER__") == "__MANAGER__"
    assert canonical_plain_speaker(0) == "SPEAKER_T0"
    assert short_speaker_id("SPEAKER_T0D1") == "ST0D1"
    assert short_speaker_id("SPEAKER_T3") == "ST3"


def test_detect_next_action_flow():
    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=2)
    a = detect_next_action(p, hf_token_available=True)
    assert a.kind == ActionKind.EXTRACT

    p.stage("extract").status = StageStatus.SUCCEEDED
    a = detect_next_action(p, hf_token_available=True)
    assert a.kind == ActionKind.CONFIGURE_PROMPT

    p.transcription_defaults["initial_prompt_reviewed"] = True
    a = detect_next_action(p, hf_token_available=True)
    assert a.kind == ActionKind.CONFIGURE_TRACK
    assert a.track_index == 0


def test_signature_stable():
    assert signature({"a": 1, "b": 2}) == signature({"b": 2, "a": 1})


def test_invalidation_speakers():
    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=1)
    p.stage("merge").status = StageStatus.SUCCEEDED
    p.stage("minimize").status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(p, "speakers:0")
    assert "merge" in keys
    assert "minimize" in keys
    assert p.stage("merge").status == StageStatus.STALE


def test_project_roundtrip_dict():
    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=2)
    p.tracks[0].mode = TrackMode.PLAIN
    p.tracks[0].plain_speaker = "SPEAKER_T0"
    p.tracks[0].status = TrackStatus.EXTRACTED
    data = p.to_dict()
    p2 = Project.from_dict(data)
    assert p2.schema_version == 2
    assert p2.tracks[0].plain_speaker == "SPEAKER_T0"


def test_stage_durations():
    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=1)
    rec = p.stage("extract")
    rec.status = StageStatus.SUCCEEDED
    rec.started_at = "2026-08-06T10:00:00+00:00"
    rec.finished_at = "2026-08-06T10:00:12+00:00"
    rec2 = p.stage("merge")
    rec2.status = StageStatus.SUCCEEDED
    rec2.started_at = "2026-08-06T10:01:00+00:00"
    rec2.finished_at = "2026-08-06T10:01:03+00:00"
    rows = stage_durations(p)
    assert rows == [("extract", 12.0), ("merge", 3.0)]
    text = format_stage_timings(p)
    assert "extract  12.0s" in text
    assert "total  15.0s" in text
