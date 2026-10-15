"""Opt-in cleanup gains and the streamed gain mixer."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest
from synth_signals import flat, frames

from a_wizard.adapters.media.gain_mix import WavGainMixer
from a_wizard.application.activity import build_activity
from a_wizard.application.cleanup import cleanup_gains, dilate
from a_wizard.domain.activity import DEFAULT_CLEANUP_PARAMS as C
from a_wizard.domain.errors import AppError, UsageError


def _write(path: Path, samples: np.ndarray, *, channels: int = 1, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.astype("<i2").tobytes())
    return path


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2").astype(np.int32)


def test_dilate_adds_pre_roll_and_hangover():
    mask = np.zeros(20, dtype=bool)
    mask[10] = True
    assert np.flatnonzero(dilate(mask, before=2, after=3)).tolist() == [8, 9, 10, 11, 12, 13]
    assert dilate(mask, before=0, after=0).tolist() == mask.tolist()


def test_gains_open_on_speech_close_on_silence_and_normalize():
    desk = flat(10, [(2, 4, 4000)])
    model = build_activity({0: desk})
    gain = cleanup_gains(model)[0]
    target = 32768.0 * 10 ** (C.target_level_dbfs / 20)
    norm = target / model.tracks[0].level
    closed = norm * 10 ** (C.closed_gain_db / 20)
    assert gain[frames(3)] == pytest.approx(norm, rel=0.01)
    assert gain[frames(7)] == pytest.approx(closed, rel=0.01)
    assert gain[frames(1.92)] == pytest.approx(norm, rel=0.01)
    assert gain[frames(4.2)] == pytest.approx(norm, rel=0.01)
    assert gain[frames(4.6)] == pytest.approx(closed, rel=0.01)


def test_mixer_applies_gains_and_sums(tmp_path: Path):
    rate = 16000
    t = np.arange(rate) / rate
    a = np.round(0.25 * 32767 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
    b = np.round(0.25 * 32767 * np.sin(2 * np.pi * 880 * t[: rate // 2])).astype(np.int16)
    wa = _write(tmp_path / "a.wav", a)
    wb = _write(tmp_path / "b.wav", b)
    out = WavGainMixer().mix(
        [wa, wb], [np.full(50, 2.0), np.zeros(25)], tmp_path / "mix.wav", chunk_ms=300
    )
    mixed = _read(out)
    assert len(mixed) == rate
    assert np.max(np.abs(mixed - 2 * a.astype(np.int32))) <= 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.wav", "b.wav", "mix.wav"]


def test_mixer_clips_instead_of_wrapping(tmp_path: Path):
    loud = np.full(1600, 30000, dtype=np.int16)
    w = _write(tmp_path / "loud.wav", loud)
    mixed = _read(WavGainMixer().mix([w, w], [np.ones(5), np.ones(5)], tmp_path / "o.wav"))
    assert mixed.max() == 32767


def test_mixer_rejects_bad_inputs(tmp_path: Path):
    mono = _write(tmp_path / "m.wav", np.zeros(160, dtype=np.int16))
    stereo = _write(tmp_path / "s.wav", np.zeros(320, dtype=np.int16), channels=2)
    mixer = WavGainMixer()
    with pytest.raises(UsageError):
        mixer.mix([], [], tmp_path / "x.wav")
    with pytest.raises(UsageError):
        mixer.mix([mono], [], tmp_path / "x.wav")
    with pytest.raises(AppError):
        mixer.mix([mono, stereo], [np.ones(1), np.ones(1)], tmp_path / "x.wav")
