"""Typer CLI for a-wizard."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from a_wizard.application.service import ServiceConfig, WizardService, resolve_target
from a_wizard.domain.dag import ActionKind, NextAction
from a_wizard.domain.errors import AppError, ExitCode, UsageError
from a_wizard.domain.models import ProcessingMode, Project, TrackMode

app = typer.Typer(
    name="a-wizard",
    help="Resume-safe multitrack ASR wizard",
    no_args_is_help=True,
    add_completion=False,
)
bench_app = typer.Typer(help="Benchmark utilities")
app.add_typer(bench_app, name="bench")
console = Console(stderr=True)
out = Console()


def _service(
    mock: bool = False,
    *,
    asr_adapter: str = "auto",
    diar_adapter: str = "auto",
    processing_mode: str = "mixdown",
) -> WizardService:
    mode = ProcessingMode(processing_mode)
    return WizardService(
        config=ServiceConfig(
            use_mock_engines=mock,
            asr_adapter="mock-asr" if mock else asr_adapter,
            diar_adapter="mock-diar" if mock else diar_adapter,
            processing_mode=mode,
        )
    )


def _handle_error(err: BaseException) -> int:
    if isinstance(err, AppError):
        console.print(f"[red]{err.message}[/red]")
        if err.next_step:
            console.print(f"Next: {err.next_step}")
        return err.exit_code
    if isinstance(err, typer.Exit):
        raise err
    console.print(f"[red]Internal error: {err}[/red]")
    return ExitCode.INTERNAL


def _prompt_choice(prompt: str, options: list[str], *, default: int | None = None) -> int:
    console.print(prompt)
    for i, opt in enumerate(options, start=1):
        mark = " (default)" if default is not None and i == default else ""
        console.print(f"  [{i}] {opt}{mark}")
    while True:
        raw = input("> ").strip()
        if not raw and default is not None:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print("Invalid choice, try again.")


def _interactive_handler(svc: WizardService):
    def handle(project_dir: Path, project: Project, action: NextAction) -> bool:
        if action.kind == ActionKind.CONFIGURE_PROMPT:
            current = project.transcription_defaults.get("initial_prompt")
            if isinstance(current, str) and current:
                console.print(f"Current initial_prompt: {current}")
            choice = _prompt_choice(
                "Whisper initial_prompt for the project:",
                [
                    "leave empty / unchanged",
                    "disable prompt",
                    "enter custom prompt",
                ],
                default=1,
            )
            if choice == 2:
                project.transcription_defaults["initial_prompt"] = None
            elif choice == 3:
                text = input("initial_prompt text: ").strip()
                project.transcription_defaults["initial_prompt"] = text or None
            project.transcription_defaults["initial_prompt_reviewed"] = True
            lang_choice = _prompt_choice("Project language:", ["ru", "en"], default=1)
            project.transcription_defaults["language"] = ("ru", "en")[lang_choice - 1]
            svc.repo.save(project_dir, project)
            return True

        if action.kind == ActionKind.CONFIGURE_TRACK:
            assert action.track_index is not None
            idx = action.track_index
            track = project.get_track(idx)
            console.print(f"\nTrack {idx} (channel role in mixdown)")
            console.print(f"  WAV: {(project_dir / track.wav).resolve()}")
            mode_choice = _prompt_choice(
                "Channel mode:",
                [
                    "plain — one speaker",
                    "diarized — multiple speakers on the channel",
                    "skipped — exclude from the mix",
                ],
            )
            if mode_choice == 1:
                svc.set_track_mode(project, idx, mode="plain")
            elif mode_choice == 2:
                svc.set_track_mode(project, idx, mode="diarized")
            else:
                reason = input("Skip reason (Enter for none): ").strip() or None
                svc.set_track_mode(project, idx, mode="skipped", reason=reason)
            svc.repo.save(project_dir, project)
            return True

        if action.kind == ActionKind.NEED_HF_TOKEN:
            console.print(
                "\nThe pyannote-community-1 adapter requires a Hugging Face token.\n"
                "export HF_TOKEN=hf_..."
            )
            return False

        return False

    return handle


def _parse_track_flag(item: str) -> tuple[int, str, str | None]:
    parts = item.split(":", 2)
    if len(parts) < 2 or not parts[0].isdigit():
        raise UsageError(
            f"bad --track value: {item!r} (expected N:mode)",
            code="bad_track",
        )
    idx = int(parts[0])
    mode = parts[1].strip()
    reason = parts[2].strip() or None if len(parts) == 3 else None
    if mode not in ("plain", "diarized", "skipped"):
        raise UsageError(
            f"track {idx}: mode must be plain, diarized, or skipped",
            code="bad_mode",
        )
    return idx, mode, reason


def _collect_configure(
    project: Project,
    *,
    language: str | None,
    prompt: str | None,
    no_prompt: bool,
    track_flags: list[str],
) -> tuple[str, str | None, dict[int, str], dict[int, str | None]]:
    if prompt is not None and no_prompt:
        raise UsageError("--prompt and --no-prompt are mutually exclusive", code="bad_prompt")

    tty = sys.stdin.isatty()
    defaults = project.transcription_defaults or {}
    current_prompt = defaults.get("initial_prompt")
    if isinstance(current_prompt, str) and not current_prompt.strip():
        current_prompt = None

    if no_prompt:
        initial_prompt: str | None = None
    elif prompt is not None:
        initial_prompt = prompt
    elif tty:
        if isinstance(current_prompt, str) and current_prompt:
            console.print(f"Current initial_prompt: {current_prompt}")
        choice = _prompt_choice(
            "Whisper initial_prompt for the project:",
            [
                "leave empty / unchanged",
                "disable prompt",
                "enter custom prompt",
            ],
            default=1,
        )
        if choice == 2:
            initial_prompt = None
        elif choice == 3:
            text = input("initial_prompt text: ").strip()
            initial_prompt = text or None
        else:
            initial_prompt = current_prompt if isinstance(current_prompt, str) else None
    else:
        raise UsageError(
            "non-interactive configure requires --prompt or --no-prompt",
            code="prompt_required",
            next_step="pass --prompt TEXT or --no-prompt",
        )

    if language is not None:
        if language not in ("ru", "en"):
            raise UsageError("language must be ru or en", code="bad_language")
        chosen_lang = language
    elif tty:
        current_lang = defaults.get("language", "ru")
        lang_default = 1 if current_lang == "ru" else 2
        lang_choice = _prompt_choice("Project language:", ["ru", "en"], default=lang_default)
        chosen_lang = ("ru", "en")[lang_choice - 1]
    else:
        raise UsageError(
            "non-interactive configure requires --language",
            code="language_required",
            next_step="pass --language ru|en",
        )

    parsed: dict[int, tuple[str, str | None]] = {}
    for item in track_flags:
        idx, mode, reason = _parse_track_flag(item)
        parsed[idx] = (mode, reason)

    track_modes: dict[int, str] = {}
    skip_reasons: dict[int, str | None] = {}
    for t in project.tracks:
        if t.index in parsed:
            track_modes[t.index] = parsed[t.index][0]
            skip_reasons[t.index] = parsed[t.index][1]
            continue
        if not tty:
            raise UsageError(
                f"non-interactive configure requires --track {t.index}:mode",
                code="track_required",
                next_step="pass --track N:plain|diarized|skipped for every track",
            )
        console.print(f"\nTrack {t.index} (channel role in mixdown)")
        if t.wav:
            console.print(f"  WAV: {t.wav}")
        mode_default = {
            TrackMode.PLAIN: 1,
            TrackMode.DIARIZED: 2,
            TrackMode.SKIPPED: 3,
        }.get(t.mode)
        mode_choice = _prompt_choice(
            "Channel mode:",
            [
                "plain — one speaker",
                "diarized — multiple speakers on the channel",
                "skipped — exclude from the mix",
            ],
            default=mode_default,
        )
        if mode_choice == 1:
            track_modes[t.index] = "plain"
        elif mode_choice == 2:
            track_modes[t.index] = "diarized"
        else:
            reason = input("Skip reason (Enter for none): ").strip() or None
            track_modes[t.index] = "skipped"
            skip_reasons[t.index] = reason

    return chosen_lang, initial_prompt, track_modes, skip_reasons


@app.command()
def run(
    target: str = typer.Argument(..., help="Video file or .project directory"),
    status_only: bool = typer.Option(False, "--status-only", help="Show status and exit"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview next step only"),
    preset: Optional[str] = typer.Option(None, "--preset", help="Non-interactive preset"),
    allow_raw_speakers: bool = typer.Option(
        False, "--allow-raw-speakers", help="Allow merge with unreviewed SPEAKER labels"
    ),
    processing_mode: str = typer.Option(
        "mixdown",
        "--processing-mode",
        help="mixdown (default) | per_track",
    ),
    asr_adapter: str = typer.Option(
        "auto", "--asr-adapter", help="auto|mlx-whisper|faster-whisper|mock-asr"
    ),
    diar_adapter: str = typer.Option(
        "auto",
        "--diar-adapter",
        help="auto|fluidaudio|sherpa-onnx|speakrs-coreml|pyannote-community-1|mock-diar",
    ),
    mock: bool = typer.Option(False, "--mock", help="Use mock ASR/diar engines (tests)"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable summary"),
) -> None:
    """Run or resume the ASR pipeline."""
    svc = _service(
        mock=mock,
        asr_adapter=asr_adapter,
        diar_adapter=diar_adapter,
        processing_mode=processing_mode,
    )

    def printer(msg: str) -> None:
        if not json_out:
            out.print(msg)

    try:
        interactive = None if preset else _interactive_handler(svc)
        code = svc.run_until_blocked(
            target,
            preset=preset,
            allow_raw_speakers=allow_raw_speakers,
            dry_run=dry_run,
            status_only=status_only,
            processing_mode=ProcessingMode(processing_mode),
            interactive_handler=interactive,
            print_fn=printer,
        )
        if json_out:
            project_dir, _, _ = resolve_target(target)
            if project_dir and svc.repo.exists(project_dir):
                project = svc.load(project_dir)
                out.print(json.dumps(svc.plan_dict(project), ensure_ascii=False, indent=2))
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e
    except Exception as e:
        raise typer.Exit(_handle_error(e)) from e
    raise typer.Exit(code)


@app.command("status")
def status_cmd(
    target: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
    mock: bool = typer.Option(False, "--mock", hidden=True),
) -> None:
    """Show project checklist."""
    svc = _service(mock=mock)
    try:
        project_dir, _, needs_init = resolve_target(target)
        if needs_init or project_dir is None or not svc.repo.exists(project_dir):
            out.print("Project not initialized yet.")
            raise typer.Exit(0)
        project = svc.load(project_dir)
        if json_out:
            out.print(json.dumps(svc.plan_dict(project), ensure_ascii=False, indent=2))
        else:
            out.print(svc.status_text(project_dir, project))
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("plan")
def plan_cmd(
    target: str = typer.Argument(...),
    json_out: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Show stage DAG plan."""
    svc = _service()
    try:
        project_dir, _, needs_init = resolve_target(target)
        if needs_init or project_dir is None or not svc.repo.exists(project_dir):
            raise AppError("Project not initialized", code="not_initialized", exit_code=ExitCode.USAGE)
        project = svc.load(project_dir)
        data = svc.plan_dict(project)
        if json_out:
            out.print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            out.print(svc.status_text(project_dir, project))
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("init")
def init_cmd(
    video: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force"),
    processing_mode: str = typer.Option("mixdown", "--processing-mode"),
    asr_adapter: str = typer.Option("auto", "--asr-adapter"),
    diar_adapter: str = typer.Option("auto", "--diar-adapter"),
    mock: bool = typer.Option(False, "--mock", hidden=True),
) -> None:
    """Initialize a project for a video file."""
    svc = _service(
        mock=mock,
        asr_adapter=asr_adapter,
        diar_adapter=diar_adapter,
        processing_mode=processing_mode,
    )
    try:
        path = svc.init_project(
            Path(video), force=force, processing_mode=ProcessingMode(processing_mode)
        )
        out.print(f"Created project: {path}")
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("configure")
def configure_cmd(
    target: str = typer.Argument(..., help="Video file or .project directory"),
    language: Optional[str] = typer.Option(None, "--language", help="ru|en"),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="Whisper initial_prompt"),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Clear initial_prompt"),
    track_flags: list[str] = typer.Option(
        [],
        "--track",
        help="N:mode or N:mode:reason (repeatable). mode=plain|diarized|skipped",
    ),
) -> None:
    """Re-enter project prompt, language, and track modes without running ASR."""
    svc = _service(mock=True)
    try:
        project_dir, _, needs_init = resolve_target(target)
        if needs_init or project_dir is None or not svc.repo.exists(project_dir):
            raise UsageError(
                "Project not initialized",
                code="not_initialized",
                next_step="a-wizard init VIDEO  or  a-wizard run VIDEO",
            )
        proj = svc.load(project_dir)
        language_v, prompt_v, modes, reasons = _collect_configure(
            proj,
            language=language,
            prompt=prompt,
            no_prompt=no_prompt,
            track_flags=track_flags,
        )
        svc.lock.acquire(project_dir)
        try:
            result = svc.apply_configure(
                proj,
                language=language_v,
                initial_prompt=prompt_v,
                track_modes=modes,
                skip_reasons=reasons,
            )
            svc.repo.save(project_dir, proj)
        finally:
            svc.lock.release(project_dir)

        out.print(f"Language: {result['language']}")
        out.print(f"Prompt: {'set' if result['prompt_set'] else '(none)'}")
        for idx, mode in result["tracks"].items():
            extra = f" ({reasons.get(idx)})" if mode == "skipped" and reasons.get(idx) else ""
            out.print(f"Track {idx}: {mode}{extra}")
        if result["changed"]:
            out.print("Settings saved; dependent stages marked stale.")
        else:
            out.print("No settings changed.")
        out.print(f"Next: a-wizard run {project_dir}")
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("track")
def track_cmd(
    project: str = typer.Option(..., "--project"),
    track: int = typer.Option(..., "--track"),
    mode: str = typer.Option(..., "--mode", help="plain|diarized|skipped|pending"),
    speaker: Optional[str] = typer.Option(
        None, "--speaker", help="Optional override; plain defaults to SPEAKER_T{n}"
    ),
    reason: Optional[str] = typer.Option(None, "--reason"),
) -> None:
    """Set track / channel mode."""
    svc = _service()
    try:
        project_dir = Path(project).resolve()
        proj = svc.load(project_dir)
        svc.lock.acquire(project_dir)
        try:
            svc.set_track_mode(
                proj,
                track,
                mode=mode,
                speaker=speaker,
                reason=reason,
            )
            t = proj.get_track(track)
            if t.mode in (TrackMode.PLAIN, TrackMode.DIARIZED) and t.status.value == "pending":
                if (project_dir / t.wav).is_file():
                    from a_wizard.domain.models import TrackStatus

                    t.status = TrackStatus.EXTRACTED
            svc.repo.save(project_dir, proj)
            out.print(f"Track {track}: mode={mode}")
        finally:
            svc.lock.release(project_dir)
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("speakers")
def speakers_cmd(
    project: str = typer.Option(..., "--project"),
    track: int = typer.Option(..., "--track"),
    map_pairs: list[str] = typer.Option(
        ...,
        "--map",
        help="SPEAKER_T1D0=__MANAGER__ (legacy remap; repeatable)",
    ),
) -> None:
    """Optional legacy speaker remapping (new runs use fixed SPEAKER_Tn / SPEAKER_TnDm)."""
    svc = _service()
    try:
        mapping: dict[str, str] = {}
        for item in map_pairs:
            if "=" not in item:
                raise AppError(f"bad map item: {item}", code="bad_map", exit_code=ExitCode.USAGE)
            k, v = item.split("=", 1)
            mapping[k.strip()] = v.strip()
        project_dir = Path(project).resolve()
        proj = svc.load(project_dir)
        svc.lock.acquire(project_dir)
        try:
            t = proj.get_track(track)
            normalized = {}
            for k, v in mapping.items():
                if k in t.speaker_map:
                    normalized[k] = v
                elif f"T{track}/{k}" in t.speaker_map:
                    normalized[f"T{track}/{k}"] = v
                else:
                    normalized[k] = v
            svc.map_speakers(proj, track, normalized, reviewed=True)
            svc.repo.save(project_dir, proj)
            out.print(f"Updated speaker_map for track {track}")
        finally:
            svc.lock.release(project_dir)
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("stage")
def stage_cmd(
    project: str = typer.Option(..., "--project"),
    stage: str = typer.Option(
        ...,
        "--stage",
        help="extract|mixdown|transcribe-mix|attribute|transcribe|merge|minimize",
    ),
    track: Optional[int] = typer.Option(None, "--track"),
    allow_raw_speakers: bool = typer.Option(False, "--allow-raw-speakers"),
    mock: bool = typer.Option(False, "--mock", hidden=True),
) -> None:
    """Run a single stage."""
    svc = _service(mock=mock)
    try:
        project_dir = Path(project).resolve()
        proj = svc.load(project_dir)
        svc.lock.acquire(project_dir)
        try:
            if stage == "extract":
                svc.run_extract(project_dir, proj)
            elif stage == "mixdown":
                svc.run_mixdown(project_dir, proj)
            elif stage in ("transcribe-mix", "transcribe:mix"):
                svc.run_transcribe_mix(project_dir, proj)
            elif stage == "attribute":
                svc.run_attribute(project_dir, proj)
            elif stage == "transcribe":
                if track is None:
                    raise AppError("--track required", code="track_required", exit_code=ExitCode.USAGE)
                svc.run_transcribe(project_dir, proj, track)
            elif stage == "merge":
                svc.run_merge(project_dir, proj, allow_raw_speakers=allow_raw_speakers)
            elif stage == "minimize":
                svc.run_minimize(project_dir, proj)
            else:
                raise AppError(f"unknown stage: {stage}", code="bad_stage", exit_code=ExitCode.USAGE)
            out.print(f"Stage {stage} completed")
        finally:
            svc.lock.release(project_dir)
    except AppError as e:
        raise typer.Exit(_handle_error(e)) from e


