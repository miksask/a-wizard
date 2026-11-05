"""Speak rendering, cache key, and clone ref extraction."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from a_wizard.application.speak import (
    cache_key,
    extract_clone_ref,
    render_sequential,
    render_timeline,
    write_wav_mono,
)
from a_wizard.domain.models import Project, Segment, Track, TrackMode, TrackStatus


def test_cache_key_changes_with_voice():
    a = cache_key(
        text="hi",
        lang="en",
        model_id="m",
        voice="af_heart",
        ref_digest=None,
        speed=1.0,
    )
    b = cache_key(
        text="hi",
        lang="en",
        model_id="m",
        voice="am_adam",
        ref_digest=None,
        speed=1.0,
    )
    assert a != b


def test_cache_key_stable():
    a = cache_key(
        text="hi", lang="en", model_id="m", voice="v", ref_digest=None, speed=1.0
    )
    b = cache_key(
        text="hi", lang="en", model_id="m", voice="v", ref_digest=None, speed=1.0
    )
    assert a == b


def test_render_sequential_pause():
    sr = 1000
    a = np.ones(100, dtype=np.float32)
    b = np.ones(50, dtype=np.float32) * 0.5
    out = render_sequential(
        [a, b],
        ["A", "A"],
        sample_rate=sr,
        pause_ms=100,
        speaker_change_pause_ms=200,
    )
    # 100 + 100 pause + 50
    assert len(out) == 250


def test_render_sequential_speaker_change_longer_pause():
    sr = 1000
    a = np.ones(10, dtype=np.float32)
    b = np.ones(10, dtype=np.float32)
    same = render_sequential(
        [a, b], ["A", "A"], sample_rate=sr, pause_ms=50, speaker_change_pause_ms=200
    )
    change = render_sequential(
        [a, b], ["A", "B"], sample_rate=sr, pause_ms=50, speaker_change_pause_ms=200
    )
    assert len(change) > len(same)


def test_render_timeline_placement():
    sr = 1000
    clip = np.ones(100, dtype=np.float32)  # 100 ms
    audio, overruns = render_timeline(
        [clip, clip],
        [0, 500],
        [100, 600],
        sample_rate=sr,
        fit=False,
    )
    assert overruns == 0
    assert len(audio) >= 600
    assert audio[0] == 1.0
    assert audio[500] == 1.0
    assert abs(float(audio[250])) < 1e-6


def test_render_timeline_overrun_count():
    sr = 1000
    long_clip = np.ones(400, dtype=np.float32)  # 400 ms
    short_slot = np.ones(50, dtype=np.float32)
    audio, overruns = render_timeline(
        [long_clip, short_slot],
        [0, 200],
        [400, 250],
        sample_rate=sr,
        fit=False,
    )
    assert overruns == 1
    assert len(audio) > 0


def test_extract_clone_ref(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    (project_dir / "tracks").mkdir(parents=True)
    # 2 seconds of 16 kHz tone
    sr = 16_000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    audio = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav_path = project_dir / "tracks" / "track_0.wav"
    write_wav_mono(wav_path, audio, sr)

    project = Project.new(source_path="/x.mkv", basename="x.mkv", audio_stream_count=1)
    project.tracks = [
        Track(
            index=0,
            wav="tracks/track_0.wav",
            mode=TrackMode.PLAIN,
            status=TrackStatus.TRANSCRIBED,
            plain_speaker="SPEAKER_T0",
        )
    ]
    segs = [
        Segment(200, 900, "hello world", "SPEAKER_T0"),
        Segment(1000, 1800, "more speech here", "SPEAKER_T0"),
    ]
    out = project_dir / "dialog" / "speech" / "refs" / "SPEAKER_T0.wav"
    path, ref_text = extract_clone_ref(
        project_dir, project, "SPEAKER_T0", segs, out_path=out
    )
    assert path.is_file()
    assert "hello" in ref_text
    with wave.open(str(path), "rb") as wf:
        assert wf.getnframes() > 0
        duration_ms = wf.getnframes() * 1000 / wf.getframerate()
    assert duration_ms >= 1000  # collected longest segments
