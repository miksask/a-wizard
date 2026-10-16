<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0
- Modified principles: none (I–V unchanged)
- Product Constraints: workflow chain no longer includes speaker review;
  fixed SPEAKER_T{n}/SPEAKER_T{n}D{k} ids; --allow-raw-speakers is CLI-compat only
- Added sections: none
- Removed sections: none
- Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ no change (no speaker-review wording)
  - .specify/templates/spec-template.md — ✅ no change
  - .specify/templates/tasks-template.md — ✅ no change
  - README.md — ✅ no change (already matches)
- Follow-up TODOs: none in constitution; historical 001/002 docs updated separately
-->

# a-wizard Constitution

## Core Principles

### I. Local-First Privacy
All processing runs locally. Secrets (HF_TOKEN and similar values) are supplied only through the environment or a secret provider, never through argv, the manifest, or logs. Logs never contain transcript text, full prompts, or tokens. Real media and PII are not committed to the repository.

### II. Resume-Safe Atomic State
Project state is the single source of truth. Every completed stage is recorded atomically (temp → replace). Interruptions (Ctrl+C) and errors leave the project in a valid state that can be resumed with the same command. A project lock prevents concurrent writers.

### III. Verifiable Freshness
`done` statuses alone are insufficient. Stage freshness is determined by a signature: normalized configuration + upstream artifact digests + algorithm version + adapter/model identity. Input changes automatically invalidate only dependent stages.

### IV. Ports and Adapters
The domain and application layers do not depend on ffmpeg, Whisper, WhisperX, or YAML. Media, ASR, and diarization are hidden behind Protocol ports. Heavy dependencies are imported only when an adapter is selected. Version 1 uses a built-in registry; dynamic plugins are optional.

### V. Synthetic Tests First
Automated tests use only synthetic segments, short ffmpeg fixtures, and mock adapters. Real interviews, WAV files, and tokens are excluded from normal CI. Adapter contract tests are identical for fake and real implementations.

## Product Constraints

- The primary v1 interface is a local interactive CLI.
- Functional parity with legacy asr-wizard workflows: extract → configure → transcribe → attribute → merge → minimize. There is no interactive role-mapping gate. Speaker ids are fixed: plain → `SPEAKER_T{n}`, diarized voice → `SPEAKER_T{n}D{k}`. An optional `speakers map` MAY remap them for display.
- Old v1 `manifest.yaml` files and exact legacy CLI flags are unsupported; familiar output filenames are retained.
- Non-interactive mode requires an explicit preset (`obs-interview`). `--allow-raw-speakers` is retained for CLI compatibility and does not change merge behavior.
- Target platforms are macOS and Linux; Windows support is not guaranteed.
- LLM post-processing (summary) is outside the v1 scope.

## Development Workflow

1. The specification and plan precede code (Spec Kit artifacts).
2. Domain invariants are covered by unit tests before ML integration.
3. CLI: stdout contains results, stderr contains progress/errors; exit codes are stable.
4. Human-facing UX, machine identifiers, and JSON keys are in English.
5. Before a resource-intensive stage, show the adapter/model/device and the risk of model downloads.

## Governance

The Constitution takes precedence over implementation convenience. Violations are documented with justification in the plan's Complexity Tracking section. Constitution changes require updating the amendment date and reviewing related specifications and plans.

**Version**: 1.1.0 | **Ratified**: 2026-08-06 | **Last Amended**: 2026-10-16
