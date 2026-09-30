"""CLI metadata-only and hygiene smoke tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from a_wizard.adapters.asr.engines import MockAsrAdapter
from a_wizard.adapters.diarization.engines import MockDiarAdapter
from a_wizard.application.service import ServiceConfig, WizardService
from a_wizard.cli.app import app
from a_wizard.domain.models import ProcessingMode, Segment, SpeakerTurn, Word


def _make_mkv(path: Path, tracks: int = 2) -> None:
    inputs: list[str] = []
    maps: list[str] = []
    for i in range(tracks):
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono"]
        maps += ["-map", f"{i}:a"]
    cmd = ["ffmpeg", "-y", *inputs, *maps, "-t", "0.5", "-c:a", "aac", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture
def finished_project(tmp_path: Path) -> Path:
    video = tmp_path / "clip.mkv"
    try:
        _make_mkv(video)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")
    svc = WizardService(
        config=ServiceConfig(use_mock_engines=True, processing_mode=ProcessingMode.MIXDOWN),
        asr=MockAsrAdapter(
            segments=[Segment(0, 400, "hi", "X")],
            words=[Word(0, 400, "hi")],
        ),
        diar=MockDiarAdapter(turns=[SpeakerTurn(0, 400, "SPEAKER_00")]),
    )
    assert svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    return tmp_path / "clip.project"


def test_status_and_plan_metadata_only(finished_project: Path):
    runner = CliRunner()
    status = runner.invoke(app, ["status", str(finished_project)])
    assert status.exit_code == 0, status.output
    out_l = status.output.lower()
    assert "minimize" in out_l or "done" in status.output or "[x]" in status.output

    plan = runner.invoke(app, ["plan", str(finished_project), "--json"])
    assert plan.exit_code == 0, plan.output
    assert "next" in plan.output
    assert "done" in plan.output.lower() or '"kind"' in plan.output


def test_status_after_artifact_delete(finished_project: Path):
    (finished_project / "transcripts" / "mix.raw.json").unlink()
    runner = CliRunner()
    plan = runner.invoke(app, ["plan", str(finished_project), "--json"])
    assert plan.exit_code == 0, plan.output
    assert "transcribe" in plan.output.lower()
