# Implementation Plan: Configure CLI

**Branch**: `003-configure-cli` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-configure-cli/spec.md`

## Summary

Add `a-wizard configure TARGET` so an operator can re-enter project language, Whisper prompt, and track modes on an existing project. Configure writes the manifest, marks only dependent stages stale, and does not run ASR. A following `a-wizard run` resumes from the first stale stage.

Technical approach: extend `mark_stale_downstream` with an `asr_config` change key; add `WizardService.apply_configure` that compares current vs requested settings and invalidates accordingly; add a Typer command that collects settings interactively or from flags, then calls the service under the project lock.

### Amendment 2026-10-16: any Whisper language and `auto`

The language question gains `auto` (first, default), `ru`, `en`, `other`. `other` takes a free-text language that is normalized to a Whisper code. Approach:

- New `domain/languages.py`: bundled Whisper language table, `LANGUAGE_AUTO`, `DEFAULT_LANGUAGE = "auto"` (new projects), `LEGACY_LANGUAGE = "ru"` (manifest without a stored value), and `normalize_language()` raising `UsageError(code="bad_language")` with `difflib` suggestions.
- `apply_configure` and `--language` call `normalize_language`; the ASR freshness hash already includes language, so normalization alone prevents spurious invalidation.
- One shared `_prompt_language()` in `cli/app.py` replaces the two duplicated `ru|en` prompts (first-run gate and `configure`).
- ASR adapters map `auto` → `language=None` via one helper; the manifest keeps `auto`.
- README documents `per_track` vs `mixdown` behavior of `auto`.
- Tests: normalization unit tests, configure invalidation, interactive prompt (mocked `input`), adapter language passthrough (mocked `mlx_whisper` / `faster_whisper`), and a consistency test against `mlx_whisper.tokenizer.LANGUAGES` (skipped if not installed).

No new packages. Constitution check unchanged (local-first, atomic state, verifiable freshness, ports unchanged, synthetic tests).

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
  domain/languages.py          # + Whisper language table, normalize_language (amendment)
  adapters/asr/engines.py      # + auto -> language=None (amendment)
  application/service.py       # + apply_configure (normalize language)
  cli/app.py                   # + configure command, shared _prompt_language

tests/
  unit/test_domain.py          # + asr_config / no-op
  unit/test_languages.py       # + normalization, table consistency (amendment)
  application/test_configure.py # + language change / same-code no-op
  integration/test_pipeline.py # + configure then run
```

**Structure Decision**: Extend the existing single-package CLI. No new modules unless `apply_configure` grows beyond service.py.

## Complexity Tracking

None.
