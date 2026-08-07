# Implementation Plan: Multitrack ASR Wizard

**Branch**: `001-multitrack-asr-wizard` | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)

## Summary

The local `a-wizard` CLI implements a resume-safe multitrack ASR pipeline with a typed manifest, freshness signatures, replaceable media/ASR/diarization adapters, and canonical `dialog.json` → minimize output.

## Technical Context

**Language/Version**: Python 3.13  
**Primary Dependencies**: uv, Typer, Rich, PyYAML, ffmpeg/ffprobe; optional faster-whisper, whisperx  
**Storage**: Filesystem project dir + versioned YAML manifest  
**Testing**: pytest (+ coverage), synthetic fixtures, mock adapters  
**Target Platform**: macOS / Linux CLI  
**Project Type**: single-package CLI  
**Performance Goals**: Correct resume; avoid redundant heavy stages  
**Constraints**: Local-only; no telemetry; no secrets in state/logs  
**Scale/Scope**: Typical 1–6 tracks; interview-length recordings

## Constitution Check

- Local-first privacy: PASS (env tokens, redacted logs)
- Atomic resume: PASS (lock + atomic write design)
- Verifiable freshness: PASS (signatures)
- Ports/adapters: PASS (Protocol registry)
- Synthetic tests: PASS (planned fixtures)

## Project Structure

### Documentation (this feature)

```text
specs/001-multitrack-asr-wizard/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── manifest.schema.json
│   └── segments.schema.json
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root of a-wizard)

```text
src/a_wizard/
├── domain/           # models, dag, freshness, invariants
├── application/      # planner, executor, use cases
├── ports/            # Protocols
├── adapters/
│   ├── media/
│   ├── asr/
│   ├── diarization/
│   ├── persistence/
│   └── terminal/
└── cli/              # Typer app

tests/
├── unit/
├── application/
├── contract/
├── integration/
└── fixtures/
```

**Structure Decision**: Single Python package with hexagonal layers under `src/a_wizard`.

## Complexity Tracking

No constitution violations requiring justification.
