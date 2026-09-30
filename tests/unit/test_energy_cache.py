"""Energy profile cache validation."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from a_wizard.application.attribution import load_or_compute_profiles
from a_wizard.domain.freshness import ENERGY_ALGORITHM_VERSION, sha256_file
from a_wizard.domain.models import Track, TrackMode


def _write_silence_wav(path: Path, *, frames: int = 1600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * frames)


def test_energy_cache_hit(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    wav = project_dir / "tracks" / "track_0.wav"
    _write_silence_wav(wav)
    tracks = [Track(index=0, wav="tracks/track_0.wav", mode=TrackMode.PLAIN)]
    p1 = load_or_compute_profiles(project_dir, tracks, window_ms=20)
    meta = json.loads((project_dir / "meta" / "energy" / "track_0.json").read_text())
    assert meta["algorithm_version"] == ENERGY_ALGORITHM_VERSION
    assert meta["wav_sha256"] == sha256_file(wav)
    mtime = (project_dir / "meta" / "energy" / "track_0.npy").stat().st_mtime_ns
    p2 = load_or_compute_profiles(project_dir, tracks, window_ms=20)
    assert np.array_equal(p1[0], p2[0])
    assert (project_dir / "meta" / "energy" / "track_0.npy").stat().st_mtime_ns == mtime


def test_energy_cache_miss_on_window(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    wav = project_dir / "tracks" / "track_0.wav"
    _write_silence_wav(wav)
    tracks = [Track(index=0, wav="tracks/track_0.wav", mode=TrackMode.PLAIN)]
    load_or_compute_profiles(project_dir, tracks, window_ms=20)
    load_or_compute_profiles(project_dir, tracks, window_ms=40)
    meta = json.loads((project_dir / "meta" / "energy" / "track_0.json").read_text())
    assert meta["window_ms"] == 40


def test_energy_cache_miss_on_wav_change(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    wav = project_dir / "tracks" / "track_0.wav"
    _write_silence_wav(wav, frames=1600)
    tracks = [Track(index=0, wav="tracks/track_0.wav", mode=TrackMode.PLAIN)]
    load_or_compute_profiles(project_dir, tracks)
    old = sha256_file(wav)
    _write_silence_wav(wav, frames=3200)
    load_or_compute_profiles(project_dir, tracks)
    meta = json.loads((project_dir / "meta" / "energy" / "track_0.json").read_text())
    assert meta["wav_sha256"] != old
    assert meta["wav_sha256"] == sha256_file(wav)


def test_energy_cache_corrupt_npy(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    wav = project_dir / "tracks" / "track_0.wav"
    _write_silence_wav(wav)
    tracks = [Track(index=0, wav="tracks/track_0.wav", mode=TrackMode.PLAIN)]
    load_or_compute_profiles(project_dir, tracks)
    npy = project_dir / "meta" / "energy" / "track_0.npy"
    npy.write_bytes(b"not-a-npy")
    profiles = load_or_compute_profiles(project_dir, tracks)
    assert 0 in profiles
    assert isinstance(profiles[0], np.ndarray)
