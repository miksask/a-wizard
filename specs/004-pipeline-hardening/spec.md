# Feature Specification: Pipeline Hardening

**Feature Branch**: `004-pipeline-hardening`

**Created**: 2026-10-01

**Status**: Implemented

**Input**: User description: "Fix P0/P1 audit findings: verifiable freshness before planning, energy-cache correctness, JSON contract alignment, lazy adapters for read-only CLI, records/privacy hygiene, and a local quality gate (no cloud CI)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detect stale or corrupt artifacts (Priority: P1)

The operator finishes a project, then deletes or replaces a pipeline artifact (for example `tracks/mix.wav` or `dialog/dialog.json`) or changes source video content under the same path. When they run `status`, `plan`, or `run`, the system reconciles signatures and digests, marks the first broken stage and its dependents stale, and resumes from that stage.

**Why this priority**: Constitution III requires verifiable freshness; today `status == succeeded` alone can leave a Done project with missing or wrong files.

**Independent Test**: Completed mixdown fixture with mock engines; delete `transcripts/mix.raw.json`; `status`/`plan` show mix transcription as next; `run` redoes transcription and later stages without re-extracting when extract digests remain valid.

**Acceptance Scenarios**:

1. **Given** a completed project, **When** a required succeeded-stage output is missing, **Then** that stage and downstream become stale and next action is that stage.
2. **Given** a completed project, **When** a required output file digest no longer matches the recorded digest, **Then** that stage and downstream become stale.
3. **Given** a completed project with unchanged artifacts and config, **When** `status` or `run` runs, **Then** no stage is marked stale and the manifest is not rewritten solely for reconciliation.

---

### User Story 2 - Switch runtime adapters safely (Priority: P1)

The operator re-runs with a different ASR or diarization adapter than the one stored in the manifest. Before planning, the system updates adapter identity and invalidates only stages that depend on that adapter.

**Why this priority**: Adapter IDs are part of stage signatures but were only written at init; switching `--asr-adapter` / `--diar-adapter` could leave stale results marked succeeded.

**Independent Test**: Completed mixdown fixture; re-run with a different mock/real adapter id recorded in service config; mix transcription (or attribute) becomes stale as appropriate; extract remains fresh when only diarization identity changed.

**Acceptance Scenarios**:

1. **Given** a completed mixdown project with ASR adapter A, **When** `run` uses ASR adapter B, **Then** mix transcription and downstream are stale before work starts.
2. **Given** a completed mixdown project, **When** only the diarization adapter identity changes, **Then** attribute + merge + minimize are stale and mix transcription stays succeeded if still digest-valid.
3. **Given** `status` or `plan` without processing extras, **When** those commands run, **Then** they do not import or require mlx-whisper / diarization packages.

---

### User Story 3 - Safe energy cache (Priority: P1)

Attribution caches per-track RMS profiles. After extract changes the WAV, or cache metadata is wrong/corrupt, the system recomputes profiles instead of reusing a stale `.npy`.

**Why this priority**: Wrong energy profiles silently mis-attribute speakers.

**Independent Test**: Synthetic WAVs; load cache with matching digest/window; mutate WAV or corrupt `.npy`; next attribution recomputes and succeeds.

**Acceptance Scenarios**:

1. **Given** a valid cached profile matching WAV digest + window_ms + algorithm version, **When** profiles are loaded, **Then** the cache is reused.
2. **Given** a cache whose WAV digest or window_ms differs, **When** profiles are loaded, **Then** the profile is recomputed and cache replaced atomically.
3. **Given** a corrupt `.npy` or missing metadata sidecar, **When** profiles are loaded, **Then** the profile is recomputed without crashing.

---

### User Story 4 - Local quality and privacy gate (Priority: P2)

Contributors run a local quality gate before push. Ruff is clean, tests pass with coverage floor, JSON schemas validate emitted artifacts, and `records` (including a symlink) cannot be tracked accidentally.

**Why this priority**: Prevents regression of P0/P1 fixes without requiring cloud CI.

**Independent Test**: `scripts/quality-gate.sh` exits 0 on a clean tree; `git check-ignore -v records` matches; tracked-path hygiene script fails if a `.wav` or token-like file would be added.

