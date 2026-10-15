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
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono"]
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
    transcript = (project_dir / "dialog" / "transcript.txt").read_text(encoding="utf-8")
    assert transcript == minimize
    timed = (project_dir / "dialog" / "dialog.minimize.ts.txt").read_text(encoding="utf-8")
    assert timed.split("\n\n", 1)[0] == minimize.split("\n\n", 1)[0]
    timed_body = [ln for ln in timed.split("\n\n", 1)[-1].splitlines() if ln]
    plain_body = [ln for ln in minimize.split("\n\n", 1)[-1].splitlines() if ln]
    stripped = [ln.split("] ", 1)[1] for ln in timed_body]
    assert stripped == plain_body
    assert all(ln.startswith("[") and "–" not in ln.split("] ", 1)[0] for ln in timed_body)
    creation = (
        project_dir / "dialog" / "dialog.minimize.ts.creation.txt"
    ).read_text(encoding="utf-8")
    assert creation.split("\n\n", 1)[0] == minimize.split("\n\n", 1)[0]
    creation_body = [ln for ln in creation.split("\n\n", 1)[-1].splitlines() if ln]
    assert [ln.split("] ", 1)[1] for ln in creation_body] == plain_body
    assert creation_body[0].startswith("[")
    assert not creation_body[0].startswith("[00:00:00.000]")

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


