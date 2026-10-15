"""Track activity model: noise floors, speech levels, word evidence."""

from __future__ import annotations

import numpy as np
from synth_signals import frames, profile

from a_wizard.application.activity import build_activity, noise_floor, speech_level
from a_wizard.domain.activity import DEFAULT_ACTIVITY_PARAMS as P


def test_floor_clamps_digital_silence():
    desk = profile(60, [(5, 10), (20, 30)], level=4000)
    floor = noise_floor(desk)
    assert np.allclose(floor[frames(12) : frames(18)], P.min_floor_rms)


def test_floor_follows_noisy_microphone_not_its_lower_tail():
    mic = profile(60, [(10, 11), (40, 41)], level=3000, floor=300, jitter=0.25, seed=1)
    floor = noise_floor(mic)
    middle = floor[frames(20) : frames(35)]
    assert 270 < float(np.median(middle)) < 330


def test_floor_adapts_to_noise_step_within_window():
    quiet = profile(60, floor=200, jitter=0.1, seed=2)
    loud = profile(60, floor=600, jitter=0.1, seed=3)
    floor = noise_floor(np.concatenate([quiet, loud]))
    assert float(np.median(floor[frames(10) : frames(40)])) < 260
    assert float(np.median(floor[frames(80) : frames(110)])) > 500


def test_floor_ignores_long_speech_with_pauses():
    spans = [(t, t + 0.7) for t in np.arange(0.0, 60.0, 1.0)]
    talk = profile(60, spans, level=3000, floor=50, jitter=0.1, seed=4)
    floor = noise_floor(talk)
    assert float(np.median(floor)) < 80


def test_speech_level_from_active_frames():
    mic = profile(60, [(10, 20)], level=3000, floor=300, jitter=0.1, seed=5)
    floor = noise_floor(mic)
    level, floor_median, active_ratio = speech_level(mic, floor)
    assert 2500 < level < 4500
    assert 270 < floor_median < 330
    assert 0.1 < active_ratio < 0.25


def test_evidence_gate_noise_versus_speech():
    mic = profile(30, [(10, 12)], level=3000, floor=300, jitter=0.2, seed=6)
    model = build_activity({1: mic})
    noise = model.evidence(5000, 5400)[1]
    speech = model.evidence(10500, 10900)[1]
    assert noise.snr_db < P.gate_db
    assert speech.snr_db >= P.strong_snr_db


def test_zero_length_word_uses_minimum_window():
    desk = profile(10, [(2, 4)], level=4000)
    model = build_activity({0: desk})
    i0, i1 = model.window(3000, 3000)
    assert (i1 - i0) * P.window_ms >= P.min_word_ms
    assert model.evidence(3000, 3000)[0].snr_db >= P.gate_db


def test_relative_score_is_gain_invariant():
    quiet = profile(60, [(10, 30)], level=800, floor=40, jitter=0.1, seed=7)
    model = build_activity({0: quiet, 1: quiet * 5.0}, crosstalk=False)
    a = model.evidence(15000, 15400)
    assert abs(a[0].score - a[1].score) < 0.05


def test_missing_profile_counts_as_silence():
    desk = profile(10, [(2, 4)], level=4000)
    model = build_activity({0: desk, 1: None})
    ev = model.evidence(2500, 2900)
    assert ev[0].snr_db >= P.gate_db
    assert ev[1].snr_db < P.gate_db
