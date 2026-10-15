# Tasks: Multitrack Attribution

**Input**: Design documents from `/specs/005-multitrack-attribution/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Synthetic/mock only; ffmpeg required for the full quality gate.

## Phase 1: Setup

- [x] T001 Create Spec Kit docs under `specs/005-multitrack-attribution/`; point `.specify/feature.json`, AGENTS.md, CLAUDE.md at it

---

## Phase 2: Foundational

- [x] T002 `ActivityParams`, `CleanupParams` in `src/a_wizard/domain/activity.py`
- [x] T003 `normalize_diar_label`, robust `track_scoped_speaker`, `Word.silent/dropped` in `src/a_wizard/domain/models.py`; use the normalizer in FluidAudio and speakrs adapters
- [x] T004 Attribution/cleanup versions in `attribute_signature`, per-track `merge_signature`, `mixdown_signature`, `mix_asr_config`, `track_asr_config` (options only when enabled) in `src/a_wizard/domain/freshness.py`; `audio_cleanup` change key in `mark_stale_downstream`
- [x] T005 [P] Diarization cache in `src/a_wizard/application/diar_cache.py`; `MockDiarAdapter.cacheable = False`
- [x] T006 [P] Activity model in `src/a_wizard/application/activity.py` (two-pass floor, speech level, word evidence)
- [x] T007 [P] Crosstalk detection + compensation in `src/a_wizard/application/crosstalk.py`

---

## Phase 3: US1 Noise-robust attribution (P1) 🎯 MVP

- [x] T008 [US1] Rewrite `attribute_words` in `src/a_wizard/application/attribution.py`: gate, relative dominance, context resolution, legacy fallback, island smoothing, report
- [x] T009 [US1] Wire activity-based attribution + diar cache into `run_attribute` in `src/a_wizard/application/service.py`
- [x] T010 [US1] Unit tests: noisy mic vs digital silence, context resolution, islands, fallback in `tests/unit/test_attribution.py`; activity tests in `tests/unit/test_activity.py`

---

## Phase 4: US2 Several diarized tracks (P1)

- [x] T011 [US2] Overlap-based diarized speaker assignment with boundary context (mixdown + per-track) in `src/a_wizard/application/attribution.py`
- [x] T012 [US2] Tests: label normalization (`tests/unit/test_domain.py`), FluidAudio/speakrs parsing, two diarized tracks with colliding ids, boundary word

---

## Phase 5: US3 Rooms with crosstalk (P2)

- [x] T013 [US3] Use compensated profiles in attribution; crosstalk + noisy-track warnings in the report
- [x] T014 [US3] Tests: detection/compensation/no false positives (`tests/unit/test_crosstalk.py`), four rooms with gain differences and crosstalk in `tests/unit/test_attribution.py`

---

## Phase 6: US4 Hallucinations (P2)

- [x] T015 [US4] Isolated silent-run dropping with `dropped` flags; no drops in fallback
- [x] T016 [US4] Tests: isolated run dropped, adjacent word kept, silent fixture untouched

---

## Phase 7: US5 Per-track filter (P2)

- [x] T017 [US5] `run_transcribe` writes `transcripts/track_{n}.words.json`; overlap-based diarized assignment
- [x] T018 [US5] `filter_track_words` (hallucination, crosstalk, domination) + segment fallback; `run_merge` per_track uses it and writes `meta/track_filter.json`
- [x] T019 [US5] Tests in `tests/unit/test_track_filter.py` and per-track integration with crosstalk duplicates

---

## Phase 8: US6 Opt-in ASR cleanup (P3)

- [x] T020 [US6] `hallucination_silence_threshold` in ASR adapters and service calls
- [x] T021 [US6] Frame gains in `src/a_wizard/application/cleanup.py`; streamed mixer in `src/a_wizard/adapters/media/gain_mix.py`; gated mixdown and clean per-track WAV in service
- [x] T022 [US6] `WizardService.apply_options` + `a-wizard options` command; `Options:` status line
- [x] T023 [US6] Tests: signatures unchanged by defaults, invalidation, CLI, gains/mixer (`tests/unit/test_cleanup.py`, `tests/application/test_options.py`)

---

## Phase 9: Polish

- [x] T024 Contract tests for the attribution report and v2 segments schema; manifest schema documents new options
- [x] T025 Integration: noisy-mic mixdown end-to-end in `tests/integration/test_pipeline.py`
- [x] T026 README (attribution behavior, diagnostics, options); offline validation on local recordings
- [x] T027 Run the full quality gate; mark tasks complete only after green

## MVP

T002–T010: noise-robust attribution with versioned freshness.
