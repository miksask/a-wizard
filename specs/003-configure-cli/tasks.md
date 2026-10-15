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

## Phase 7: Amendment 2026-10-16 — any Whisper language and `auto` (US4)

**Goal**: Language question offers `auto` (default), `ru`, `en`, `other`; `other` accepts any Whisper language; `--language` accepts the same values.

**Independent Test**: Mock fixture; `other` + `German` stores `de` and stales ASR; `auto` reaches adapters as no forced language; unsupported input is rejected.

- [x] T014 [US4] Add `src/a_wizard/domain/languages.py`: bundled Whisper table, aliases, Russian names, `LANGUAGE_AUTO`, `DEFAULT_LANGUAGE="auto"`, `LEGACY_LANGUAGE="ru"`, `normalize_language()` raising `bad_language` with `difflib` suggestions
- [x] T015 [P] [US4] Unit tests in `tests/unit/test_languages.py`: code, name, alias, Russian name, case/whitespace, `auto`, unsupported + suggestions, `De` == `de`
- [x] T016 [P] [US4] Consistency test: bundled table equals `mlx_whisper.tokenizer.LANGUAGES` (`pytest.importorskip("mlx_whisper")`) in `tests/unit/test_languages.py`
- [x] T017 [US4] Use `normalize_language` in `WizardService.apply_configure` (`src/a_wizard/application/service.py`); replace `"ru"` fallbacks with the legacy/default constants (new project → `auto`, missing stored value → `ru`); set default in new-project defaults in `src/a_wizard/domain/models.py`
- [x] T018 [US4] Add `_prompt_language(current)` in `src/a_wizard/cli/app.py` (`auto`/`ru`/`en`/`other`, `other (current: X)`, re-ask on invalid) and use it in both the first-run gate and `_collect_configure`; normalize `--language`; update help and `next_step` text
- [x] T019 [US4] ASR adapters: helper mapping `auto` → `language=None`, used by `MlxWhisperAsrAdapter` and `FasterWhisperAsrAdapter` in `src/a_wizard/adapters/asr/engines.py`; update the `ports` default
- [x] T020 [P] [US4] Adapter tests with mocked `mlx_whisper` / `faster_whisper` (`sys.modules`): `auto` → `None`, `de` → `de`
- [x] T021 [P] [US4] Configure tests in `tests/application/test_configure.py`: `ru` → `de` stales ASR and keeps extract; `de` → `De` / `German` is a no-op; `ru` ↔ `auto` stales ASR
- [x] T022 [US4] Interactive prompt tests (mocked `input`): default `auto`; `other` → invalid → valid; `other (current: de)` + Enter keeps `de`
- [x] T023 [US4] Integration tests in `tests/integration/test_pipeline.py`: `configure --language German` stores `de`; `--language klingon` exits 2 and saves nothing; legacy manifest with `ru` is unchanged
- [x] T024 [P] [US4] Docs: `README.md` (language options, `auto`, `per_track` vs `mixdown` detection note), `specs/001-multitrack-asr-wizard/contracts/manifest.schema.json` language description
- [x] T025 [US4] Run `uv run pytest` and `./scripts/quality-gate.sh`

---

## Dependencies

- Setup → Foundational (T002/T003) → US1 (T004–T007) → US2/US3 can share `apply_configure`
- T008 extends T005; T010 is the no-op path of T004

- Amendment: T014 → T015/T016/T017/T019 → T018 → T020–T023 → T024/T025. T017 and T019 are independent of each other; T018 needs T014.

## MVP

T001–T007: operator can reconfigure and resume with `run`.
Amendment MVP: T014, T017–T019, T021.
