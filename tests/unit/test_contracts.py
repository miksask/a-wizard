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