**Acceptance Scenarios**:

1. **Given** the repo with the new gate scripts, **When** the full gate runs with ffmpeg available, **Then** Ruff, pytest (no silent skip of integration), schema contracts, and package build succeed.
2. **Given** a symlink named `records`, **When** git status is inspected, **Then** it is ignored.
3. **Given** an attempt to track a media or `HF_TOKEN`-like path, **When** the hygiene check runs, **Then** it fails with a clear message.

---

### Edge Cases

- Legacy manifests with semantic `output_digests` keys (`raw`, `mix`, `segments`) remain readable; verification maps them via stage contracts or marks the stage stale once for a safe rerun.
- Schema version remains 2; no manual migration tool is required.
- Interrupted stages (`running` without finish) are treated as needing rerun (stale or interrupted) during reconciliation.
- Metadata-only CLI commands never resolve ASR/diar adapters even when extras are installed.
- Empty digests on a succeeded stage with missing files → stale.
- Source fingerprint uses content hash (or documented sampled hash) so size+mtime collisions do not hide replacements.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before `run`, `status`, and `plan` compute next action, the system MUST reconcile stage freshness using expected signatures, required artifact paths, and SHA-256 digests.
- **FR-002**: Reconciliation MUST mark the earliest broken succeeded/running stage and all dependents `stale`, and MUST persist the manifest only when status or recorded identity actually changed.
- **FR-003**: `StageRecord.output_digests` for newly completed stages MUST use artifact-relative paths as keys; legacy semantic keys MUST still be interpretable via stage contracts.
- **FR-004**: Read-only and settings commands (`status`, `plan`, `configure`, `track`, `speakers`) MUST work with base dependencies and MUST NOT construct ASR/diarization engines.
- **FR-005**: Processing `run`/`stage` MUST compare selected adapter identities (and model when applicable) to the manifest and invalidate dependent stages before planning.
- **FR-006**: Energy profile cache MUST key on WAV SHA-256, `window_ms`, and algorithm version; invalid or corrupt cache MUST be recomputed with atomic write.
- **FR-007**: Mix/dialog JSON contracts MUST use `start_ms`/`end_ms` (not ambiguous `start`/`end` seconds) for emitted artifacts; contract tests MUST validate real serialized outputs.
- **FR-008**: `.gitignore` MUST ignore `records` whether it is a directory or a symlink; a local hygiene check MUST block media/token paths from being tracked.
- **FR-009**: A local quality gate (scripts + optional git hooks) MUST run Ruff, pytest with coverage floor ≥70%, schema contracts, and package build; cloud CI remotes are out of scope.
- **FR-010**: Automated tests for this feature MUST use only synthetic fixtures and mock adapters (no real recordings, tokens, or network).

### Key Entities

- **Stage contract**: Declares signature builder, required outputs, and digest key mapping for a stage.
- **Reconciliation result**: List of invalidated stage keys and whether the manifest should be saved.
- **Energy cache entry**: Profile array plus metadata (wav digest, window_ms, algorithm version).
- **Service mode**: Metadata-only vs processing composition root.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Deleting a required mix ASR artifact on a completed fixture causes `plan` next action to be mix transcription and a following `run` to restore Done without re-extract when extract remains valid.
- **SC-002**: Changing only the configured diarization adapter id on a completed mixdown fixture stales attribute+downstream and leaves mix transcription fresh when digests match.
- **SC-003**: `uv run a-wizard status` on an initialized project succeeds in an environment without mlx/diar extras installed.
- **SC-004**: Energy cache reuse and invalidation behaviors are covered by unit tests; corrupt cache does not fail attribution.
- **SC-005**: Full local quality gate exits 0; Ruff reports 0 errors; coverage ≥70%; `records` symlink is ignored.

## Assumptions

- Feature 004 extends 001–003; those specs are not rewritten except for shared contract files under 002 that document the real ms-based JSON shape.
- Local hooks require a one-time `git config core.hooksPath` documented in README; the repo does not rewrite global git config automatically.
- Improving source fingerprint to content hash may make extract stale once for existing projects when fingerprint format changes — acceptable one-time cost.
- Cloud CI and remote renaming remain out of scope.
