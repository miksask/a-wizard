# Feature Specification: Configure CLI

**Feature Branch**: `003-configure-cli`

**Created**: 2026-08-28

**Status**: Implemented (amended 2026-10-16: any Whisper language and `auto`, also implemented)

**Input**: User description: "Add `a-wizard configure` so an operator can re-enter project settings (prompt, language, track modes) on an existing project, invalidate only dependent stages, and then resume transcription with `run`. Configure must not start ASR itself."

**Amendment (2026-10-16)**: "The wizard offers only `ru`/`en`. Add an `other` option where the operator types the language themselves. `auto` (Whisper language detection) is the first option and the default."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reconfigure a finished project (Priority: P1)

The operator finished a recording, then decides the language, Whisper prompt, or channel modes were wrong. They run `a-wizard configure` on the existing project (or its source video). The system asks again for project prompt, language, and each track’s mode, using the current values as defaults. After save, dependent pipeline stages become stale. Extracted audio is left untouched. Configure does not transcribe, mix, merge, or minimize. The operator then runs `a-wizard run` on the same project to resume from the first stale stage.

**Why this priority**: Without a second pass through settings, the only recovery is hand-editing the manifest or destroying the project. Wrong language or prompt is a common cause of unusable transcripts.

**Independent Test**: On a completed two-track mixdown fixture with mock engines, interactive configure changes language; status/plan then show transcription (not extract) as next; a following `run` redoes transcription and later stages and leaves extract artifacts unchanged.

**Acceptance Scenarios**:

1. **Given** a completed project with reviewed prompt and configured tracks, **When** the operator runs `configure`, **Then** they are asked for prompt, language, and every track mode, and current values are offered as defaults.
2. **Given** configure saves a different language or prompt, **When** configure exits, **Then** mix transcription (mixdown mode) or per-track transcription (per-track mode) and all downstream stages are stale, while extract and existing track WAV files remain fresh.
3. **Given** configure has finished, **When** the operator inspects output, **Then** no transcription, mixdown, merge, or minimize work ran during configure, and the next suggested command is `run` on that project.
4. **Given** a video path whose `.project` already exists, **When** `configure` is given that video path, **Then** it configures the existing project the same way as when given the `.project` directory.

---

### User Story 2 - Non-interactive flags for scripts (Priority: P2)

In automation, the operator sets language, prompt, and track modes without answering prompts. They pass `--language`, `--prompt` or `--no-prompt`, and `--track N:mode` as needed. When every required setting is supplied, configure completes with no stdin. When stdin is not a terminal and a required setting is missing, configure fails with a usage/blocked error and does not guess modes or language (no implicit interview preset).

**Why this priority**: Scripts and CI cannot use the interactive gates; guessing would violate the existing non-interactive policy.

**Independent Test**: A completed fixture configured with a full flag set and no stdin exits 0; the same fixture with missing track modes and no TTY exits non-zero without writing guessed modes.

**Acceptance Scenarios**:

1. **Given** `--language en --no-prompt --track 0:diarized --track 1:skipped` on a two-track project, **When** configure runs without stdin, **Then** it exits 0, persists those settings, and applies the invalidation rules.
2. **Given** a flag that covers language but not track modes, **When** stdin is not a terminal, **Then** configure exits with a usage or blocked code and does not invent track modes.
3. **Given** flags for some questions and a terminal, **When** configure runs, **Then** flagged questions are skipped and remaining questions are asked interactively.

---

### User Story 3 - Idempotent reconfigure (Priority: P3)

The operator runs configure again and confirms the same prompt, language, and track modes already stored. No stage becomes stale. A following `run` reports the pipeline complete and does not redo work.

**Why this priority**: Accidental re-entry must not cost another full transcription.

**Independent Test**: Configure a completed fixture with flags that match the current manifest; all previously succeeded stages stay succeeded; `run` reports done without rewriting transcription artifacts.

**Acceptance Scenarios**:

1. **Given** a completed project, **When** configure persists identical language, prompt, and track modes, **Then** no stage is marked stale.
2. **Given** that no-op configure, **When** `run` is invoked, **Then** the next action is done and transcription artifacts are unchanged.

---

### User Story 4 - Choose any Whisper language (Priority: P2)

Today the project language question offers only `ru` and `en`. The operator needs other languages (for example German or Polish) or wants Whisper to detect the language itself. The language question lists `auto`, `ru`, `en`, and `other`, in that order. `auto` is selected by default. Choosing `other` asks the operator to type a language, either as a Whisper language code (`de`) or as a name (`German`, `немецкий`). The system normalizes the input to a Whisper language code, stores the code, and re-asks if the input is not a supported language. The same values work in non-interactive mode via `--language`.

**Why this priority**: Recordings in languages other than Russian and English currently cannot be configured without hand-editing the manifest. A wrong forced language is a common cause of unusable transcripts, and `auto` is the safest default when the operator has not decided.

**Independent Test**: On a mock-engine fixture, interactive configure choosing `other` and typing `German` stores `de` and stales transcription; typing an unsupported name is rejected and re-asked; `configure --language auto` stores `auto`; the ASR adapter receives no forced language for `auto`.

