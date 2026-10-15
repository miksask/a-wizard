"""JSON schema contract tests for emitted artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
MIX_SCHEMA = json.loads(
    (ROOT / "specs/004-pipeline-hardening/contracts/mix.segments.schema.json").read_text()
)
ENERGY_SCHEMA = json.loads(
    (ROOT / "specs/004-pipeline-hardening/contracts/energy-cache.schema.json").read_text()
)
MANIFEST_SCHEMA = json.loads(
    (ROOT / "specs/001-multitrack-asr-wizard/contracts/manifest.schema.json").read_text()
)
REPORT_SCHEMA = json.loads(
    (ROOT / "specs/005-multitrack-attribution/contracts/attribution-report.schema.json").read_text()
)
MIX_V2_SCHEMA = json.loads(
    (ROOT / "specs/005-multitrack-attribution/contracts/mix.segments.schema.json").read_text()
)


def _synthetic_attribution():
    import numpy as np

    from a_wizard.application.attribution import attribute_words
    from a_wizard.domain.models import SpeakerTurn, Track, TrackMode, Word

    rng = np.random.default_rng(0)
    desk = np.zeros(1000)
    desk[100:300] = 4000 * rng.uniform(0.6, 1.4, 200)
    mic = 300 * rng.uniform(0.8, 1.2, 1000)
    mic[600:700] = 3000
    tracks = [
        Track(index=0, wav="tracks/track_0.wav", mode=TrackMode.DIARIZED),
        Track(index=1, wav="tracks/track_1.wav", mode=TrackMode.PLAIN, plain_speaker="SPEAKER_T1"),
    ]
    words = [
        Word(2100, 2500, "hello"),
        Word(2600, 5900, "there"),
        Word(9000, 9500, "Thank"),
        Word(12100, 12600, "yes"),
    ]
    return attribute_words(
        words, tracks, {0: desk, 1: mic}, {0: [SpeakerTurn(2000, 6000, "SPEAKER_01")]}
    )


def test_attribution_report_matches_schema():
    result = _synthetic_attribution()
    jsonschema.validate(result.report, REPORT_SCHEMA)
    assert result.report["dropped_count"] == 1


def test_mix_segments_with_flags_match_both_schemas():
    result = _synthetic_attribution()
    payload = {
        "segments": [s.to_dict() for s in result.segments],
        "words": [w.to_dict() for w in result.words],
    }
    assert any(w.get("dropped") for w in payload["words"])
    jsonschema.validate(payload, MIX_SCHEMA)
    jsonschema.validate(payload, MIX_V2_SCHEMA)


def test_manifest_with_options_matches_schema():
    from a_wizard.domain.models import Project

    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=2)
    p.transcription_defaults["audio_cleanup"] = True
    p.transcription_defaults["hallucination_silence_threshold"] = 2.0
    jsonschema.validate(p.to_dict(), MANIFEST_SCHEMA)
    p.transcription_defaults["hallucination_silence_threshold"] = 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p.to_dict(), MANIFEST_SCHEMA)


def test_mix_segments_schema_accepts_ms_payload():
    payload = {
        "segments": [
            {"start_ms": 0, "end_ms": 100, "text": "hello", "speaker": "SPEAKER_T0"}
        ],
        "words": [
            {
                "start_ms": 0,
                "end_ms": 50,
                "text": "hello",
                "speaker": "SPEAKER_T0",
                "channel": 0,
                "ambiguous": False,
            }
        ],
    }
    jsonschema.validate(payload, MIX_SCHEMA)


def test_mix_segments_schema_rejects_seconds_form():
    payload = {
        "segments": [{"start": 0.0, "end": 0.1, "text": "hello", "speaker": "SPEAKER_T0"}],
        "words": [{"start": 0.0, "end": 0.05, "text": "hello"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, MIX_SCHEMA)


def test_energy_sidecar_schema():
    payload = {
        "wav_sha256": "a" * 64,
        "window_ms": 20,
        "algorithm_version": "a-wizard-2-energy-v1",
    }
    jsonschema.validate(payload, ENERGY_SCHEMA)


def test_project_manifest_roundtrip_matches_schema():
    from a_wizard.domain.models import Project

    p = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=2)
    data = p.to_dict()
    jsonschema.validate(data, MANIFEST_SCHEMA)
