# Quickstart: a-wizard

## Install

```bash
cd a-wizard
uv sync
# optional:
uv sync --extra asr
uv sync --extra diar
export HF_TOKEN=hf_...   # for diarization
```

Requirements: Python 3.13, ffmpeg, and ffprobe.

## First run

```bash
uv run a-wizard run /path/to/recording.mkv
# resume:
uv run a-wizard run /path/to/recording.project
uv run a-wizard status /path/to/recording.project
uv run a-wizard plan /path/to/recording.project --json
```

## Non-interactive

```bash
uv run a-wizard run recording.mkv --preset obs-interview --allow-raw-speakers
```

Preset: track 0 → plain/`__EMPLOYEE__`/ru; all others → diarized/ru.

## Primary output

```text
recording.project/dialog/dialog.minimize.txt
```

## Doctor

```bash
uv run a-wizard doctor
uv run a-wizard doctor recording.project
```
