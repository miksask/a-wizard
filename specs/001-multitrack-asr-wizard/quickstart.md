# Quickstart: a-wizard

Canonical install and usage live in the repository [README.md](../../README.md). This page is a short pointer aligned with that README.

## Install

```bash
cd a-wizard
uv sync --extra dev
uv sync --extra mlx --extra diar-onnx
```

There is no `--extra diar`. Optional Python diarization: `uv sync --extra diar-pyannote` and `HF_TOKEN` only for `pyannote-community-1`. FluidAudio (Apple Silicon CoreML) is built from source; see the README for clone/build/`fluidaudio` PATH steps.

Requirements: Python 3.13, `ffmpeg`, and `ffprobe`.

## First run

```bash
uv run a-wizard doctor
uv run a-wizard run /path/to/recording.mkv
# new projects default to --processing-mode mixdown
# first run asks for prompt, language, and track modes (unless --preset)

uv run a-wizard run /path/to/recording.project --status-only
uv run a-wizard plan /path/to/recording.project --json
```

## Non-interactive

```bash
uv run a-wizard run recording.mkv --preset obs-interview
```

Preset `obs-interview`: track 0 → plain (`SPEAKER_T0`); all other tracks → diarized. Language is left at the project default (`auto`); the preset does not assign role names such as `__EMPLOYEE__`.

## Primary output

```text
recording.project/dialog/dialog.minimize.txt
```

For `configure`, `options`, attribution behavior, and adapters, see [README.md](../../README.md).

## Doctor

```bash
uv run a-wizard doctor
uv run a-wizard doctor /path/to/recording.project
```
