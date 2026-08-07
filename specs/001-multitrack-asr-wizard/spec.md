# Feature Specification: Multitrack ASR Wizard

**Feature Branch**: `001-multitrack-asr-wizard`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "A local interactive CLI for multitrack ASR with a resume-safe pipeline, plain/diarized/skipped modes, and a minimized dialog for LLMs"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - End-to-end interview transcription (Priority: P1)

The operator runs `a-wizard run` on an OBS recording with multiple audio streams. The system creates a project beside the video, extracts tracks, helps configure modes, transcribes them, assigns speaker roles when needed, merges the dialog, and creates `dialog.minimize.txt` for an LLM.

**Why this priority**: This is the primary product workflow; without it, the project has no value.

**Independent Test**: Use synthetic two-track media and mock ASR to produce `dialog.minimize.txt` with a glyph legend and no timestamps.

**Acceptance Scenarios**:

1. **Given** a video with ≥1 audio stream, **When** `a-wizard run VIDEO`, **Then** `<stem>.project/` is created with `manifest.yaml` and mono 16 kHz WAV files.
2. **Given** configured tracks, **When** transcription completes, **Then** `transcripts/track_N.segments.json` and `.txt` exist.
3. **Given** all active tracks are transcribed or skipped, **When** merge+minimize runs, **Then** `dialog/dialog.json`, `dialog/dialog.txt`, and `dialog/dialog.minimize.txt` exist.

---

### User Story 2 - Safe resume after interruption (Priority: P1)

The operator interrupts a long transcription (Ctrl+C) or encounters an error. Running the same command again resumes from the correct next step without losing completed artifacts.

**Why this priority**: Recordings are long; without resume support, the product is unusable.

**Independent Test**: Stop during extract/transcribe, check status, rerun, and verify that completed stages are not recomputed.

**Acceptance Scenarios**:

1. **Given** a project after Ctrl+C, **When** `a-wizard run PROJECT` is repeated, **Then** processing continues from the next incomplete step and exits with a code other than 130.
2. **Given** `--status-only`, **When** run twice consecutively, **Then** stdout is identical except for permitted timestamps, and files remain unchanged.

---

### User Story 3 - Track modes and fixed speaker IDs (Priority: P1)

The operator selects `plain`, `diarized`, or `skipped` for each track. Language and the Whisper prompt are configured at project level. Speaker names are fixed: plain → `SPEAKER_T{n}`, diarized → `SPEAKER_T{n}D{k}` (0-based).

**Why this priority**: Without modes and stable IDs, the dialog is unusable by an LLM.

**Independent Test**: A fixture with mock diarization causes attribute/merge to write `SPEAKER_T*` without a speaker-review gate.

**Acceptance Scenarios**:

1. **Given** track mode=plain, **When** attribute/transcribe runs, **Then** segments have `SPEAKER_T{n}`.
2. **Given** a diarized track with diarizer label `SPEAKER_00`, **When** attribution runs, **Then** the merged label is `SPEAKER_T{n}D0`.
3. **Given** a skipped track, **When** merge runs, **Then** its segments are absent from the dialog.

---

### User Story 4 - Status, plan and dry-run (Priority: P2)

The operator checks state without side effects: checklist, DAG plan, and a preview of the next step.

**Why this priority**: This is required for diagnostics and safe automation.

**Independent Test**: On an incomplete fixture, `status`/`plan`/`--dry-run` do not change the manifest mtime.

**Acceptance Scenarios**:

1. **Given** an incomplete project, **When** `--dry-run` is used, **Then** exactly one next step is reported and no mutations occur.
2. **Given** any project, **When** `a-wizard plan PROJECT --json` runs, **Then** the JSON contains stages with statuses and blocked/stale reasons.

---

### User Story 5 - Non-interactive preset run (Priority: P2)

In CI or scripts, the operator runs `a-wizard run VIDEO --preset obs-interview` without stdin.

**Why this priority**: Automation is important and must not require custom speaker names.

**Independent Test**: Mock adapters plus a preset on a two-track fixture exits with 0 and no prompts.

**Acceptance Scenarios**:

1. **Given** `--preset obs-interview`, **When** a non-interactive run starts, **Then** track 0 is plain/`SPEAKER_T0` and all other tracks are diarized.
2. **Given** diarized tracks without review, **When** running non-interactively, **Then** merge completes with fixed `SPEAKER_T*` labels.
3. **Given** diarization without an HF token (pyannote), **When** attribution is reached, **Then** the process exits with code 3 and token setup instructions.

---

### User Story 6 - Granular stage rerun (Priority: P3)

