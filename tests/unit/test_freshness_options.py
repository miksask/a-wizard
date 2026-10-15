"""Signatures and invalidation for attribution versioning and opt-in options."""

from __future__ import annotations

from a_wizard.domain import freshness
from a_wizard.domain.freshness import (
    attribute_signature,
    hallucination_silence_threshold,
    mark_stale_downstream,
    merge_signature,
    mix_asr_config,
    mix_transcribe_signature,
    mixdown_signature,
    signature,
    track_asr_config,
    transcribe_signature,
)
from a_wizard.domain.models import ProcessingMode, Project, StageStatus, TrackMode


def _project(mode: ProcessingMode = ProcessingMode.MIXDOWN) -> Project:
    p = Project.new(
        source_path="/v.mkv", basename="v.mkv", audio_stream_count=2, processing_mode=mode
    )
    p.tracks[0].mode = TrackMode.DIARIZED
    p.tracks[1].mode = TrackMode.PLAIN
    p.tracks[1].plain_speaker = "SPEAKER_T1"
    p.stage("extract").output_digests = {"tracks/track_0.wav": "a", "tracks/track_1.wav": "b"}
    return p


def test_default_options_keep_previous_signatures():
    p = _project()
    previous_mixdown = signature(
        "mixdown",
        p.mix.wav,
        [0, 1],
        p.stage("extract").output_digests,
        p.adapters.get("media"),
    )
    assert mixdown_signature(p) == previous_mixdown
    assert set(mix_asr_config(p)) == {
        "model",
        "language",
        "compute_type",
        "device",
        "initial_prompt",
        "adapter",
    }
    assert "audio_cleanup" not in track_asr_config(p, p.tracks[0])
    before = (mixdown_signature(p), mix_transcribe_signature(p))
    p.transcription_defaults["audio_cleanup"] = False
    p.transcription_defaults["hallucination_silence_threshold"] = None
    assert (mixdown_signature(p), mix_transcribe_signature(p)) == before


def test_enabled_options_change_dependent_signatures():
    p = _project()
    mix_before, asr_before = mixdown_signature(p), mix_transcribe_signature(p)
    p.transcription_defaults["audio_cleanup"] = True
    assert mixdown_signature(p) != mix_before
    assert mix_transcribe_signature(p) == asr_before
    p.transcription_defaults["hallucination_silence_threshold"] = 2.0
    assert mix_asr_config(p)["hallucination_silence_threshold"] == 2.0
    assert mix_transcribe_signature(p) != asr_before

    q = _project(ProcessingMode.PER_TRACK)
    sig = transcribe_signature(q, q.tracks[0])
    q.transcription_defaults["audio_cleanup"] = True
    assert transcribe_signature(q, q.tracks[0]) != sig


def test_attribution_version_is_part_of_attribute_and_per_track_merge(monkeypatch):
    p = _project()
    q = _project(ProcessingMode.PER_TRACK)
    attr, merge = attribute_signature(p), merge_signature(q)
    monkeypatch.setattr(freshness, "ATTRIBUTION_ALGORITHM_VERSION", "test-next")
    assert attribute_signature(p) != attr
    assert merge_signature(q) != merge


def test_audio_cleanup_invalidation_by_mode():
    p = _project()
    for key in ("extract", "mixdown", "transcribe:mix", "attribute", "merge", "minimize"):
        p.stage(key).status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(p, "audio_cleanup")
    assert set(keys) == {"mixdown", "transcribe:mix", "attribute", "merge", "minimize"}
    assert p.stage("extract").status == StageStatus.SUCCEEDED

    q = _project(ProcessingMode.PER_TRACK)
    q.tracks[1].mode = TrackMode.SKIPPED
    for key in ("extract", "transcribe:0", "transcribe:1", "merge", "minimize"):
        q.stage(key).status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(q, "audio_cleanup")
    assert set(keys) == {"transcribe:0", "merge", "minimize"}


def test_hallucination_threshold_parsing():
    p = _project()
    for raw, expected in (("2.5", 2.5), (3, 3.0), (0, None), (-1, None), (True, None), ("x", None)):
        p.transcription_defaults["hallucination_silence_threshold"] = raw
        assert hallucination_silence_threshold(p) == expected
