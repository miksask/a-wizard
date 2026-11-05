# Implementation Plan: Speak (TTS)

**Branch**: `006-speak` | **Date**: 2026-10-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-speak/spec.md`

## Summary

Add an explicit `a-wizard speak` command that synthesizes speech from project `dialog/dialog.json` (or an arbitrary `.txt`) via a `TtsEngine` port. Default MLX models: Kokoro for English, Chatterbox multilingual for Russian/Polish, all overridable. Sequential layout by default; optional timeline/`--fit`; optional voice cloning from project tracks; per-line atomic cache; outputs `dialog/speech.wav` + `dialog/speech.json` without changing the ASR DAG or `SCHEMA_VERSION`.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: numpy (base); optional `mlx-audio>=0.6.2` behind `--extra tts` (darwin arm64)

**Storage**: Project `dialog/speech.wav`, `dialog/speech.json`, `dialog/speech/cache/`, `dialog/speech/refs/`; optional project-root `speak.yaml`; txt mode writes beside input

**Testing**: pytest + fake TTS; synthetic wav/dialog; optional `@pytest.mark.slow` mlx smoke

**Target Platform**: macOS Apple Silicon primary; Linux without TTS extra

**Project Type**: local CLI

**Performance Goals**: load each model once per process; group lines by (model, voice); cache hits make re-runs near-instant

**Constraints**: Local-first; no transcript text in logs; speak not in DAG; schema_version stays 2

**Scale/Scope**: dialogs up to several hours of text; 1–N speakers

## Constitution Check

- **I. Local-First Privacy**: Local models; stderr progress/counts only. Pass.
- **II. Resume-Safe Atomic State**: Cache and speech outputs temp→replace; project lock in project mode. Pass.
- **III. Verifiable Freshness**: `speech.json` signature (dialog digest + models + voices + layout); not a stage in manifest. Pass.
- **IV. Ports and Adapters**: `TtsEngine` Protocol; mlx-audio imported only in adapter. Pass.
- **V. Synthetic Tests First**: Fake adapter + synthetic fixtures; real mlx marked slow. Pass.

## Project Structure

### Documentation (this feature)

```text
specs/006-speak/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── contracts/cli.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
src/a_wizard/
  domain/speech.py
  ports/__init__.py              # + TtsEngine
  adapters/tts/
    __init__.py
    registry.py
    mlx_audio.py
    fake.py
  application/speak.py
  cli/app.py                     # speak + doctor

tests/
  unit/test_speech.py
  unit/test_tts_registry.py
  unit/test_speak_render.py
  application/test_speak.py
  integration/test_speak_mlx.py  # slow, skip if missing
```

## Complexity Tracking

| Violation | Why needed | Alternative rejected |
|-----------|------------|----------------------|
| Chatterbox single default voice for ru/pl without clone | Model has no presets | Force clone always — too slow/heavy as default |
| Optional ffmpeg for mp3/`--fit` | Already required by extract | Pure-python mp3 encoder — new dep |
