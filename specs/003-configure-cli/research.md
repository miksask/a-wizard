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

## 5. Language choice beyond `ru` / `en` (amendment 2026-10-16)

**Decision**: Menu `auto` / `ru` / `en` / `other`. `other` takes free text, accepted as a Whisper code, English name or alias, or a supported Russian name. Input is normalized to the canonical Whisper code and stored; unsupported input is rejected with `difflib` close matches. `auto` is stored literally and translated to `language=None` by the ASR adapters. `--language` accepts the same values.

**Rationale**:
- `faster-whisper` accepts only codes, while `mlx-whisper` also accepts names, so normalizing to a code works for both adapters.
- Normalizing before storing and comparing means `De` / `German` / `de` produce one freshness hash and never trigger a spurious re-transcription.
- The language table is bundled because `mlx-whisper` / `faster-whisper` are optional extras; validation must work in tests and in `configure` without them. A consistency test against `mlx_whisper.tokenizer.LANGUAGES` (skipped when not installed) guards against drift.
- `auto` is first and the default for new projects: when the operator has not decided, detection is safer than a forced wrong language. Existing manifests keep their stored language; a manifest with no stored value is still read as `ru` so older projects behave as before.
- One shared prompt function replaces the two duplicated `ru|en` prompts (first-run gate and `configure`).

**Caveats**:
- `per_track` + `auto`: each track is detected independently and may disagree. `mixdown` detects once on the mix. Documented in the README.
- The initial prompt is not translated when the language changes; the operator owns it.

**Alternatives considered**:
- Free-text passthrough without validation — a typo would fail late inside the ASR adapter, after the operator has left.
- Warn-and-accept for unknown languages — same late-failure risk; rejected by the operator.
- Language list read from `mlx_whisper` at runtime — breaks validation when the optional extra is absent.
- Keeping `ru` as the default for new projects — rejected by the operator in favor of `auto`.
