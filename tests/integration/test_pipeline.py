"""End-to-end pipeline with mock engines and synthetic media."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from a_wizard.adapters.asr.engines import MockAsrAdapter
from a_wizard.adapters.diarization.engines import MockDiarAdapter
from a_wizard.application.service import ServiceConfig, WizardService
from a_wizard.domain.errors import ExitCode
from a_wizard.domain.models import (
    ProcessingMode,
    Segment,
    SpeakerTurn,
    StageStatus,
    Word,
)


def _make_multitrack_mkv(path: Path, tracks: int = 2, seconds: float = 1.0) -> None:
    inputs = []
    maps = []
    for i in range(tracks):
        inputs += ["-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono"]
        maps += ["-map", f"{i}:a"]
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        *maps,
        "-t",
        str(seconds),
        "-c:a",
        "aac",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture
def mock_svc() -> WizardService:
    asr = MockAsrAdapter(
        segments=[
            Segment(0, 800, "employee line one", "X"),
            Segment(2000, 2800, "employee line two", "X"),
        ],
        words=[
            Word(0, 400, "employee"),
            Word(400, 800, "line"),
            Word(2000, 2400, "employee"),
            Word(2400, 2800, "two"),
        ],
    )
    diar = MockDiarAdapter(
        turns=[
            SpeakerTurn(0, 1500, "SPEAKER_00"),
            SpeakerTurn(1600, 3000, "SPEAKER_01"),
        ]
    )
    return WizardService(
        config=ServiceConfig(
            use_mock_engines=True,
            processing_mode=ProcessingMode.MIXDOWN,
        ),
        asr=asr,
        diar=diar,
    )


def test_full_pipeline_mixdown_preset(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "interview.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    code = mock_svc.run_until_blocked(
        video,
        preset="obs-interview",
        allow_raw_speakers=True,
        processing_mode=ProcessingMode.MIXDOWN,
        print_fn=lambda s: None,
    )
    assert code == ExitCode.SUCCESS
    project_dir = tmp_path / "interview.project"
    assert (project_dir / "manifest.yaml").is_file()
    assert (project_dir / "tracks" / "track_0.wav").is_file()
    assert (project_dir / "tracks" / "mix.wav").is_file()
    assert (project_dir / "transcripts" / "mix.raw.json").is_file()
    assert (project_dir / "transcripts" / "mix.segments.json").is_file()
    assert (project_dir / "dialog" / "dialog.json").is_file()
    minimize = (project_dir / "dialog" / "dialog.minimize.txt").read_text(encoding="utf-8")
    assert ":" in minimize

    project = mock_svc.load(project_dir)
    assert project.processing_mode == ProcessingMode.MIXDOWN
    assert project.stage("mixdown").status == StageStatus.SUCCEEDED
    assert project.stage("transcribe:mix").status == StageStatus.SUCCEEDED
    assert project.stage("attribute").status == StageStatus.SUCCEEDED

    before = (project_dir / "manifest.yaml").read_bytes()
    code2 = mock_svc.run_until_blocked(project_dir, status_only=True, print_fn=lambda s: None)
    assert code2 == 0
    assert (project_dir / "manifest.yaml").read_bytes() == before


def test_full_pipeline_per_track(tmp_path: Path):
    video = tmp_path / "legacy.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    asr = MockAsrAdapter(
        [
            Segment(0, 800, "employee line one", "X"),
            Segment(2000, 2800, "employee line two", "X"),
        ]
    )
    diar = MockDiarAdapter(
        [
            Segment(100, 900, "manager asks", "SPEAKER_00"),
            Segment(1000, 1800, "colleague answers", "SPEAKER_01"),
        ]
    )
    svc = WizardService(
        config=ServiceConfig(
            use_mock_engines=True,
            processing_mode=ProcessingMode.PER_TRACK,
        ),
        asr=asr,
        diar=diar,
    )
    code = svc.run_until_blocked(
        video,
        preset="obs-interview",
        allow_raw_speakers=True,
        processing_mode=ProcessingMode.PER_TRACK,
        print_fn=lambda s: None,
    )
    assert code == ExitCode.SUCCESS
    project_dir = tmp_path / "legacy.project"
    assert not (project_dir / "tracks" / "mix.wav").is_file()
    assert (project_dir / "dialog" / "dialog.minimize.txt").is_file()


def test_speaker_map_invalidates_merge(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "call.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert (
        mock_svc.run_until_blocked(
            video,
            preset="obs-interview",
            print_fn=lambda s: None,
        )
        == 0
    )
    project_dir = tmp_path / "call.project"
    project = mock_svc.load(project_dir)
    assert project.stage("merge").status == StageStatus.SUCCEEDED

    # Legacy remap still invalidates merge/minimize
    mapping = {"SPEAKER_T1D0": "__MANAGER__", "SPEAKER_T1D1": "__COLLEAGUE__"}
    mock_svc.map_speakers(project, 1, mapping, reviewed=True)
    mock_svc.repo.save(project_dir, project)
    project = mock_svc.load(project_dir)
    assert project.stage("merge").status == StageStatus.STALE

    mock_svc.lock.acquire(project_dir)
    try:
        mock_svc.run_merge(project_dir, project)
        project = mock_svc.load(project_dir)
        mock_svc.run_minimize(project_dir, project)
    finally:
        mock_svc.lock.release(project_dir)

    text = (project_dir / "dialog" / "dialog.minimize.txt").read_text(encoding="utf-8")
    assert ":" in text


def test_pipeline_emits_fixed_speaker_ids(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "ids.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert (
        mock_svc.run_until_blocked(
            video,
            preset="obs-interview",
            print_fn=lambda s: None,
        )
        == 0
    )
    project_dir = tmp_path / "ids.project"
    dialog = (project_dir / "dialog" / "dialog.json").read_text(encoding="utf-8")
    assert "SPEAKER_T" in dialog
    minimize = (project_dir / "dialog" / "dialog.minimize.txt").read_text(encoding="utf-8")
    assert "ST" in minimize
    project = mock_svc.load(project_dir)
    assert project.tracks[0].plain_speaker == "SPEAKER_T0"
    timings = (project_dir / "manifest.yaml").read_text(encoding="utf-8")
    assert "started_at" in timings
