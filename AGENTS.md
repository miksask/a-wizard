# AGENTS.md — a-wizard

This directory is a standalone `a-wizard` project organized with GitHub Spec Kit.

## Getting Started

1. Principles: `.specify/memory/constitution.md`
2. Specifications: `specs/001-multitrack-asr-wizard/`, `specs/002-mlx-mixdown-pipeline/`
3. Code: `src/a_wizard/`
4. Quickstart: `README.md`

## Spec Kit Commands (Cursor / Claude)

Skills are installed in `.cursor/skills/` and `.claude/skills/` (`speckit-constitution`, `speckit-specify`, …).

Active feature: `specs/002-mlx-mixdown-pipeline` (see `.specify/feature.json`).

## Rules

- Do not commit real media, transcripts containing PII, or `HF_TOKEN`.
- Tests must use only synthetic data and mock adapters.
- Legacy code in the parent `whisper/pipeline` is a behavioral reference only; do not import it.
- On Apple Silicon: ASR = mlx-whisper, diarization = FluidAudio/sherpa-onnx; WhisperX has been removed.
- Default mode: `processing_mode=mixdown` (one ASR pass on the mix plus energy attribution).
