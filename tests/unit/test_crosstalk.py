"""Crosstalk detection and compensation on synthetic energy envelopes."""

from __future__ import annotations

import numpy as np
from synth_signals import frames, profile, turn_taking, with_copy

from a_wizard.application.activity import noise_floor
from a_wizard.application.crosstalk import (
    compensate_crosstalk,
    detect_crosstalk,
    excess_db,
    lagged_correlation,
)
from a_wizard.domain.activity import DEFAULT_ACTIVITY_PARAMS as P


def rooms(seconds: float = 120.0):
    a_spans, b_spans = turn_taking(seconds, seed=11)
    a = profile(seconds, a_spans, level=3000, floor=60, jitter=0.15, seed=1)
    b_own = profile(seconds, b_spans, level=2000, floor=150, jitter=0.15, seed=2)
    return a, b_own, a_spans, b_spans


def test_lagged_correlation_matches_numpy():
    rng = np.random.default_rng(0)
    a = rng.normal(size=500)
    b = np.roll(a, 7) + 0.3 * rng.normal(size=500)
    corr = lagged_correlation(a, b, 20)
    for lag in (0, 3, 7, 15):
        expected = np.corrcoef(a[: 500 - lag], b[lag:])[0, 1]
        assert abs(corr[lag] - expected) < 1e-9
    assert int(np.argmax(corr)) == 7


def test_detects_delayed_copy_with_lag_and_gain():
    a, b_own, _, _ = rooms()
    b = with_copy(b_own, a, lag_s=0.24, gain=0.4)
    links = detect_crosstalk({0: a, 1: b}, {0: noise_floor(a), 1: noise_floor(b)}, P)
    assert len(links) == 1
    link = links[0]
    assert (link.src, link.dst) == (0, 1)
    assert abs(link.lag_frames * P.window_ms - 240) <= 40
    assert 0.25 <= link.gain <= 0.7
    assert link.compensated


def test_no_link_for_independent_turn_taking():
    a, b_own, _, _ = rooms()
    links = detect_crosstalk({0: a, 1: b_own}, {0: noise_floor(a), 1: noise_floor(b_own)}, P)
    assert links == []


def test_same_room_copy_is_not_compensated():
    a_own, b_own, _, _ = rooms()
    a = with_copy(a_own, b_own, lag_s=0.0, gain=0.3)
    b = with_copy(b_own, a_own, lag_s=0.0, gain=0.3)
    links = detect_crosstalk({0: a, 1: b}, {0: noise_floor(a), 1: noise_floor(b)}, P)
    assert not any(link.compensated for link in links)


def test_compensation_removes_copy_and_keeps_own_speech():
    a, b_own, a_spans, b_spans = rooms()
    b = with_copy(b_own, a, lag_s=0.24, gain=0.4)
    floors = {0: noise_floor(a), 1: noise_floor(b)}
    links = detect_crosstalk({0: a, 1: b}, floors, P)
    fixed = compensate_crosstalk({0: a, 1: b}, links, floors, P)

    copy_frames = np.zeros(len(b), dtype=bool)
    for start, end in a_spans:
        copy_frames[frames(start + 0.3) : frames(end + 0.2)] = True
    own_frames = np.zeros(len(b), dtype=bool)
    for start, end in b_spans:
        own_frames[frames(start) : frames(end)] = True
    copy_only = copy_frames & ~own_frames
    own_only = own_frames & ~copy_frames

    before = excess_db(b, floors[1])[copy_only]
    after = excess_db(fixed[1], floors[1])[copy_only]
    assert float(np.mean(before >= P.gate_db)) > 0.9
    assert float(np.mean(after >= P.gate_db)) < 0.1
    assert np.allclose(fixed[1][own_only], b[own_only], rtol=0.01)
    assert fixed[0] is a
