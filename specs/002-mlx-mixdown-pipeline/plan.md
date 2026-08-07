# Implementation Plan: MLX Mixdown Pipeline

**Branch**: `002-mlx-mixdown-pipeline` | **Date**: 2026-08-06

## Technical Context

- Language: Python 3.13, Typer CLI, uv
- ASR: mlx-whisper (Apple), faster-whisper fallback
- Diarization: FluidAudio CLI, sherpa-onnx, experimental speakrs
- Media: ffmpeg amix mixdown + per-track extract
- Architecture: hexagonal ports/adapters (extend 001)

## Constitution Check

- Local-first: yes
- Adapter isolation: yes (ASR ≠ diarization)
- Resume/freshness: extended for mixdown stages
- No secrets in manifests: HF only for optional pyannote community-1

## Project Structure

```
src/a_wizard/
  domain/{models,dag,freshness,errors}.py
  ports/__init__.py
  adapters/asr/engines.py          # mlx + faster-whisper + mock
  adapters/diarization/
    fluidaudio.py, sherpa.py, speakrs.py, engines.py
  adapters/media/ffmpeg.py         # + mixdown
  application/{service,attribution,dialog}.py
  cli/app.py                       # + bench diar, processing-mode
```

## Complexity Tracking

None beyond planned adapters.
