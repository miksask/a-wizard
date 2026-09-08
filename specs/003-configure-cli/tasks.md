# Tasks: Configure CLI

**Input**: Design documents from `/specs/003-configure-cli/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md

**Tests**: Included — constitution requires synthetic/mock coverage for freshness and resume.

## Phase 1: Setup

- [x] T001 Confirm feature docs exist under `specs/003-configure-cli/` (spec, plan, research, data-model, contracts, quickstart)

---

## Phase 2: Foundational

- [x] T002 Add `asr_config` branch to `mark_stale_downstream` in `src/a_wizard/domain/freshness.py` (mixdown: transcribe:mix + attribute + merge + minimize; per-track: active transcribe:N + merge + minimize)
- [x] T003 [P] Unit-test `asr_config` invalidation and no-op unchanged stages in `tests/unit/test_domain.py`

---

## Phase 3: User Story 1 - Reconfigure a finished project (P1) 🎯 MVP

**Goal**: Interactive/programmatic configure updates settings, marks the right stages stale, does not run ASR.

**Independent Test**: Completed mixdown fixture; language change → transcribe:mix stale, extract fresh; following `run` redoes ASR only.

- [x] T004 [US1] Implement `WizardService.apply_configure` in `src/a_wizard/application/service.py` (compare language/prompt/modes; call `asr_config` / existing track keys; reset per-track status when ASR config changes)
- [x] T005 [US1] Add `a-wizard configure` in `src/a_wizard/cli/app.py` (resolve target, lock, interactive questions with current defaults, one save, summary + next `run`)
- [x] T006 [US1] Integration test: configure language then `run` redoes mix transcription and keeps extract digest in `tests/integration/test_pipeline.py`
- [x] T007 [US1] Integration test: plain↔diarized keeps mix ASR succeeded in `tests/integration/test_pipeline.py`

---

## Phase 4: User Story 2 - Non-interactive flags (P2)

**Goal**: Full flag set works without stdin; missing flags on non-TTY fail without guessing.

- [x] T008 [US2] Parse `--language`, `--prompt` / `--no-prompt`, repeatable `--track N:mode` in `src/a_wizard/cli/app.py`; skip flagged questions; non-TTY missing settings → usage/blocked
- [x] T009 [US2] Integration test: full flags exit 0; language-only without TTY fails in `tests/integration/test_pipeline.py`

---

## Phase 5: User Story 3 - Idempotent reconfigure (P3)

**Goal**: Identical settings do not stale stages; `run` stays Done.

- [x] T010 [US3] Guard `apply_configure` so unchanged language/prompt/modes call no invalidation in `src/a_wizard/application/service.py`
- [x] T011 [US3] Test no-op configure leaves succeeded stages and `run` done in `tests/integration/test_pipeline.py`

---

## Phase 6: Polish

- [x] T012 [P] Document `configure` in `README.md`
- [x] T013 Run `uv run pytest tests/unit/test_domain.py tests/integration/test_pipeline.py`

---

## Dependencies

- Setup → Foundational (T002/T003) → US1 (T004–T007) → US2/US3 can share `apply_configure`
- T008 extends T005; T010 is the no-op path of T004

## MVP

T001–T007: operator can reconfigure and resume with `run`.
