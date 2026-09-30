# Research: Pipeline Hardening

## 1. Where to verify freshness

**Decision**: Application-level `reconcile_project(project_dir, project, store)` called under lock before `detect_next_action` in `run`/`status`/`plan`. Domain keeps pure signature functions and stage contracts (required outputs + digest key aliases).

**Rationale**: Digest checks need filesystem access (ArtifactStore); domain stays I/O-free. Planner continues to trust `status` after reconciliation has updated it.

**Alternatives considered**:
- Push digest checks into `detect_next_action` — couples DAG to FS.
- Only check on `run` — `status`/`plan` would lie about Done.

## 2. Legacy output_digests keys

**Decision**: Stage contracts map semantic keys (`raw`, `mix`, `segments`, …) to relative paths. Verification accepts either path keys or mapped semantic keys. New writes always store path keys.

**Rationale**: Avoid schema bump and manual migration; one safe stale+rerun if mapping cannot prove validity.

## 3. Lazy adapters

**Decision**: `ServiceConfig.metadata_only=True` skips `resolve_asr_adapter` / `resolve_diar_adapter`. CLI uses metadata-only for `status`, `plan`, `configure`, `track`, `speakers`. Processing commands resolve adapters as today.

**Rationale**: Meets SC-003 without restructuring the whole DI graph.

## 4. Energy cache format

**Decision**: Store `meta/energy/track_{n}.npy` plus sidecar `meta/energy/track_{n}.json` with `{wav_sha256, window_ms, algorithm_version}`. Atomic write both; validate before load.

**Rationale**: Numpy alone cannot carry metadata portably without custom formats.

## 5. Source fingerprint

**Decision**: Replace size:mtime with SHA-256 of full file when size ≤ 64 MiB; for larger files use size + mtime_ns + sha256 of first and last 1 MiB (documented sampled hash).

**Rationale**: Closes silent replace risk without hashing multi-GB video on every status.

## 6. Local quality gate

**Decision**: `scripts/quality-gate.sh` + `scripts/check-repo-hygiene.sh`; optional `hooks/pre-commit` and `hooks/pre-push` with README instruction `git config core.hooksPath hooks`.

**Rationale**: User chose local-only; no GitHub/Bitbucket workflows.
