# Research: Configure CLI

## 1. How to re-enter settings without breaking resume

**Decision**: Dedicated `configure` command that only writes settings and freshness. `run` stays the resume driver.

**Rationale**: First-run gates (`initial_prompt_reviewed`, track `pending`) fire once. Resetting those flags inside `run` would surprise operators who only wanted to resume. A separate command makes reconfigure explicit.

**Alternatives considered**:
- `run --reconfigure` — mixes human gates with pipeline execution; harder to script.
- `init --force` — destroys extract artifacts; too expensive.
- Hand-edit `manifest.yaml` — no invalidation; `run` stays `Done`.

## 2. Invalidation key for language / prompt

**Decision**: Add `mark_stale_downstream(project, "asr_config")`. Mixdown: stale `transcribe:mix` + attribute + merge + minimize. Per-track: stale each active `transcribe:N` + merge + minimize, and reset those tracks from `transcribed` to `extracted` so the DAG re-enters transcription.

**Rationale**: 001/002 already specify this matrix; the code only marked stale from `set_track_mode` / speakers. Planner uses `status == succeeded`, so signature mismatch alone is not enough — status must become `stale`.

**Alternatives considered**:
- Compare signatures inside `detect_next_action` — larger change, out of scope.
- Always force `stage transcribe-mix` from configure — violates “configure does not run ASR” and wastes work on no-op.

## 3. Non-interactive policy

**Decision**: Flags `--language`, `--prompt` / `--no-prompt`, repeatable `--track N:mode`. If stdin is not a TTY, every setting not supplied by flags is a usage/blocked error. No `obs-interview` preset on configure.

**Rationale**: Matches constitution: non-interactive auto-config only via explicit preset on `run`, never by guessing. Scripts that only change language still pass the full current track set.

**Alternatives considered**:
- Unspecified flags keep current values even without a TTY — convenient but contradicts spec US2 (missing track modes must fail).
- Reuse `--preset obs-interview` — would overwrite intentional skip/diarize choices.

## 4. Interactive defaults

**Decision**: Reuse the first-run question order and copy. Current stored values are the defaults. Collect all answers, then save once so Ctrl+C before save is a no-op.

**Rationale**: Matches FR-004 and the interrupt edge case.

**Alternatives considered**: Save after each question — can leave a half-configured skipped set.
