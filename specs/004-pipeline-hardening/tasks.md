# Tasks: Pipeline Hardening

**Input**: Design documents from `/specs/004-pipeline-hardening/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Synthetic/mock only; ffmpeg required for full quality gate.

## Phase 1: Setup

- [x] T001 Create Spec Kit docs under `specs/004-pipeline-hardening/` and point `.specify/feature.json` at it; update AGENTS.md/README pointers

---

## Phase 2: Foundational freshness

- [x] T002 Add stage contracts + digest alias helpers in `src/a_wizard/domain/freshness.py`
- [x] T003 [P] Implement `src/a_wizard/application/reconciliation.py` (signatures, paths, digests → stale)
- [x] T004 Wire reconcile into `WizardService` before run/status/plan under lock; save only on change
- [x] T005 Normalize new `output_digests` to path keys in stage success writers
- [x] T006 Unit tests for reconciliation (missing file, digest mismatch, idempotent no-op, legacy keys)

---

## Phase 3: US2 Lazy adapters + identity

- [x] T007 Metadata-only `ServiceConfig` / lazy ASR+diar resolution in `application/service.py`
- [x] T008 CLI: metadata-only for status/plan/configure/track/speakers; processing for run/stage/init
- [x] T009 Reconcile adapter identity changes → targeted invalidation before planning
- [x] T010 Tests: status without resolving real adapters; adapter change stales dependents

---

## Phase 4: US3 Energy cache

- [x] T011 Versioned energy cache + atomic write in `application/attribution.py`
- [x] T012 Unit tests: hit, miss on digest/window, corrupt npy

---

## Phase 5: Contracts + fingerprint

- [x] T013 Update `specs/002-mlx-mixdown-pipeline/contracts/segments.schema.json` to ms form; keep 004 copy in sync
- [x] T014 Add `jsonschema` to dev extras; contract tests for manifest/mix/dialog/energy sidecar
- [x] T015 Stronger source fingerprint in `adapters/media/ffmpeg.py` + unit coverage

---

## Phase 6: US4 Local gate + privacy

- [x] T016 Fix `.gitignore` for `records` symlink; hygiene script
- [x] T017 Fix all Ruff violations
- [x] T018 Add `scripts/quality-gate.sh`, `scripts/check-repo-hygiene.sh`, hooks; document in README
- [x] T019 Coverage fail_under ≥70% in pytest config

---

## Phase 7: Polish

- [x] T020 Integration regressions in `tests/integration/test_pipeline.py`
- [x] T021 Run full quality gate; mark tasks complete only after green

## MVP

T001–T006 + T011–T012: verifiable freshness and safe energy cache.
