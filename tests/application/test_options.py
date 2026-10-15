"""Opt-in ASR options: service invalidation, ASR pass-through, CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from a_wizard.adapters.asr.engines import MockAsrAdapter
from a_wizard.adapters.diarization.engines import MockDiarAdapter
from a_wizard.application.service import ServiceConfig, WizardService
from a_wizard.cli.app import app
from a_wizard.domain.errors import ExitCode, UsageError
from a_wizard.domain.models import ProcessingMode, Segment, SpeakerTurn, StageStatus, Word


def _mock_service() -> WizardService:
    return WizardService(
        config=ServiceConfig(use_mock_engines=True, processing_mode=ProcessingMode.MIXDOWN),
        asr=MockAsrAdapter(
            segments=[Segment(0, 400, "hi there", "X")],
            words=[Word(0, 200, "hi"), Word(200, 400, "there")],
        ),
        diar=MockDiarAdapter(turns=[SpeakerTurn(0, 400, "SPEAKER_00")]),
    )


@pytest.fixture
def finished(tmp_path: Path) -> tuple[WizardService, Path]:
    video = tmp_path / "opt.mkv"
    cmd = ["ffmpeg", "-y"]
    for _ in range(2):
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono"]
    cmd += ["-map", "0:a", "-map", "1:a", "-t", "0.6", "-c:a", "aac", str(video)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")
    svc = _mock_service()
    assert svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    return svc, tmp_path / "opt.project"


def test_apply_options_invalidates_only_dependents(finished):
    svc, project_dir = finished
    project = svc.load(project_dir)
    result = svc.apply_options(project, audio_cleanup=True)
    assert result["changed"] and result["audio_cleanup"]
    assert set(result["invalidated"]) == {
        "mixdown",
        "transcribe:mix",
        "attribute",
        "merge",
        "minimize",
    }
    assert project.stage("extract").status == StageStatus.SUCCEEDED
    again = svc.apply_options(project, audio_cleanup=True, hallucination_silence=...)
    assert again["changed"] is False and again["invalidated"] == []
    with pytest.raises(UsageError):
        svc.apply_options(project, hallucination_silence=0)


def test_options_reach_asr_and_cleanup_mix_runs(finished):
    svc, project_dir = finished
    project = svc.load(project_dir)
    svc.apply_options(project, audio_cleanup=True, hallucination_silence=2.0)
    svc.repo.save(project_dir, project)
    assert svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0
    assert svc.asr.last_options["hallucination_silence_threshold"] == 2.0
    project = svc.load(project_dir)
    assert project.stage("mixdown").adapter_id == "numpy-gain-mix"
    assert project.stage("minimize").status == StageStatus.SUCCEEDED
    assert (project_dir / "tracks" / "mix.wav").is_file()
    assert "Options: audio_cleanup=on, hallucination_silence=2s" in svc.status_text(
        project_dir, project
    )


def test_options_cli(finished):
    _, project_dir = finished
    runner = CliRunner()
    shown = runner.invoke(app, ["options", str(project_dir)])
    assert shown.exit_code == 0, shown.output
    assert "audio_cleanup: off" in shown.output

    set_ = runner.invoke(
        app, ["options", str(project_dir), "--audio-cleanup", "--hallucination-silence", "1.5"]
    )
    assert set_.exit_code == 0, set_.output
    defaults = yaml.safe_load((project_dir / "manifest.yaml").read_text())[
        "transcription_defaults"
    ]
    assert defaults["audio_cleanup"] is True
    assert defaults["hallucination_silence_threshold"] == 1.5

    clash = runner.invoke(
        app,
        ["options", str(project_dir), "--hallucination-silence", "1", "--no-hallucination-silence"],
    )
    assert clash.exit_code == ExitCode.USAGE
    bad = runner.invoke(app, ["options", str(project_dir), "--hallucination-silence", "0"])
    assert bad.exit_code == ExitCode.USAGE

    cleared = runner.invoke(
        app, ["options", str(project_dir), "--no-audio-cleanup", "--no-hallucination-silence"]
    )
    assert cleared.exit_code == 0, cleared.output
    defaults = yaml.safe_load((project_dir / "manifest.yaml").read_text())[
        "transcription_defaults"
    ]
    assert "audio_cleanup" not in defaults
    assert "hallucination_silence_threshold" not in defaults


def test_options_cli_requires_project(tmp_path: Path):
    video = tmp_path / "none.mkv"
    video.write_bytes(b"")
    result = CliRunner().invoke(app, ["options", str(video)])
    assert result.exit_code == ExitCode.USAGE