@app.command("doctor")
def doctor_cmd(
    target: Optional[str] = typer.Argument(None),
) -> None:
    """Check environment and optional project health."""
    import os
    import platform

    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            out.print(f"OK {tool}: {path}")
        else:
            out.print(f"MISSING {tool}")
            ok = False

    # ASR
    try:
        import mlx_whisper  # noqa: F401

        out.print("OK mlx-whisper installed")
    except ImportError:
        out.print("OPTIONAL mlx-whisper not installed (uv sync --extra mlx)")
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            out.print("  Hint (Apple Silicon): uv sync --extra mlx")

    try:
        import faster_whisper  # noqa: F401

        out.print("OK faster-whisper installed (non-Apple fallback)")
    except ImportError:
        out.print("OPTIONAL faster-whisper not installed (uv sync --extra asr)")

    # Diarization
    from a_wizard.adapters.diarization.fluidaudio import fluidaudio_bin
    from a_wizard.adapters.diarization.speakrs import speakrs_bin

    fluid = fluidaudio_bin()
    if fluid:
        out.print(f"OK fluidaudio: {fluid}")
    else:
        out.print("OPTIONAL fluidaudio binary missing")
        out.print("  Hint: build FluidAudio CLI and export A_WIZARD_FLUIDAUDIO_BIN=/path/to/fluidaudio")

    try:
        import sherpa_onnx  # noqa: F401

        out.print("OK sherpa-onnx installed")
    except ImportError:
        out.print("OPTIONAL sherpa-onnx not installed (uv sync --extra diar-onnx)")

    speakrs = speakrs_bin()
    if speakrs:
        out.print(f"OK speakrs (experimental): {speakrs}")
    else:
        out.print("OPTIONAL speakrs-coreml not on PATH (bench only)")

    try:
        import pyannote.audio  # noqa: F401

        out.print("OK pyannote.audio (optional community-1)")
    except ImportError:
        out.print("OPTIONAL pyannote.audio not installed (uv sync --extra diar-pyannote)")

    swift = shutil.which("swift")
    if swift:
        out.print(f"OK swift: {swift} (needed to build FluidAudio)")
    else:
        out.print("OPTIONAL swift not found (Xcode CLT for FluidAudio builds)")

    try:
        import numpy  # noqa: F401

        out.print("OK numpy")
    except ImportError:
        out.print("MISSING numpy")
        ok = False

    token = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"))
    out.print(
        f"{'OK' if token else 'OPTIONAL'} HF_TOKEN present: {token} "
        "(only for pyannote-community-1)"
    )

    if target:
        svc = _service()
        try:
            project_dir, _, needs_init = resolve_target(target)
            if needs_init or not project_dir or not svc.repo.exists(project_dir):
                out.print("Project not initialized")
            else:
                project = svc.load(project_dir)
                out.print(f"OK manifest schema_version={project.schema_version}")
                out.print(f"OK processing_mode={project.processing_mode.value}")
                out.print(svc.status_text(project_dir, project))
        except AppError as e:
            out.print(f"ERROR {e.message}")
            ok = False
    raise typer.Exit(0 if ok else ExitCode.USAGE)


