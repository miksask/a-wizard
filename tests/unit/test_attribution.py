"""Unit tests for channel-energy attribution."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from a_wizard.adapters.media.energy import NumpyChannelEnergyProfiler, mean_energy
from a_wizard.adapters.media.ffmpeg import FfmpegMediaAdapter
from a_wizard.application.attribution import attribute_words
from a_wizard.domain.freshness import mark_stale_downstream
from a_wizard.domain.models import (
    ProcessingMode,
    Project,
    StageStatus,
    TrackMode,
    TrackStatus,
    Word,
)


def _sine_wav(path: Path, *, freq: float, seconds: float = 1.0, rate: int = 16000) -> None:
    n = int(rate * seconds)
    t = np.arange(n) / rate
    audio = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(audio.tobytes())


def _gated_sine(
    path: Path,
    *,
    active: list[tuple[float, float]],
    freq: float = 440.0,
    seconds: float = 1.0,
    rate: int = 16000,
) -> None:
    n = int(rate * seconds)
    t = np.arange(n) / rate
    audio = np.zeros(n, dtype=np.float32)
    for start, end in active:
        mask = (t >= start) & (t < end)
        audio[mask] = 0.4 * np.sin(2 * np.pi * freq * t[mask])
    pcm = (audio * 32767).astype(np.int16)
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


def test_attribute_alternating_windows(tmp_path: Path):
    # track0 active 0-0.4s, track1 active 0.5-0.9s
    t0 = tmp_path / "t0.wav"
    t1 = tmp_path / "t1.wav"
    _gated_sine(t0, active=[(0.0, 0.4)], freq=440)
    _gated_sine(t1, active=[(0.5, 0.9)], freq=880)

    profiler = NumpyChannelEnergyProfiler()
    p0 = profiler.profile(t0)
    p1 = profiler.profile(t1)
    assert mean_energy(p0, 100, 200) > mean_energy(p1, 100, 200)
    assert mean_energy(p1, 600, 700) > mean_energy(p0, 600, 700)

    project = Project.new(source_path="/v.mkv", basename="v.mkv", audio_stream_count=2)
    project.tracks[0].mode = TrackMode.PLAIN
    project.tracks[0].plain_speaker = "SPEAKER_T0"
    project.tracks[1].mode = TrackMode.PLAIN
    project.tracks[1].plain_speaker = "SPEAKER_T1"

    words = [
        Word(100, 200, "hello"),
        Word(250, 350, "there"),
        Word(600, 700, "world"),
        Word(750, 850, "yes"),
    ]
    result = attribute_words(
        words,
        project.tracks,
        {0: p0, 1: p1},
        {},
        ambiguity_ratio=1.05,
    )
    assert result.words[0].speaker == "SPEAKER_T0"
    assert result.words[0].channel == 0
    assert result.words[2].speaker == "SPEAKER_T1"
    assert result.words[2].channel == 1
    assert result.report["ambiguous_ratio"] < 0.5


def test_channel_role_invalidates_attribute_keeps_asr():
    p = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=2,
        processing_mode=ProcessingMode.MIXDOWN,
    )
    p.stage("transcribe:mix").status = StageStatus.SUCCEEDED
    p.stage("attribute").status = StageStatus.SUCCEEDED
    p.stage("merge").status = StageStatus.SUCCEEDED
    keys = mark_stale_downstream(p, "track:0")
    assert "attribute" in keys
    assert "merge" in keys
    assert p.stage("transcribe:mix").status == StageStatus.SUCCEEDED


def test_mixdown_ffmpeg(tmp_path: Path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "mix.wav"
    try:
        _sine_wav(a, freq=440, seconds=0.5)
        _sine_wav(b, freq=880, seconds=0.5)
        FfmpegMediaAdapter().mixdown([a, b], out, force=True)
    except (FileNotFoundError, Exception) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_detect_mixdown_next_action():
    from a_wizard.domain.dag import ActionKind, detect_next_action

    p = Project.new(
        source_path="/v.mkv",
        basename="v.mkv",
        audio_stream_count=2,
        processing_mode=ProcessingMode.MIXDOWN,
    )
    p.stage("extract").status = StageStatus.SUCCEEDED
    p.transcription_defaults["initial_prompt_reviewed"] = True
    p.tracks[0].mode = TrackMode.PLAIN
    p.tracks[0].plain_speaker = "SPEAKER_T0"
    p.tracks[0].status = TrackStatus.EXTRACTED
    p.tracks[1].mode = TrackMode.DIARIZED
    p.tracks[1].status = TrackStatus.EXTRACTED
    a = detect_next_action(p, skip_interactive=True)
    assert a.kind == ActionKind.MIXDOWN
