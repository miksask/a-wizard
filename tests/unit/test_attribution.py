"""Unit tests for channel-energy attribution."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from synth_signals import flat, frames, profile, with_copy, words_in

from a_wizard.adapters.media.energy import NumpyChannelEnergyProfiler, mean_energy
from a_wizard.adapters.media.ffmpeg import FfmpegMediaAdapter
from a_wizard.application.attribution import assign_speakers_by_turns, attribute_words
from a_wizard.domain.freshness import mark_stale_downstream
from a_wizard.domain.models import (
    ProcessingMode,
    Project,
    SpeakerTurn,
    StageStatus,
    Track,
    TrackMode,
    TrackStatus,
    Word,
    canonical_plain_speaker,
)


def _tracks(*modes: str) -> list[Track]:
    out = []
    for i, mode in enumerate(modes):
        track = Track(index=i, wav=f"tracks/track_{i}.wav", mode=TrackMode(mode))
        track.status = TrackStatus.EXTRACTED
        if mode == "plain":
            track.plain_speaker = canonical_plain_speaker(i)
        out.append(track)
    return out


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


def test_noisy_mic_does_not_steal_desktop_words():
    desk = profile(40, [(2, 6), (7, 12), (20, 25)], level=4000, seed=1)
    mic = profile(40, [(30, 33)], level=3000, floor=300, jitter=0.25, seed=2)
    words = sorted(
        words_in(2, 6, 8, "a")
        + words_in(7, 12, 10, "b")
        + [Word(5900, 6600, "spill"), Word(6700, 6700, "zero")]
        + words_in(20, 25, 8, "c")
        + words_in(30, 33, 5, "u"),
        key=lambda w: w.start_ms,
    )
    turns = {0: [SpeakerTurn(2000, 12000, "SPEAKER_01"), SpeakerTurn(20000, 25000, "SPEAKER_02")]}
    result = attribute_words(words, _tracks("diarized", "plain"), {0: desk, 1: mic}, turns)

    for w in result.words:
        if w.text.startswith("u"):
            assert w.speaker == "SPEAKER_T1", w
        else:
            assert w.channel == 0, w
            assert w.speaker in ("SPEAKER_T0D1", "SPEAKER_T0D2"), w
    assert [s.speaker for s in result.segments].count("SPEAKER_T1") == 1
    assert result.report["fallback"] is False
    assert result.report["silent_count"] >= 1


def test_silent_word_joins_nearest_confident_neighbor():
    desk = profile(12, [(2, 5)], level=4000, seed=3)
    mic = profile(12, [(6, 8)], level=3000, floor=300, jitter=0.2, seed=4)
    words = words_in(2, 5, 6, "d") + [Word(5800, 5900, "gap")] + words_in(6, 8, 4, "u")
    result = attribute_words(words, _tracks("diarized", "plain"), {0: desk, 1: mic}, {})
    gap = next(w for w in result.words if w.text == "gap")
    assert gap.silent and gap.ambiguous
    assert gap.channel == 1


def test_weak_island_is_smoothed_and_strong_interjection_kept():
    desk = flat(16, [(2, 6, 4000), (3.9, 4.2, 1200), (6.5, 8.0, 4000), (8.4, 10, 4000)])
    mic = flat(16, [(3.9, 4.2, 2600), (8.0, 8.4, 3300), (12, 14, 3300)], floor=300)
    words = sorted(
        words_in(2, 3.9, 4, "a")
        + [Word(3950, 4150, "weak")]
        + words_in(4.2, 6, 4, "b")
        + words_in(6.5, 8.0, 3, "c")
        + [Word(8050, 8350, "yeah")]
        + words_in(8.4, 10, 3, "d")
        + words_in(12, 14, 4, "u"),
        key=lambda w: w.start_ms,
    )
    result = attribute_words(words, _tracks("diarized", "plain"), {0: desk, 1: mic}, {})
    by_text = {w.text: w for w in result.words}
    assert by_text["weak"].channel == 0
    assert by_text["weak"].ambiguous
    assert by_text["yeah"].channel == 1
    assert result.report["smoothed_count"] == 1


def test_isolated_hallucinations_dropped_adjacent_kept():
    desk = profile(20, [(2, 5), (13, 15)], level=4000, seed=5)
    mic = profile(20, floor=300, jitter=0.2, seed=6)
    words = sorted(
        words_in(2, 5, 6, "a")
        + [Word(5200, 5500, "tail")]
        + [Word(9000, 9500, "Thank"), Word(9600, 10000, "you.")]
        + words_in(13, 15, 4, "b"),
        key=lambda w: w.start_ms,
    )
    result = attribute_words(words, _tracks("diarized", "plain"), {0: desk, 1: mic}, {})
    by_text = {w.text: w for w in result.words}
    assert by_text["Thank"].dropped and by_text["you."].dropped
    assert not by_text["tail"].dropped and by_text["tail"].channel == 0
    assert result.report["dropped_count"] == 2
    assert result.report["kept_word_count"] == len(words) - 2
    assert all("Thank" not in s.text for s in result.segments)
    assert any("tail" in s.text for s in result.segments)


def test_fallback_when_no_track_is_active():
    silent = np.zeros(frames(5))
    words = words_in(0.5, 4.5, 6)
    result = attribute_words(words, _tracks("plain", "diarized"), {0: silent, 1: silent}, {})
    assert result.report["fallback"] is True
    assert result.report["dropped_count"] == 0
    assert len(result.words) == len(words)
    assert all(w.channel in (0, 1) for w in result.words)
    assert result.report["warnings"]


def test_two_diarized_tracks_keep_speakers_apart():
    desk = profile(20, [(2, 5), (6, 9)], level=4000, seed=7)
    room = profile(20, [(10, 13), (14, 17)], level=2500, floor=200, jitter=0.2, seed=8)
    words = words_in(2, 5, 4) + words_in(6, 9, 4) + words_in(10, 13, 4) + words_in(14, 17, 4)
    turns = {
        0: [SpeakerTurn(2000, 5000, "SPEAKER_01"), SpeakerTurn(6000, 9000, "SPEAKER_02")],
        1: [SpeakerTurn(10000, 13000, "SPEAKER_01"), SpeakerTurn(14000, 17000, "SPEAKER_S2")],
    }
    result = attribute_words(words, _tracks("diarized", "diarized"), {0: desk, 1: room}, turns)
    speakers = [s.speaker for s in result.segments]
    assert speakers == ["SPEAKER_T0D1", "SPEAKER_T0D2", "SPEAKER_T1D1", "SPEAKER_T1D2"]


def test_boundary_word_follows_nearest_same_track_speaker():
    words = [Word(400, 800, "one"), Word(900, 1100, "two"), Word(1500, 1900, "three")]
    turns = [SpeakerTurn(0, 1000, "SPEAKER_00"), SpeakerTurn(1000, 2000, "SPEAKER_01")]
    out = assign_speakers_by_turns(words, turns, track_index=1)
    assert [w.speaker for w in out] == ["SPEAKER_T1D0", "SPEAKER_T1D0", "SPEAKER_T1D1"]


def test_word_without_turn_overlap_takes_nearest_turn():
    out = assign_speakers_by_turns(
        [Word(5000, 5200, "late")],
        [SpeakerTurn(0, 1000, "SPEAKER_00"), SpeakerTurn(4000, 4500, "SPEAKER_03")],
        track_index=0,
    )
    assert out[0].speaker == "SPEAKER_T0D3"


def _room_schedule(seconds: float, rooms: int, seed: int) -> list[tuple[int, float, float]]:
    rng = np.random.default_rng(seed)
    schedule = []
    t = 1.0
    k = 0
    while t < seconds - 5:
        duration = float(rng.uniform(1.5, 3.5))
        schedule.append((k % rooms, t, t + duration))
        t += duration + float(rng.uniform(0.6, 1.2))
        k += 1
    return schedule


def test_four_rooms_with_gain_differences_and_crosstalk():
    seconds = 180.0
    schedule = _room_schedule(seconds, 4, seed=21)
    spans = {r: [(s, e) for room, s, e in schedule if room == r] for r in range(4)}
    a = profile(seconds, spans[0], level=900, floor=40, jitter=0.15, seed=31)
    b = profile(seconds, spans[1], level=2000, floor=100, jitter=0.15, seed=32)
    c = profile(seconds, spans[2], level=2000, floor=100, jitter=0.15, seed=33)
    d = profile(seconds, spans[3], level=2500, floor=80, jitter=0.15, seed=34)
    b = with_copy(b, a, lag_s=0.24, gain=2.0)
    c = with_copy(c, d, lag_s=0.30, gain=0.5)
    words: list[Word] = []
    expected: dict[str, int] = {}
    turns_b: list[SpeakerTurn] = []
    for n, (room, start, end) in enumerate(schedule):
        for w in words_in(start + 0.1, end - 0.1, 5, f"r{room}u{n}w"):
            words.append(w)
            expected[w.text] = room
        if room == 1:
            label = "SPEAKER_01" if len(turns_b) % 2 else "SPEAKER_02"
            turns_b.append(SpeakerTurn(int(start * 1000), int(end * 1000), label))
    tracks = _tracks("plain", "diarized", "plain", "plain")
    result = attribute_words(words, tracks, {0: a, 1: b, 2: c, 3: d}, {1: turns_b})

    correct = sum(1 for w in result.words if w.channel == expected[w.text])
    assert correct / len(words) >= 0.95
    links = {(x["src"], x["dst"]): x for x in result.report["crosstalk"]}
    assert (0, 1) in links and abs(links[(0, 1)]["lag_ms"] - 240) <= 40
    assert (3, 2) in links and abs(links[(3, 2)]["lag_ms"] - 300) <= 40
    assert {s.speaker for s in result.segments if s.speaker.startswith("SPEAKER_T1")} == {
        "SPEAKER_T1D1",
        "SPEAKER_T1D2",
    }


def test_report_lists_per_track_diagnostics_and_noisy_warning():
    desk = profile(30, [(2, 10)], level=4000, seed=9)
    mic = profile(30, [(15, 18)], level=6000, floor=900, jitter=0.2, seed=10)
    words = words_in(2, 10, 8) + words_in(15, 18, 4, "u")
    result = attribute_words(words, _tracks("diarized", "plain"), {0: desk, 1: mic}, {})
    rows = {row["index"]: row for row in result.report["tracks"]}
    assert rows[0]["noise_floor_rms"] == pytest.approx(30.0)
    assert rows[1]["noise_floor_rms"] > 600
    assert rows[1]["word_count"] == 4 and rows[0]["word_count"] == 8
    assert rows[0]["segment_count"] >= 1 and rows[1]["segment_count"] == 1
    assert any("track 1: noisy channel" in w for w in result.report["warnings"])
    assert result.report["algorithm_version"]
