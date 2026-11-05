# Tasks: Speak (TTS)

**Input**: Design documents from `/specs/006-speak/`

## Phase 1: Setup

- [x] T001 Create `specs/006-speak` artifacts (spec, research, plan, data-model, contracts, tasks); point `.specify/feature.json` at 006; update `AGENTS.md` and constitution 1.2.0
- [x] T002 Add `tts` optional-dependency in `pyproject.toml`; omit real TTS adapter from coverage

## Phase 2: Foundational

- [x] T003 [P] Add `src/a_wizard/domain/speech.py` (`SpeechLine`, `SpeechScript`, `detect_lang`, sentence chunking)
- [x] T004 [P] Add `TtsEngine` Protocol to `src/a_wizard/ports/__init__.py`
- [x] T005 [P] Add `src/a_wizard/adapters/tts/fake.py` and package `__init__.py`
- [x] T006 Add `src/a_wizard/adapters/tts/registry.py` (defaults + env/yaml/flag override order)
- [x] T007 Add `src/a_wizard/adapters/tts/mlx_audio.py` (lazy load, model cache, Kokoro/Chatterbox/generic)

## Phase 3: User Story 1+2 — speak project & txt (P1)

- [x] T008 Implement loaders, voice assignment, sequential render, cache, `speech.json` in `src/a_wizard/application/speak.py`
- [x] T009 Wire `a-wizard speak` and doctor mlx-audio check in `src/a_wizard/cli/app.py`
- [x] T010 Unit tests: lang detect, parsers, cache key, sequential render (`tests/unit/test_speech.py`, `test_speak_render.py`)
- [x] T011 Application tests: mock speak project + txt (`tests/application/test_speak.py`)

## Phase 4: User Story 3–5 — timeline, models, clone (P2)

- [x] T012 Timeline renderer + `--fit` atempo via ffmpeg
- [x] T013 Registry override tests (`tests/unit/test_tts_registry.py`)
- [x] T014 Clone ref extraction from project tracks + `--ref` override
- [x] T015 Chatterbox no-presets warning; `--list-voices`

## Phase 5: Polish

- [x] T016 README Speak section
- [x] T017 Optional `@pytest.mark.slow` mlx smoke (`tests/integration/test_speak_mlx.py`)
- [x] T018 Checklist pass: constitution, no PII in logs, DAG unchanged

## Dependencies

T001 → T002 → (T003–T007) → T008 → T009 → tests. T012–T015 after T008. T016–T018 last.

## Parallel opportunities

T003, T004, T005 can run in parallel after T002. T010 and T013 after T008/T006.
