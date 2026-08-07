# Tasks: Multitrack ASR Wizard

**Input**: Design documents from `/specs/001-multitrack-asr-wizard/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Phase 1: Setup

- [x] T001 Create package layout under `src/a_wizard/` and `tests/`
- [x] T002 Initialize `pyproject.toml` (Python 3.13, typer, pyyaml, optional asr/diar extras)
- [x] T003 [P] Add README.md, .python-version, .gitignore for a-wizard

## Phase 2: Foundational

- [x] T004 Implement domain models in `src/a_wizard/domain/models.py`
- [x] T005 [P] Implement DAG + freshness in `src/a_wizard/domain/dag.py` and `freshness.py`
- [x] T006 [P] Implement errors/exit codes in `src/a_wizard/domain/errors.py`
- [x] T007 Implement ports in `src/a_wizard/ports/`
- [x] T008 Implement atomic persistence + lock in `src/a_wizard/adapters/persistence/`
- [x] T009 Implement JSONL logging observer in `src/a_wizard/adapters/persistence/logging.py`
- [x] T010 Wire application planner/executor skeletons in `src/a_wizard/application/`

## Phase 3: User Story 1 — End-to-end (P1)

- [x] T011 [P] [US1] Media ffmpeg adapter in `src/a_wizard/adapters/media/ffmpeg.py`
- [x] T012 [P] [US1] Mock + faster-whisper ASR adapters
- [x] T013 [P] [US1] Mock + WhisperX diarization adapters
- [x] T014 [US1] Merge/minimize services in `src/a_wizard/application/dialog.py`
- [x] T015 [US1] `run` orchestration producing project artifacts
- [x] T016 [US1] Unit/integration tests with mock adapters for full pipeline

## Phase 4: User Story 2 — Resume (P1)

- [x] T017 [US2] Persist stage attempts and resume from next action
- [x] T018 [US2] SIGINT handling → exit 130 + resume hint
- [x] T019 [US2] Tests for interrupt/resume and status-only idempotency

## Phase 5: User Story 3 — Modes & speakers (P1)

- [x] T020 [US3] Track mode configuration use case + CLI `track set`
- [x] T021 [US3] Speaker map review + track-scoped IDs
- [x] T022 [US3] Tests for plain/diarized/skipped and mapping

## Phase 6: User Story 4 — Status/plan/dry-run (P2)

- [x] T023 [US4] `status` and `plan` commands with JSON
- [x] T024 [US4] `--dry-run` single-step preview without mutations
- [x] T025 [US4] Tests verifying no file changes

## Phase 7: User Story 5 — Preset non-interactive (P2)

- [x] T026 [US5] `--preset obs-interview` and `--allow-raw-speakers`
- [x] T027 [US5] HF token gate (exit 3)
- [x] T028 [US5] Non-interactive tests

## Phase 8: User Story 6 — Stage rerun (P3)

- [x] T029 [US6] Invalidation matrix on config changes
- [x] T030 [US6] `stage run` command with selective rerun
- [x] T031 [US6] Tests speaker_map/glyphs stale behavior

## Phase 9: Polish

- [x] T032 `doctor` command
- [x] T033 Quickstart validation commands in README
- [x] T034 Mark tasks complete after suite green

## Parallel opportunities

- T004–T006 after T001
- T011–T013 after ports ready
- US4/US5 after foundational + US1 skeleton
