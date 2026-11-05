# Feature Specification: Speak (TTS)

**Feature Branch**: `006-speak`

**Created**: 2026-10-28

**Status**: Implemented

**Input**: User description: "Add `a-wizard speak` to synthesize speech from a project's dialog.json (or an arbitrary txt file) with MLX TTS on Apple Silicon, multi-voice, sequential/timeline layout, optional voice cloning, and per-language overridable models for en/ru/pl."

## Background

After merge, operators have a structured dialog (`dialog/dialog.json`) with speaker ids and timings. There is no way to hear that dialog without the original recording. An explicit `speak` command synthesizes a WAV/MP3 from the dialog (or from a plain text file) using local MLX TTS. It is **not** part of the `run` DAG: `a-wizard run` never loads TTS models.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Speak a project dialog (Priority: P1)

The operator finishes a project (merge succeeded). They run `a-wizard speak PROJECT` and get `dialog/speech.wav`: every segment from `dialog.json` is spoken in order with short pauses, different speakers get different built-in voices when the model supports presets, and English uses the fast Kokoro MLX model.

**Why this priority**: Core value; without this the feature does not exist.

**Independent Test**: Synthetic project with `dialog/dialog.json` of two speakers; `speak --mock` writes `dialog/speech.wav` and `dialog/speech.json`; a second identical run is a no-op.

**Acceptance Scenarios**:

1. **Given** a project with merge succeeded, **When** `a-wizard speak PROJECT` runs, **Then** `dialog/speech.wav` and `dialog/speech.json` exist and stdout prints the wav path.
2. **Given** merge has not succeeded, **When** speak runs, **Then** it fails with `merge_required` and does not write speech artifacts.
3. **Given** identical inputs and an existing fresh `speech.json`, **When** speak runs again without `--force`, **Then** synthesis is skipped and the existing wav is reported.
4. **Given** English segments and default models, **When** speak runs, **Then** the English model id is Kokoro-82M (or an override) and stderr announces the model/device before the first load.

---

### User Story 2 - Speak an arbitrary text file (Priority: P1)

The operator has a `.txt` file (not a project). They run `a-wizard speak notes.txt` and get `notes.speech.wav` next to the file (or at `-o`). Plain text is one speaker by default, including lines that contain a colon. Lines `Name: text` become speakers only when `--speakers-from-prefix` is set.

**Why this priority**: Explicitly requested second mode; same synthesizer, no project lock.

**Independent Test**: Temporary txt with two `Name: …` lines; `--mock` writes wav beside the file; no `manifest.yaml` is created.

**Acceptance Scenarios**:

1. **Given** a plain txt without prefixes, **When** speak runs, **Then** one speaker synthesizes all non-blank lines.
2. **Given** lines `Alice: hi` / `Bob: bye` and speakers-from-prefix on, **When** speak runs, **Then** two speakers are used.
3. **Given** `-o /tmp/out.wav`, **When** speak runs, **Then** that path is written and reported.

---

### User Story 3 - Timeline layout and fit (Priority: P2)

The operator wants speech aligned to original timings. `--timeline` places each segment at its `start_ms`. Overruns are counted on stderr; `--fit` speeds overrunning chunks up to 1.5× via ffmpeg `atempo`.

**Why this priority**: Useful for A/B against the original recording; sequential remains the default.

**Independent Test**: Synthetic dialog with known `start_ms`; timeline render places audio at those offsets; a long segment past the next start is counted as overrun; with `--fit` duration shrinks within the cap.

**Acceptance Scenarios**:

1. **Given** `--timeline`, **When** speak runs, **Then** each line starts at its `start_ms` on a zeroed buffer.
2. **Given** a line that overruns the next segment start, **When** speak runs without `--fit`, **Then** stderr reports the overrun count and audio is still written.
3. **Given** `--timeline --fit`, **When** a line would overrun, **Then** it is sped up by at most 1.5× before placement.

---

### User Story 4 - Per-language models and overrides (Priority: P2)

English defaults to Kokoro; Russian and Polish default to Chatterbox multilingual. The operator can override per language via env (`A_WIZARD_TTS_MODEL_RU`), `speak.yaml`, or `--model ru=…`, with flag > yaml > env > default priority.

**Why this priority**: Required languages and quality escape hatch.

**Independent Test**: Unit tests of the registry override order; `--list-voices` / doctor show mlx-audio availability.

**Acceptance Scenarios**:

