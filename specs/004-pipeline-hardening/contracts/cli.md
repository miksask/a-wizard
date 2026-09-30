# Contracts: CLI (pipeline hardening)

## Commands affected

| Command | Reconciliation | Adapters |
|---------|----------------|----------|
| `run` | Yes, under lock before plan | Processing (ASR/diar/media) |
| `status` | Yes, under lock | Metadata-only |
| `plan` | Yes, under lock | Metadata-only |
| `configure` / `track` / `speakers` | No full digest reconcile required beyond existing stale marks | Metadata-only |
| `stage` | Yes before selected stage when project loaded | Processing as needed |

## Exit codes

Unchanged (`ExitCode` classes). Reconciliation failures that indicate corrupt state use STATE (5) only for unreadable manifests; missing artifacts yield STALE + resume, not STATE.

## Machine-readable plan

`plan --json` `next` reflects post-reconciliation DAG.