@bench_app.command("diar")
def bench_diar(
    input_wav: Path = typer.Option(..., "--input", help="WAV to diarize"),
    backends: str = typer.Option(
        "fluidaudio,sherpa-onnx,speakrs-coreml",
        "--backends",
        help="Comma-separated backend ids",
    ),
) -> None:
    """Compare diarization backends (RTFx, speaker count)."""
    from a_wizard.adapters.diarization.engines import resolve_diar_adapter

    if not input_wav.is_file():
        raise typer.Exit(_handle_error(AppError(f"missing wav: {input_wav}", code="wav_missing")))

    # duration via ffprobe
    import subprocess

    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(input_wav),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration_s = float((r.stdout or "0").strip() or "0")
    except Exception:
        duration_s = 0.0

    table = Table(title="Diarization bench")
    table.add_column("backend")
    table.add_column("wall_s", justify="right")
    table.add_column("RTFx", justify="right")
    table.add_column("speakers", justify="right")
    table.add_column("error")

    for name in [b.strip() for b in backends.split(",") if b.strip()]:
        try:
            adapter = resolve_diar_adapter(name)
            t0 = time.perf_counter()
            turns = adapter.diarize(input_wav)
            wall = time.perf_counter() - t0
            speakers = len({t.speaker for t in turns})
            rtfx = (duration_s / wall) if wall > 0 and duration_s > 0 else float("nan")
            table.add_row(
                name,
                f"{wall:.3f}",
                f"{rtfx:.1f}" if rtfx == rtfx else "n/a",
                str(speakers),
                "",
            )
        except Exception as e:
            table.add_row(name, "-", "-", "-", str(e)[:80])

    out.print(table)


def main() -> None:
    try:
        app()
    except SystemExit as e:
        raise SystemExit(int(e.code) if isinstance(e.code, int) else 1) from e


if __name__ == "__main__":
    main()
