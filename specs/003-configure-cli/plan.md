# Implementation Plan: Configure CLI

**Branch**: `003-configure-cli` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-configure-cli/spec.md`

## Summary

Add `a-wizard configure TARGET` so an operator can re-enter project language, Whisper prompt, and track modes on an existing project. Configure writes the manifest, marks only dependent stages stale, and does not run ASR. A following `a-wizard run` resumes from the first stale stage.

Technical approach: extend `mark_stale_downstream` with an `asr_config` change key; add `WizardService.apply_configure` that compares current vs requested settings and invalidates accordingly; add a Typer command that collects settings interactively or from flags, then calls the service under the project lock.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Typer CLI, existing `a_wizard` domain/application layers (no new packages)

**Storage**: Existing project directory + atomic YAML manifest

**Testing**: pytest, synthetic ffmpeg fixtures, mock ASR/diar adapters

**Target Platform**: macOS and Linux (same as v1)

**Project Type**: local CLI

**Performance Goals**: Configure completes in seconds (no media work)

**Constraints**: Local-first; no secrets or full prompt text in JSONL logs; project lock; no guessed presets

**Scale/Scope**: One new command, one freshness key, reuse of existing track-mode setter

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Local-First Privacy**: Configure does not log full prompt, transcript, or tokens. Pass.
- **II. Resume-Safe Atomic State**: Single atomic manifest save after all answers collected; lock held for the update. Pass.
- **III. Verifiable Freshness**: Language/prompt changes invalidate transcription + downstream via `asr_config`; channel-role and skipped-set reuse existing keys. No-op leaves stages succeeded. Pass.
- **IV. Ports and Adapters**: No new media/ASR/diar adapters. Pass.
- **V. Synthetic Tests First**: Tests use mock engines and short ffmpeg fixtures only. Pass.

Post-design re-check: unchanged. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/003-configure-cli/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/cli.md
└── tasks.md
```

### Source Code (repository root)

```text
src/a_wizard/
  domain/freshness.py          # + asr_config invalidation
  application/service.py       # + apply_configure
  cli/app.py                   # + configure command

tests/
  unit/test_domain.py          # + asr_config / no-op
  integration/test_pipeline.py # + configure then run
```

**Structure Decision**: Extend the existing single-package CLI. No new modules unless `apply_configure` grows beyond service.py.

## Complexity Tracking

None.
