"""Application-level speak tests with fake TTS."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest
from typer.testing import CliRunner

from a_wizard.adapters.persistence.store import YamlProjectRepository
from a_wizard.application.speak import SpeakOptions, speak_project, speak_txt
from a_wizard.cli.app import app
from a_wizard.domain.errors import UsageError
from a_wizard.domain.models import Project, StageStatus


def _project_with_dialog(tmp_path: Path, *, merge_ok: bool = True) -> tuple[Path, Project]:
    project_dir = tmp_path / "demo.project"
    (project_dir / "dialog").mkdir(parents=True)
    project = Project.new(source_path="/demo.mkv", basename="demo.mkv", audio_stream_count=2)
    if merge_ok:
        rec = project.stage("merge")
        rec.status = StageStatus.SUCCEEDED
        rec.signature = "test"
    dialog = [
        {
            "start_ms": 0,
            "end_ms": 1000,
            "text": "Hello from track zero.",
            "speaker": "SPEAKER_T0",
        },
        {
            "start_ms": 1200,
            "end_ms": 2200,
            "text": "And a reply from track one.",
            "speaker": "SPEAKER_T1",
        },
    ]
    (project_dir / "dialog" / "dialog.json").write_text(
        json.dumps(dialog, indent=2) + "\n", encoding="utf-8"
    )
    YamlProjectRepository().save(project_dir, project)
    return project_dir, project


def test_speak_project_mock(tmp_path: Path):
    project_dir, project = _project_with_dialog(tmp_path)
    opts = SpeakOptions(mock=True, force=True)
    result = speak_project(project_dir, project, opts)
    assert result.output.is_file()
    assert (project_dir / "dialog" / "speech.json").is_file()
    assert result.cache_misses >= 1
    with wave.open(str(result.output), "rb") as wf:
        assert wf.getnframes() > 0


def test_speak_project_second_run_noop(tmp_path: Path):
    project_dir, project = _project_with_dialog(tmp_path)
    opts = SpeakOptions(mock=True, force=True)
    first = speak_project(project_dir, project, opts)
    assert not first.skipped
    second = speak_project(project_dir, project, SpeakOptions(mock=True))
    assert second.skipped
    assert second.output == first.output


def test_speak_merge_required(tmp_path: Path):
    project_dir, project = _project_with_dialog(tmp_path, merge_ok=False)
    with pytest.raises(UsageError) as ei:
        speak_project(project_dir, project, SpeakOptions(mock=True, force=True))
    assert ei.value.code == "merge_required"


def test_speak_txt_mock(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("Alice: hello there\nBob: hi alice\n", encoding="utf-8")
    result = speak_txt(path, SpeakOptions(mock=True, force=True))
    assert result.output.is_file()
    assert result.output.name == "notes.speech.wav"
    assert result.line_count == 2
    meta = json.loads(result.speech_json.read_text(encoding="utf-8"))
    assert list(meta["voices"]) == ["SPEAKER_00"]


def test_speak_voice_change_partial_cache(tmp_path: Path):
    project_dir, project = _project_with_dialog(tmp_path)
    speak_project(project_dir, project, SpeakOptions(mock=True, force=True))
    # Change only SPEAKER_T1 voice → some cache hits expected
    result = speak_project(
        project_dir,
        project,
        SpeakOptions(mock=True, voices={"SPEAKER_T1": "am_adam"}),
    )
    assert not result.skipped
    assert result.cache_hits >= 1
    assert result.cache_misses >= 1


def test_cli_speak_txt(tmp_path: Path):
    path = tmp_path / "hi.txt"
    path.write_text("Hello world from the CLI.\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["speak", str(path), "--mock", "--force"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "hi.speech.wav").is_file()


def test_cli_speak_project(tmp_path: Path):
    project_dir, _ = _project_with_dialog(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["speak", str(project_dir), "--mock", "--force"])
    assert result.exit_code == 0, result.output
    assert (project_dir / "dialog" / "speech.wav").is_file()


def test_cli_speak_merge_required(tmp_path: Path):
    project_dir, _ = _project_with_dialog(tmp_path, merge_ok=False)
    runner = CliRunner()
    result = runner.invoke(app, ["speak", str(project_dir), "--mock", "--force"])
    assert result.exit_code != 0
    assert "Merge" in result.output or "merge" in result.output.lower()
