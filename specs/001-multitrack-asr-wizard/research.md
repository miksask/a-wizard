# Research: Multitrack ASR Wizard

**Feature**: 001-multitrack-asr-wizard | **Date**: 2026-08-06

## Decisions

### D1. Hexagonal architecture without dynamic plugins (v1)
- **Decision**: Domain/application + Protocol ports + built-in adapter registry.
- **Rationale**: ASR/diarization must be replaceable and testable without the complexity of entry points.
- **Alternatives**: A legacy-style monolith; a full plugin system (deferred).

### D2. Typed versioned YAML manifest + atomic filesystem
- **Decision**: `manifest.yaml` schema version 2 as snapshot; temp→replace; project lock.
- **Rationale**: Familiar UX and sufficient for a single-writer CLI; SQLite/event sourcing would be excessive.
- **Alternatives**: SQLite, append-only event log.

### D3. Freshness by signatures/digests
- **Decision**: Stage fresh iff signature matches and outputs exist/valid.
- **Rationale**: Fixes legacy stale `done` after reconfigure/re-transcribe.
- **Alternatives**: Manual status flags (rejected).

### D4. Canonical structured dialog.json
- **Decision**: Merge writes JSON first; txt/minimize/spk_* derived from it.
- **Rationale**: Avoids re-parsing text; stable machine contract.
- **Alternatives**: Text-first like legacy.

### D5. Independent ASR and diarization ports
- **Decision**: `TranscriptionEngine` and `DiarizationEngine` separate; attribution in application.
- **Rationale**: Allows swapping backends; WhisperX can implement both or only one.
- **Alternatives**: Single combined diarized pipeline only.

### D6. Default backends
- **Decision**: faster-whisper (plain), WhisperX+pyannote 3.1 (diar); optional extras.
- **Superseded (2026-08-06)**: Feature [002-mlx-mixdown-pipeline](../002-mlx-mixdown-pipeline/research.md) replaces Apple Silicon defaults with mlx-whisper + FluidAudio/sherpa-onnx and mixdown mode. WhisperX is removed.
- **Rationale**: Proven in legacy; optional install keeps base lightweight.
- **Alternatives**: mlx-whisper, openai API — future adapters.

### D7. CLI surface with Typer
- **Decision**: Typer + Rich for UX; argparse-like exit discipline.
- **Rationale**: Subcommands, `--json`, testing friendliness.
- **Alternatives**: Plain argparse (legacy).

### D8. Non-interactive policy
- **Decision**: `--preset obs-interview`; block raw speakers unless `--allow-raw-speakers`.
- **Rationale**: Avoid silent wrong roles from track-index guessing.
- **Alternatives**: Legacy `--yes` defaults.

### D9. Track-scoped speaker IDs
- **Decision**: Canonical ids `SPEAKER_T{n}` (plain) and `SPEAKER_T{n}D{k}` (diarized), using native 0-based track and diarizer voice indices. Short glyphs `STn` / `STnDk`. No interactive role-mapping gate.
- **Rationale**: Avoids cross-track `SPEAKER_00` collision and removes custom-name UX.
- **Alternatives**: Previous `T{n}/SPEAKER_XX` + free-form roles (superseded).

### D10. Integer millisecond timestamps
- **Decision**: Store/start/end as int ms; format for display.
- **Rationale**: Deterministic ordering and hashing.
- **Alternatives**: float seconds (legacy).

## Spikes resolved

| Topic | Outcome |
|-------|---------|
| Legacy compatibility | Behavioral parity only; no in-place v1 manifest read |
| Device policy | auto→cuda if available else cpu; no MPS guarantee for WhisperX |
| Token handling | env only (`HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`) |
| Overlap dedup | Out of scope v1 |
| Model cache | In-process per run; no cross-process shared cache required |

## Open risks

- WhisperX/Apple Silicon reliability → document CPU fallback.
- First-run model download latency → warn before heavy stages.
- Non-deterministic ASR → tests use mocks; real engines opt-in slow.