1. **Given** no overrides, **When** language is `en`, **Then** model is `mlx-community/Kokoro-82M-bf16`.
2. **Given** no overrides, **When** language is `ru` or `pl`, **Then** model is `mlx-community/chatterbox-multilingual-v3`.
3. **Given** `--model ru=mlx-community/Qwen3-TTS-…`, **When** Russian lines synthesize, **Then** that model id is used.
4. **Given** Chatterbox without cloning, **When** multiple speakers synthesize, **Then** stderr warns that the model has no preset voices.

---

### User Story 5 - Voice cloning from project tracks (Priority: P2)

The operator passes `--clone` (or `--clone SPEAKER_T0`). For each selected speaker, a 6–12 s reference is cut from the speaker's track using the longest dialog segments, saved under `dialog/speech/refs/`, and passed to the TTS engine. `--ref SPK=path.wav` overrides extraction. Txt mode requires an explicit `--ref`.

**Why this priority**: Requested opt-in; not default because slower and needs track audio.

**Independent Test**: Synthetic track wav + dialog segments; reference extraction writes a ref wav of expected duration; `--ref` wins over extraction.

**Acceptance Scenarios**:

1. **Given** `--clone` on a project with two speakers, **When** speak runs, **Then** each speaker gets a ref under `dialog/speech/refs/` and synthesis uses those refs.
2. **Given** `--ref SPEAKER_T0=custom.wav`, **When** speak runs, **Then** that file is used for T0 and other speakers follow `--clone` rules if set.
3. **Given** txt mode without `--ref`, **When** `--clone` is requested, **Then** the command fails with a clear usage error.

---

### User Story 6 - Per-line cache and partial invalidation (Priority: P3)

Changing one speaker's voice re-synthesizes only that speaker's lines; other cached chunks are reused. Cache keys include text, lang, model id, voice/ref digest, speed, and algo version.

**Why this priority**: Makes iteration on voices cheap on long dialogs.

**Independent Test**: Fake TTS counting calls; second run with one `--voice` change calls synthesize only for that speaker.

**Acceptance Scenarios**:

1. **Given** a completed speak cache, **When** only one speaker's voice changes, **Then** only that speaker's chunks are re-synthesized.
2. **Given** `--force`, **When** speak runs, **Then** all chunks are regenerated.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `a-wizard speak <project|file.txt>` that is not a DAG stage and is never invoked by `a-wizard run`.
- **FR-002**: Project mode MUST require merge succeeded; output `dialog/speech.wav` (+ optional mp3) and `dialog/speech.json` without bumping `SCHEMA_VERSION`.
- **FR-003**: Canonical dialog input MUST be `dialog/dialog.json` (segment list with `start_ms`, `end_ms`, `text`, `speaker`). Minimize txt MAY be accepted via glyph→speaker header mapping.
- **FR-004**: Default layout MUST be sequential with configurable pause (`--pause-ms`, default 250). `--timeline` MUST place by `start_ms`.
- **FR-005**: Voice assignment MUST key on speaker id; Kokoro presets MUST be assigned stably by first-seen order unless overridden.
- **FR-006**: Default models: en→Kokoro-82M-bf16; ru/pl→chatterbox-multilingual-v3. Overrides: env → speak.yaml → `--model`, highest wins.
- **FR-007**: Optional cloning from project tracks; atomic per-line cache under `dialog/speech/cache/`.
- **FR-008**: Logs MUST NOT contain transcript text; before first model load, show model/device and download risk.
- **FR-009**: `doctor` MUST report mlx-audio install status; TTS behind optional `tts` extra.
- **FR-010**: Txt mode MUST NOT create a project lock or manifest.

### Key Entities

- **SpeechLine**: text, speaker, lang, optional start_ms/end_ms.
- **SpeechScript**: ordered SpeechLines + metadata.
- **SpeakConfig**: models per lang, voices per speaker, layout, speed, clone/refs.
- **SpeechArtifact** (`speech.json`): signature digests, models, voices, layout, counts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With `--mock`, speak on a synthetic two-speaker project completes in under 2 s and produces a non-empty wav.
- **SC-002**: Identical re-run without `--force` performs zero synthesize calls.
- **SC-003**: Changing one `--voice` re-synthesizes only that speaker's lines (fake adapter call counts).
- **SC-004**: Unit tests cover lang detect, parsers, cache keys, sequential/timeline render, registry overrides, and ref extraction without real models.
- **SC-005**: On Apple Silicon with `--extra tts`, English synthesis uses Kokoro by default; ru/pl use Chatterbox unless overridden.

## Assumptions

- Target operators run primarily on Apple Silicon; Linux may lack the `tts` extra.
- Chatterbox has no preset voices; without `--clone`, ru/pl share the default voice and warn.
- ffmpeg remains available for mp3 and `--fit` atempo.
- Project language `auto` falls back to per-line heuristic detection (pl diacritics / Cyrillic / else en).