**Acceptance Scenarios**:

1. **Given** the language question is shown, **When** the operator sees the options, **Then** they are `auto`, `ru`, `en`, `other` in that order, and `auto` is the default for a project that has no explicitly chosen language.
2. **Given** the operator chooses `other` and enters `German`, `german`, `de`, or `немецкий`, **When** configure saves, **Then** the stored project language is `de`.
3. **Given** the operator chooses `other` and enters an unsupported language, **When** the input is validated, **Then** an error with close-match suggestions is shown and the question is asked again (interactive), or configure exits with a usage error (via `--language`).
4. **Given** the project language is `auto`, **When** transcription runs, **Then** Whisper detects the language (no language is forced).
5. **Given** the stored language is `de` and the operator re-runs configure, **When** the language question is shown, **Then** it is shown as `other (current: de)` and is the default; pressing Enter keeps `de`.
6. **Given** the stored language is `de`, **When** configure is given `--language De` or `--language German`, **Then** no stage becomes stale (same normalized value).

---

### Edge Cases

- Language entered in different case or with surrounding whitespace (`De `, `GERMAN`) → normalized; no spurious invalidation.
- Language `auto` ↔ explicit code (`auto` → `ru`, `ru` → `auto`) counts as a language change and stales transcription and downstream stages.
- Empty input at the `other` prompt: keeps the current language when it is a non-standard code; otherwise asks again.
- Unsupported language via `--language` in non-interactive mode → usage error, nothing is saved.
- Project manifest created before this amendment with `language: ru` or `en` keeps that value; the new default `auto` applies only to projects that have no stored language choice.
- `auto` in `per_track` mode → each track is detected independently and may yield different languages; `mixdown` mode detects once on the mix. This is documented in the README.
- Target is not a video or an existing project → usage error, same class as `run`/`status`.
- Project directory has no manifest (not initialized) → usage error; configure does not create a project.
- Another command holds the project lock → lock error, same class as `run`.
- Operator interrupts configure (Ctrl+C) before save → previous settings remain; no partial track-mode update is committed.
- All tracks set to skipped → settings are saved; mixdown-related stages become stale per the skipped-set rule; configure still does not run mixdown (a later `run` may then fail with the existing empty-mix error).
- Mixdown vs per-track project → invalidation targets the transcription stages of that mode (mix vs per-track), not both.
- Prompt is cleared (`--no-prompt` or interactive disable) after a previous non-empty prompt → treated as an ASR-config change (stale transcription + downstream).
- Track count is zero (should not occur after a valid init) → usage error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide `a-wizard configure TARGET`, where TARGET is a video file or a `.project` directory, resolved the same way as `run` and `status`.
- **FR-002**: Configure MUST require an already initialized project. It MUST NOT create a project, extract audio, or modify source media.
- **FR-003**: Configure MUST acquire the project lock for the duration of the update and persist the manifest atomically.
- **FR-004**: In interactive mode, configure MUST re-ask, in order: (1) project Whisper initial prompt — leave unchanged, disable, or enter custom text; (2) project language — `auto`, `ru`, `en`, or `other` (see FR-015..FR-018); (3) each track mode — `plain`, `diarized`, or `skipped` (with optional skip reason). Current stored values MUST be the defaults.
- **FR-005**: Configure MUST support non-interactive overrides: `--language <code|name|auto>` (any supported Whisper language, see FR-016), `--prompt TEXT`, `--no-prompt`, and repeatable `--track N:mode` (`plain`|`diarized`|`skipped`). A supplied flag MUST skip the corresponding interactive question.
- **FR-006**: When stdin is not a terminal, every setting not supplied by flags MUST cause a usage or blocked failure. Configure MUST NOT apply an interview preset or otherwise guess missing modes or language.
- **FR-007**: Configure MUST NOT run extract, mixdown, transcription, attribution, merge, or minimize. After a successful save it MUST print a short settings summary and the next command (`run` on that project).
- **FR-008**: Changing project language or initial prompt MUST mark mix transcription (mixdown) or each active-track transcription (per-track) and all downstream stages stale. Extract and mix WAV MUST remain fresh when only language or prompt changed.
- **FR-009**: Changing a track between `plain` and `diarized` without changing which tracks are skipped MUST mark attribution (mixdown) or that track’s transcription (per-track), plus merge and minimize, stale. Mix transcription MUST remain fresh in mixdown mode.
- **FR-010**: Changing which tracks are skipped MUST mark mixdown, mix transcription, and downstream stages stale in mixdown mode (the mix contents change). In per-track mode, skipped-set changes MUST stale merge and minimize (and any newly active track still pending transcription).
- **FR-011**: If language, prompt, and all track modes are unchanged, configure MUST NOT mark any stage stale.
- **FR-012**: After configure, `status` and `plan` MUST report stale stages and the correct next action so a subsequent `run` resumes from the first stale or incomplete stage.
- **FR-013**: JSONL run logs MUST NOT contain the full prompt text, transcript text, or secrets. Interactive UI MAY show the current prompt so the operator can confirm it.
- **FR-014**: Configure MUST use the same stable exit-code classes as the rest of the CLI (success, usage, blocked, lock/corrupt, interrupt).
- **FR-015**: The interactive language question MUST list `auto`, `ru`, `en`, `other` in that order. The default is the currently stored language: `auto` for a project with no stored language choice; the matching item for a stored `auto`, `ru`, or `en`; `other (current: <code>)` for any other stored code. The same question MUST be used by the first-run gate in `run` and by `configure`.
- **FR-016**: Choosing `other` (interactive) or passing `--language` (non-interactive) MUST accept a Whisper language code, an English Whisper language name or alias, or a supported Russian language name, case-insensitive and whitespace-trimmed. The value MUST be normalized to the canonical Whisper language code before it is stored or compared. `auto` is accepted as a special value.
- **FR-017**: An input that does not match a supported Whisper language MUST be rejected with a `bad_language` usage error that suggests close matches. In interactive mode the question MUST be re-asked; in non-interactive mode nothing is saved. Validation MUST NOT require ASR packages to be installed (the language table is bundled).
- **FR-018**: A stored language of `auto` MUST cause the ASR adapter to run Whisper language detection (no forced language). The manifest MUST store the literal `auto`; adapters translate it at call time. Changing the stored language, including to or from `auto`, MUST follow FR-008. Normalizing to the same code MUST NOT stale any stage (FR-011).
- **FR-019**: New projects MUST default to `auto`. Existing manifests keep their stored language; a manifest with no stored language MUST continue to be read as `ru` so older projects do not change behavior.

