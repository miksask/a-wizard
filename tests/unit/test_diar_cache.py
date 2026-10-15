"""Cached per-track diarization turns."""

from __future__ import annotations

import json
import wave
from pathlib import Path

from a_wizard.adapters.diarization.engines import MockDiarAdapter
from a_wizard.application.diar_cache import diar_cache_paths, load_or_diarize
from a_wizard.domain.freshness import DIAR_CACHE_VERSION
from a_wizard.domain.models import SpeakerTurn, Track, TrackMode


class CountingDiar:
    def __init__(self, adapter_id: str = "fake-diar") -> None:
        self.adapter_id = adapter_id
        self.calls = 0

    def diarize(self, wav: Path, **_: object) -> list[SpeakerTurn]:
        self.calls += 1
        return [SpeakerTurn(0, 50, "SPEAKER_01"), SpeakerTurn(50, 100, "SPEAKER_02")]


def _project(tmp_path: Path, *, frames: int = 1600, value: int = 0) -> tuple[Path, Track]:
    project_dir = tmp_path / "p.project"
    wav = project_dir / "tracks" / "track_0.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(value.to_bytes(2, "little", signed=True) * frames)
    return project_dir, Track(index=0, wav="tracks/track_0.wav", mode=TrackMode.DIARIZED)


def test_cache_hit_skips_diarizer(tmp_path: Path):
    project_dir, track = _project(tmp_path)
    diar = CountingDiar()
    first = load_or_diarize(project_dir, track, diar)
    second = load_or_diarize(project_dir, track, diar)
    assert diar.calls == 1
    assert first == second
    _, meta_path = diar_cache_paths(project_dir, 0)
    meta = json.loads(meta_path.read_text())
    assert meta["adapter_id"] == "fake-diar"
    assert meta["algorithm_version"] == DIAR_CACHE_VERSION


def test_cache_miss_on_wav_change_and_adapter_change(tmp_path: Path):
    project_dir, track = _project(tmp_path)
    diar = CountingDiar()
    load_or_diarize(project_dir, track, diar)
    _project(tmp_path, frames=3200)
    load_or_diarize(project_dir, track, diar)
    assert diar.calls == 2
    other = CountingDiar("other-diar")
    load_or_diarize(project_dir, track, other)
    assert other.calls == 1


def test_legacy_or_corrupt_turns_are_recomputed(tmp_path: Path):
    project_dir, track = _project(tmp_path)
    turns_path, _ = diar_cache_paths(project_dir, 0)
    turns_path.parent.mkdir(parents=True, exist_ok=True)
    turns_path.write_text(json.dumps([{"start_ms": 0, "end_ms": 10, "speaker": "SPEAKER_S1"}]))
    diar = CountingDiar()
    turns = load_or_diarize(project_dir, track, diar)
    assert diar.calls == 1
    assert turns[0].speaker == "SPEAKER_01"
    turns_path.write_text("not json")
    load_or_diarize(project_dir, track, diar)
    assert diar.calls == 2


def test_non_cacheable_adapter_always_runs(tmp_path: Path):
    project_dir, track = _project(tmp_path)
    diar = MockDiarAdapter(turns=[SpeakerTurn(0, 10, "SPEAKER_00")])
    load_or_diarize(project_dir, track, diar)
    load_or_diarize(project_dir, track, diar)
    turns_path, meta_path = diar_cache_paths(project_dir, 0)
    assert turns_path.is_file()
    assert not meta_path.exists()
