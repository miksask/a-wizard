# Implementation Plan: Pipeline Hardening

**Branch**: `004-pipeline-hardening` | **Date**: 2026-10-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-pipeline-hardening/spec.md`

## Summary

Close P0/P1 audit gaps: reconcile stage signatures and digests before planning; invalidate on adapter identity change; version energy caches; align JSON schemas with `start_ms`/`end_ms`; make read-only CLI metadata-only; ignore `records` symlink; provide a local Ruff/pytest/schema/build quality gate.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Existing Typer/YAML/numpy stack; optional `jsonschema` in `dev` extras only

**Storage**: Existing project directory + atomic YAML manifest + energy cache sidecars

**Testing**: pytest, synthetic ffmpeg fixtures, mock ASR/diar adapters, schema contract tests

**Target Platform**: macOS and Linux

**Project Type**: local CLI

**Performance Goals**: Reconciliation is O(number of stage artifacts) disk hashes; skip rewrite when unchanged

**Constraints**: Local-first; no cloud CI in this feature; synthetic tests only; schema_version stays 2

**Scale/Scope**: Domain + application reconciliation, attribution cache, CLI composition root, local scripts/hooks

## Constitution Check

- **I. Local-First Privacy**: Hygiene scripts block media/tokens; JSONL filter unchanged. Pass.
- **II. Resume-Safe Atomic State**: Reconciliation under lock; atomic energy writes. Pass.
- **III. Verifiable Freshness**: Core of this feature — compare signatures + digests. Pass.
- **IV. Ports and Adapters**: Metadata-only service avoids resolving heavy adapters; Processing injects Protocols. Pass.
- **V. Synthetic Tests First**: All new tests mock/synthetic. Pass.

## Project Structure

### Documentation (this feature)

```text
specs/004-pipeline-hardening/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── mix.segments.schema.json
│   └── energy-cache.schema.json
└── tasks.md
```

### Source Code

```text
src/a_wizard/
  domain/freshness.py              # stage contracts + digest key helpers
  application/reconciliation.py    # reconcile under lock
  application/attribution.py       # versioned energy cache
  application/service.py           # wire reconcile + lazy adapters
  adapters/media/ffmpeg.py         # stronger source fingerprint
  cli/app.py                       # metadata vs processing service
  adapters/persistence/store.py    # (unchanged API; digests path-keyed)

scripts/
  quality-gate.sh
  check-repo-hygiene.sh
hooks/
  pre-commit
  pre-push

tests/
  unit/test_reconciliation.py
  unit/test_energy_cache.py
  unit/test_contracts.py
  application/test_lazy_service.py
  integration/test_pipeline.py     # extend
```

**Structure Decision**: Keep single package; add one reconciliation module rather than bloating `service.py` further.

## Complexity Tracking

None.