### Key Entities

- **Project**: Existing artifact directory and typed manifest; configure only updates settings and stage freshness.
- **Transcription defaults**: Project-level language (`auto` or a Whisper language code) and initial prompt used by ASR.
- **Whisper language table**: Bundled mapping of Whisper language code → English name, plus aliases (for example `castilian`) and a small set of Russian names; used only for validation and normalization.
- **Track mode**: `plain`, `diarized`, or `skipped` for each audio channel.
- **Stage freshness**: Succeeded vs stale for extract, mixdown, transcription, attribute, merge, minimize; stale means `run` must redo that stage.

### Invalidation matrix (configure)

| Change | Mixdown: stale | Per-track: stale | Kept fresh |
|--------|----------------|------------------|------------|
| Language or prompt | mix transcription + attribute + merge + minimize | each active `transcribe:N` + merge + minimize | extract; mix WAV |
| `plain` ↔ `diarized` (skipped set unchanged) | attribute + merge + minimize | that track’s transcription + merge + minimize | extract; mix transcription (mixdown) |
| Skipped set changed | mixdown + mix transcription + attribute + merge + minimize | merge + minimize (+ newly active tracks still need transcription) | extract |
| No effective change | none | none | all previously succeeded stages |

Force-rerunning transcription without a settings change remains the existing single-stage command (`stage` transcribe-mix / transcribe). That path is out of scope for this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a completed two-track mixdown fixture, changing language via configure then running the project redoes transcription and later stages and does not redo extract (extract artifact identity unchanged).
- **SC-002**: On a completed mixdown fixture, changing only one channel from plain to diarized (skipped set unchanged) leaves mix transcription artifacts unchanged and still refreshes speaker attribution and dialog output on the next `run`.
- **SC-003**: A non-interactive configure that supplies language, prompt policy, and a mode for every track completes without reading stdin and exits successfully.
- **SC-004**: A no-op configure (identical settings) followed by `run` reports the pipeline complete and does not rewrite transcription artifacts.
- **SC-005**: Automated tests for this feature use only synthetic fixtures and mock engines (no real recordings, tokens, or network).
- **SC-006**: Configuring `German`, `german`, and `de` (interactive `other` or `--language`) all store `de`; repeating with a different spelling afterwards stales nothing.
- **SC-007**: An unsupported language is rejected with suggestions and never reaches the manifest or an ASR adapter.
- **SC-008**: With language `auto`, the ASR adapters are called without a forced language; with `de`, they receive `de`.
- **SC-009**: The bundled Whisper language table matches `mlx_whisper.tokenizer.LANGUAGES` whenever `mlx_whisper` is installed (consistency test; skipped when it is not installed).

## Assumptions

- This feature extends the command list from 001 (FR-010). Specs 001 and 002 are not rewritten.
- Configure does not change ASR adapter, diarization adapter, or model id; those remain `run` flags or a later change.
- Configure does not add `--rerun` to `stage` and does not add a preset to `configure`.
- `run` already resumes from stale stages once freshness is recorded; configure only has to mark the right stages.
- Interactive copy and identifiers stay in English (project constitution). Russian language names are accepted only as typed input aliases.
- Language selection is limited to languages Whisper supports; there is no custom/unknown language passthrough.
- ASR adapter, model, and prompt handling are unchanged. The wizard does not translate or rewrite the initial prompt when the language changes.
- Typical operator is fixing a bad first-pass language, empty prompt, or wrong skip/diarize choice on an existing local project.