The operator changes speaker_map or glyphs and selectively reruns merge/minimize without repeating expensive ASR.

**Why this priority**: This saves time after manual edits.

**Independent Test**: Change speaker_map → `stage run merge` and `minimize` update the dialog while ASR artifact digests remain unchanged.

**Acceptance Scenarios**:

1. **Given** a completed project, **When** speaker_map changes, **Then** merge/minimize become stale while ASR remains fresh.
2. **Given** only glyphs have changed, **When** status is checked, **Then** only minimize is stale.

---

### Edge Cases

- Video without audio streams → init/probe error with a clear message.
- Missing WAV during transcription → error suggesting that extract be run.
- Missing HF token for diarization → blocked prerequisite (exit 3).
- Corrupted/deleted artifact with status=succeeded → stage becomes stale.
- Two concurrent `run` commands on one project → lock error.
- Identical cross-track diarizer labels `SPEAKER_00` → canonical `SPEAKER_T{n}D0`, with no merge collision.
- An empty transcript (0 segments) is a valid result.
- Malformed dialog lines during rendering produce an error/report rather than being silently dropped without a trace.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a path to a video (`.mkv/.mp4/.mov/.webm/.avi/.m4v`) or a `.project` directory and resolve/create a project beside the video.
- **FR-002**: The system MUST extract all audio streams as mono 16 kHz PCM WAV using ffmpeg/ffprobe.
- **FR-003**: The system MUST support track modes `plain`, `diarized`, and `skipped`. Language and Whisper `initial_prompt` are configured only at project level (`transcription_defaults`); per-track overrides are ignored for ASR.
- **FR-004**: The system MUST transcribe plain tracks through a replaceable ASR adapter and diarized tracks through ASR plus diarization adapters.
- **FR-005**: The system MUST use fixed speaker IDs without a human role-mapping gate: plain → `SPEAKER_T{n}`, diarized voice → `SPEAKER_T{n}D{k}` (0-based track/voice indices). An optional legacy `speakers map` MAY remap them; merge does not require review. `--allow-raw-speakers` is retained for CLI compatibility.
- **FR-006**: The system MUST merge active-track segments deterministically by time and save canonical `dialog.json`.
- **FR-007**: The system MUST generate `dialog.minimize.txt` without timestamps, with a glyph legend (`[STn]` / `[STnDk]`) and adjacent turns from the same speaker merged.
- **FR-008**: The system MUST maintain a resume-safe, typed, versioned manifest using atomic writes and a project lock.
- **FR-009**: The system MUST invalidate dependent stages using freshness signatures.
- **FR-010**: The system MUST provide the commands `run`, `status`, `plan`, `init`, `track set`, `speakers map`, `stage run`, and `doctor`.
- **FR-011**: The system MUST support `--status-only`, `--dry-run`, `--json`, `--no-color`, verbosity/debug, and stable exit codes (0/2/3/4/5/70/130).
- **FR-012**: The system MUST write JSONL run logs without secrets or transcript text.
- **FR-013**: Non-interactive auto-configuration MUST use only an explicit `--preset`; guessing from track numbers without a preset is forbidden.
- **FR-014**: Legacy manifest v1 MUST NOT be read in place; an optional separate import is outside the v1 scope.
- **FR-015**: The system MUST print per-stage wall times (from `started_at`/`finished_at`) and their total at the end of run and in status.

### Key Entities

- **Project**: artifact directory and typed manifest.
- **Track**: audio stream with mode/status/config.
- **Segment**: start/end (integer ms), text, speaker id.
- **StageAttempt**: stage result with signature, digests, and provenance.
- **SpeakerMapping**: raw label → role.
- **ArtifactRef**: relative path, digest, and format version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A complete interactive run on a two-track fixture with mock adapters produces `dialog.minimize.txt` in one pass without manual file edits.
- **SC-002**: After Ctrl+C, a repeated run resumes without recreating already-fresh artifacts.
- **SC-003**: `--status-only` and `--dry-run` do not modify project files (mtime/content).
- **SC-004**: Changing speaker_map makes only merge/render stale; ASR artifacts remain fresh.
- **SC-005**: The unit and integration suite passes on synthetic data without network access, a GPU, or an HF token.
- **SC-006**: Swapping the plain mock adapter produces the expected segments without importing faster-whisper.

## Assumptions

- The user has ffmpeg/ffprobe and uv/Python 3.13.
- The typical use case is an OBS multitrack interview or one-on-one call.
- Tests do not guarantee real ASR/diarization accuracy; the adapter contract covers format and orchestration.
- Overlapping audio is not deduplicated across tracks in v1.
- GUI/API/batch service and LLM summary are outside the scope.
