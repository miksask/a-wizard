"""Per-track mode: each track keeps its own words only where it carries speech."""

from __future__ import annotations

import numpy as np
from synth_signals import frames, profile, turn_taking, with_copy, words_in

from a_wizard.application.attribution import filter_track_words
from a_wizard.domain.models import Track, TrackMode, TrackStatus, Word, canonical_plain_speaker


def _tracks(*modes: str) -> list[Track]:
    out = []
    for i, mode in enumerate(modes):
        track = Track(index=i, wav=f"tracks/track_{i}.wav", mode=TrackMode(mode))
        track.status = TrackStatus.TRANSCRIBED
        if mode == "plain":
            track.plain_speaker = canonical_plain_speaker(i)
        out.append(track)
    return out


def _rows(result) -> dict[int, dict]:
    return {row["index"]: row for row in result.report["tracks"]}


def test_hallucinations_on_silent_track_are_dropped():
    desk = profile(20, [(2, 6), (10, 14)], level=4000, seed=1)
    mic = profile(20, floor=300, jitter=0.2, seed=2)
    track_words = {
        0: words_in(2, 6, 6, "d") + words_in(10, 14, 6, "e"),
        1: [Word(7000, 7600, "Thank"), Word(7700, 8100, "you.")],
    }
    result = filter_track_words(track_words, _tracks("diarized", "plain"), {0: desk, 1: mic})
    assert result.kept[1] == []
    assert len(result.kept[0]) == 12
    assert _rows(result)[1]["dropped_hallucination"] == 2
    assert result.report["fallback"] is False


def test_crosstalk_copies_are_dropped_but_own_words_kept():
    desk_spans, room_spans = turn_taking(120, seed=5)
    desk = profile(120, desk_spans, level=3000, floor=60, jitter=0.15, seed=3)
    room_own = profile(120, room_spans, level=2000, floor=150, jitter=0.15, seed=4)
    room = with_copy(room_own, desk, lag_s=0.24, gain=0.4)
    desk_words: list[Word] = []
    copies: list[Word] = []
    own: list[Word] = []
    for n, (start, end) in enumerate(desk_spans):
        for w in words_in(start + 0.1, end - 0.1, 3, f"d{n}w"):
            desk_words.append(w)
            copies.append(Word(w.start_ms + 240, w.end_ms + 240, f"copy-{w.text}"))
    for n, (start, end) in enumerate(room_spans):
        own.extend(words_in(start + 0.1, end - 0.1, 3, f"own{n}w"))
    room_words = sorted(copies + own, key=lambda w: w.start_ms)

    result = filter_track_words(
        {0: desk_words, 1: room_words}, _tracks("plain", "diarized"), {0: desk, 1: room}
    )
    kept_room = {w.text for w in result.kept[1]}
    assert len(result.kept[0]) == len(desk_words)
    assert not any(t.startswith("copy-") for t in kept_room)
    assert sum(1 for w in own if w.text in kept_room) >= 0.95 * len(own)
    rows = _rows(result)
    assert rows[1]["dropped_crosstalk"] + rows[1]["dropped_dominated"] >= len(copies) * 0.95
    assert any(link["src"] == 0 and link["dst"] == 1 for link in result.report["crosstalk"])


def test_dominated_words_dropped_only_where_other_track_has_words():
    desk = profile(30, [(2, 8)], level=4000, seed=5)
    room_own = profile(30, [(12, 15)], level=2500, floor=100, jitter=0.1, seed=6)
    room = with_copy(room_own, desk, lag_s=0.0, gain=0.15)
    desk_words = words_in(2, 5, 4, "d")
    room_words = words_in(2, 5, 4, "x") + words_in(5.5, 8, 3, "y") + words_in(12, 15, 4, "own")
    result = filter_track_words(
        {0: desk_words, 1: room_words}, _tracks("diarized", "plain"), {0: desk, 1: room}
    )
    kept = {w.text for w in result.kept[1]}
    assert not any(t.startswith("x") for t in kept)
    assert {"y0", "y1", "y2", "own0", "own1", "own2", "own3"} <= kept
    assert _rows(result)[1]["dropped_dominated"] == 4


def test_nothing_filtered_without_any_activity():
    silent = np.zeros(frames(10))
    track_words = {0: words_in(1, 9, 5), 1: words_in(1, 9, 5, "z")}
    result = filter_track_words(track_words, _tracks("plain", "plain"), {0: silent, 1: silent})
    assert result.report["fallback"] is True
    assert len(result.kept[0]) == 5 and len(result.kept[1]) == 5
    assert result.report["warnings"]


def test_segment_units_are_filtered_as_coarse_words():
    desk = profile(20, [(2, 6)], level=4000, seed=7)
    mic = profile(20, floor=300, jitter=0.2, seed=8)
    seg_words = {
        0: [Word(2000, 6000, "a long desk segment")],
        1: [Word(10000, 12000, "phantom segment")],
    }
    result = filter_track_words(
        seg_words,
        _tracks("diarized", "plain"),
        {0: desk, 1: mic},
        units={0: "segments", 1: "segments"},
    )
    assert [w.text for w in result.kept[0]] == ["a long desk segment"]
    assert result.kept[1] == []
    assert {row["unit"] for row in result.report["tracks"]} == {"segments"}
