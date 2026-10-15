"""Unit tests for domain models and DAG."""

from __future__ import annotations

from pathlib import Path

import pytest

from a_wizard.domain.dag import ActionKind, detect_next_action
from a_wizard.domain.freshness import mark_stale_downstream, signature
from a_wizard.domain.models import (
    ProcessingMode,
    Project,
    Segment,
    StageStatus,
    TrackMode,
    TrackStatus,
    Word,
    canonical_plain_speaker,
    format_stage_timings,
    normalize_diar_label,
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


def test_normalize_diar_label_variants():
    cases = {
        "S1": "SPEAKER_01",
        "s10": "SPEAKER_10",
        "spk_2": "SPEAKER_02",
        "Speaker 3": "SPEAKER_03",
        "4": "SPEAKER_04",
        "SPEAKER_S7": "SPEAKER_07",
        "SPEAKER_00": "SPEAKER_00",
        "SPEAKER_T1D2": "SPEAKER_T1D2",
        "alice": "SPEAKER_alice",
        "": "SPEAKER_00",
    }
    for raw, expected in cases.items():
        assert normalize_diar_label(raw) == expected, raw
    assert normalize_diar_label(5) == "SPEAKER_05"


def test_track_scoped_speaker_legacy_and_unknown_labels():
    assert track_scoped_speaker(0, "SPEAKER_S3") == "SPEAKER_T0D3"
    assert track_scoped_speaker(2, "S1") == "SPEAKER_T2D1"
    assert track_scoped_speaker(1, "SPEAKER_alice") == "SPEAKER_T1_alice"
    assert track_scoped_speaker(1, "__MANAGER__") == "__MANAGER__"
    assert short_speaker_id(track_scoped_speaker(0, "SPEAKER_S3")) == "ST0D3"


def test_word_flags_serialize_only_when_set():
    plain = Word(0, 10, "x").to_dict()
    assert "silent" not in plain and "dropped" not in plain
    flagged = Word(0, 10, "x", silent=True, dropped=True)
    data = flagged.to_dict()
    assert data["silent"] is True and data["dropped"] is True
    assert Word.from_dict(data) == flagged


def test_adapter_labels_are_normalized():
    from a_wizard.adapters.diarization.fluidaudio import _parse_fluidaudio_json
    from a_wizard.adapters.diarization.speakrs import parse_rttm

    turns = _parse_fluidaudio_json(
        {
            "segments": [
                {"speakerId": "S1", "startTimeSeconds": 0.0, "endTimeSeconds": 1.5},
                {"speakerId": "S10", "startTimeSeconds": 1.5, "endTimeSeconds": 2.0},
            ]
        }
    )
    assert [t.speaker for t in turns] == ["SPEAKER_01", "SPEAKER_10"]
    rttm = "SPEAKER file 1 0.00 1.00 <NA> <NA> spk3 <NA> <NA>\n"
    assert parse_rttm(rttm)[0].speaker == "SPEAKER_03"


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


def test_content_fingerprint_small_file(tmp_path: Path):
    from a_wizard.domain.freshness import content_fingerprint

    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    fp = content_fingerprint(p)
    assert fp.startswith("sha256:")
    assert content_fingerprint(p) == fp


def test_invalidation_speakers():
    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=1)
    p.stage("merge").status = StageStatus.SUCCEEDED
    p.stage("minimize").status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(p, "speakers:0")
    assert "merge" in keys
    assert "minimize" in keys
    assert p.stage("merge").status == StageStatus.STALE


def test_asr_config_invalidates_mix_keeps_extract():
    p = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=2,
        processing_mode=ProcessingMode.MIXDOWN,
    )
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        p.stage(key).status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(p, "asr_config")
    assert "transcribe:mix" in keys
    assert "attribute" in keys
    assert "merge" in keys
    assert "minimize" in keys
    assert p.stage("extract").status == StageStatus.SUCCEEDED
    assert p.stage("mixdown").status == StageStatus.SUCCEEDED


def test_asr_config_invalidates_per_track_active_only():
    p = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=2,
        processing_mode=ProcessingMode.PER_TRACK,
    )
    p.tracks[0].mode = TrackMode.PLAIN
    p.tracks[1].mode = TrackMode.SKIPPED
    p.stage("transcribe:0").status = StageStatus.SUCCEEDED
    p.stage("transcribe:1").status = StageStatus.SUCCEEDED
    p.stage("merge").status = StageStatus.SUCCEEDED
    p.stage("minimize").status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(p, "asr_config")
    assert "transcribe:0" in keys
    assert "transcribe:1" not in keys
    assert "merge" in keys
    assert p.stage("transcribe:1").status == StageStatus.SUCCEEDED


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