def test_configure_language_then_run_redoes_asr(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "reconf.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "reconf.project"
    extract_digest = mock_svc.load(project_dir).stage("extract").output_digests
    asr_before = (project_dir / "transcripts" / "mix.raw.json").read_bytes()

    project = mock_svc.load(project_dir)
    mock_svc.apply_configure(
        project,
        language="en",
        initial_prompt=None,
        track_modes={0: "plain", 1: "diarized"},
    )
    mock_svc.repo.save(project_dir, project)
    project = mock_svc.load(project_dir)
    assert project.stage("transcribe:mix").status == StageStatus.STALE
    assert project.stage("extract").status == StageStatus.SUCCEEDED
    assert project.stage("extract").output_digests == extract_digest

    assert mock_svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0
    project = mock_svc.load(project_dir)
    assert project.stage("transcribe:mix").status == StageStatus.SUCCEEDED
    assert project.stage("extract").output_digests == extract_digest
    assert project.transcription_defaults["language"] == "en"
    # mock ASR is deterministic; file is rewritten after stale transcribe
    assert (project_dir / "transcripts" / "mix.raw.json").is_file()
    _ = asr_before


def test_configure_channel_role_keeps_mix_asr(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "roles.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "roles.project"
    asr_digest = mock_svc.load(project_dir).stage("transcribe:mix").output_digests
    raw_before = (project_dir / "transcripts" / "mix.raw.json").read_bytes()

    project = mock_svc.load(project_dir)
    mock_svc.apply_configure(
        project,
        language=project.transcription_defaults.get("language", "ru"),
        initial_prompt=project.transcription_defaults.get("initial_prompt"),
        track_modes={0: "diarized", 1: "diarized"},
    )
    mock_svc.repo.save(project_dir, project)
    project = mock_svc.load(project_dir)
    assert project.stage("transcribe:mix").status == StageStatus.SUCCEEDED
    assert project.stage("transcribe:mix").output_digests == asr_digest
    assert project.stage("attribute").status == StageStatus.STALE
    assert (project_dir / "transcripts" / "mix.raw.json").read_bytes() == raw_before

    assert mock_svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0
    assert (project_dir / "transcripts" / "mix.raw.json").read_bytes() == raw_before


def test_configure_noop_run_stays_done(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "noop.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "noop.project"
    project = mock_svc.load(project_dir)
    raw_before = (project_dir / "transcripts" / "mix.raw.json").read_bytes()
    result = mock_svc.apply_configure(
        project,
        language=project.transcription_defaults.get("language", "ru"),
        initial_prompt=project.transcription_defaults.get("initial_prompt"),
        track_modes={t.index: t.mode.value for t in project.tracks},
    )
    mock_svc.repo.save(project_dir, project)
    assert result["changed"] is False
    project = mock_svc.load(project_dir)
    assert project.stage("transcribe:mix").status == StageStatus.SUCCEEDED

    assert mock_svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0
    assert (project_dir / "transcripts" / "mix.raw.json").read_bytes() == raw_before


def test_configure_cli_flags_and_missing_tracks(tmp_path: Path, mock_svc: WizardService):
    from typer.testing import CliRunner

    from a_wizard.cli.app import app

    video = tmp_path / "cli.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "cli.project"
    runner = CliRunner()

    missing = runner.invoke(
        app,
        ["configure", str(project_dir), "--language", "en", "--no-prompt"],
    )
    assert missing.exit_code == ExitCode.USAGE

    ok = runner.invoke(
        app,
        [
            "configure",
            str(project_dir),
            "--language",
            "en",
            "--no-prompt",
            "--track",
            "0:plain",
            "--track",
            "1:skipped",
        ],
    )
    assert ok.exit_code == 0, ok.output
    project = mock_svc.load(project_dir)
    assert project.transcription_defaults["language"] == "en"
    assert project.tracks[1].mode.value == "skipped"


def test_configure_cli_other_language(tmp_path: Path, mock_svc: WizardService):
    from typer.testing import CliRunner

    from a_wizard.cli.app import app

    video = tmp_path / "lang.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "lang.project"
    runner = CliRunner()
    tail = ["--no-prompt", "--track", "0:plain", "--track", "1:skipped"]

    def configure(language: str):
        return runner.invoke(app, ["configure", str(project_dir), "--language", language, *tail])

    ok = configure("German")
    assert ok.exit_code == 0, ok.output
    project = mock_svc.load(project_dir)
    assert project.transcription_defaults["language"] == "de"
    assert project.stage("transcribe:mix").status == StageStatus.STALE
    assert project.stage("extract").status == StageStatus.SUCCEEDED

    assert mock_svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0

    # Another spelling of the same language is a no-op.
    again = configure("de")
    assert again.exit_code == 0, again.output
    project = mock_svc.load(project_dir)
    assert project.stage("transcribe:mix").status == StageStatus.SUCCEEDED

    bad = configure("klingon")
    assert bad.exit_code == ExitCode.USAGE
    assert mock_svc.load(project_dir).transcription_defaults["language"] == "de"

    auto = configure("auto")
    assert auto.exit_code == 0, auto.output
    project = mock_svc.load(project_dir)
    assert project.transcription_defaults["language"] == "auto"
    assert project.stage("transcribe:mix").status == StageStatus.STALE


def test_legacy_manifest_language_is_kept(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "legacy.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "legacy.project"
    project = mock_svc.load(project_dir)
    project.transcription_defaults["language"] = "en"
    mock_svc.repo.save(project_dir, project)
    assert mock_svc.load(project_dir).transcription_defaults["language"] == "en"
    # Same stored value is not invalidated by the new default (`auto`).
    assert mock_svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0


def test_missing_mix_raw_triggers_retranscribe(tmp_path: Path, mock_svc: WizardService):
    video = tmp_path / "fresh.mkv"
    try:
        _make_multitrack_mkv(video, tracks=2)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")

    assert mock_svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "fresh.project"
    extract_digest = mock_svc.load(project_dir).stage("extract").output_digests
    (project_dir / "transcripts" / "mix.raw.json").unlink()
    assert mock_svc.run_until_blocked(project_dir, print_fn=lambda s: None) == 0
    project = mock_svc.load(project_dir)
    assert project.stage("transcribe:mix").status == StageStatus.SUCCEEDED
    assert project.stage("extract").output_digests == extract_digest
    assert (project_dir / "transcripts" / "mix.raw.json").is_file()


def _noisy_mic_and_desktop(video: Path, *, user_speaks: bool) -> None:
    """Track 0: microphone with a noise floor (+ one user phrase); track 1: desktop audio
    with digital silence between two remote phrases."""
    import wave

    import numpy as np

    rate, seconds = 16000, 12
    t = np.arange(rate * seconds) / rate
    rng = np.random.default_rng(0)
    mic = 0.012 * rng.standard_normal(len(t))
    if user_speaks:
        m = (t >= 9.0) & (t < 10.5)
        mic[m] += 0.25 * np.sin(2 * np.pi * 300 * t[m])
    desk = np.zeros(len(t))
    for start, end in ((1.0, 4.0), (5.0, 8.0)):
        m = (t >= start) & (t < end)
        desk[m] = 0.3 * np.sin(2 * np.pi * 220 * t[m])
    paths = []
    for name, signal in (("mic", mic), ("desk", desk)):
        path = video.parent / f"{video.stem}.{name}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(np.clip(signal * 32767, -32768, 32767).astype("<i2").tobytes())
        paths.append(path)
    cmd = ["ffmpeg", "-y", "-i", str(paths[0]), "-i", str(paths[1])]
    cmd += ["-map", "0:a", "-map", "1:a", "-c:a", "pcm_s16le", str(video)]
    subprocess.run(cmd, check=True, capture_output=True)


def _desktop_words() -> list[Word]:
    words = [Word(1100 + k * 450, 1500 + k * 450, f"remote{k}") for k in range(6)]
    words.append(Word(3800, 4600, "stretched"))
    words.append(Word(4500, 4500, "pause"))
    words += [Word(5100 + k * 450, 5500 + k * 450, f"second{k}") for k in range(6)]
    return words


def test_noisy_mic_mixdown_keeps_desktop_phrases(tmp_path: Path):
    import json

    video = tmp_path / "call.mkv"
    try:
        _noisy_mic_and_desktop(video, user_speaks=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")
    user = [Word(9100 + k * 450, 9500 + k * 450, f"user{k}") for k in range(3)]
    words = sorted(_desktop_words() + user, key=lambda w: w.start_ms)
    svc = WizardService(
        config=ServiceConfig(use_mock_engines=True, processing_mode=ProcessingMode.MIXDOWN),
        asr=MockAsrAdapter(segments=[Segment(1000, 10500, "x", "X")], words=words),
        diar=MockDiarAdapter(
            turns=[SpeakerTurn(1000, 4000, "S1"), SpeakerTurn(5000, 8000, "S2")]
        ),
    )
    assert svc.run_until_blocked(video, preset="obs-interview", print_fn=lambda s: None) == 0
    project_dir = tmp_path / "call.project"
    dialog = json.loads((project_dir / "dialog" / "dialog.json").read_text(encoding="utf-8"))
    speakers = [seg["speaker"] for seg in dialog]
    assert speakers == ["SPEAKER_T1D1", "SPEAKER_T1D2", "SPEAKER_T0"]
    assert "user0" in dialog[-1]["text"] and "pause" in dialog[0]["text"]
    report = json.loads((project_dir / "meta" / "attribution.json").read_text())
    assert report["fallback"] is False
    assert any(w.startswith("track 0: noisy channel") for w in report["warnings"])


def test_per_track_drops_duplicates_from_silent_track(tmp_path: Path):
    import json

    video = tmp_path / "dup.mkv"
    try:
        _noisy_mic_and_desktop(video, user_speaks=False)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"ffmpeg unavailable: {e}")
    words = _desktop_words()
    svc = WizardService(
        config=ServiceConfig(use_mock_engines=True, processing_mode=ProcessingMode.PER_TRACK),
        asr=MockAsrAdapter(segments=[Segment(1000, 8000, "x", "X")], words=words),
        diar=MockDiarAdapter(turns=[SpeakerTurn(1000, 4000, "S1"), SpeakerTurn(5000, 8000, "S2")]),
    )
    code = svc.run_until_blocked(
        video,
        preset="obs-interview",
        processing_mode=ProcessingMode.PER_TRACK,
        print_fn=lambda s: None,
    )
    assert code == ExitCode.SUCCESS
    project_dir = tmp_path / "dup.project"
    dialog = json.loads((project_dir / "dialog" / "dialog.json").read_text(encoding="utf-8"))
    assert {seg["speaker"] for seg in dialog} == {"SPEAKER_T1D1", "SPEAKER_T1D2"}
    text = " ".join(seg["text"] for seg in dialog)
    assert text.count("remote0") == 1
    assert (project_dir / "transcripts" / "track_0.words.json").is_file()
    report = json.loads((project_dir / "meta" / "track_filter.json").read_text())
    rows = {row["index"]: row for row in report["tracks"]}
    assert rows[0]["kept_count"] == 0
    assert rows[1]["kept_count"] == len(words)
