# Data Model: Pipeline Hardening

## Stage contract (in-memory)

| Field | Meaning |
|-------|---------|
| `key` | Stage key (`extract`, `mixdown`, `transcribe:mix`, …) |
| `signature_fn` | Builds expected signature from Project |
| `required_outputs` | Relative paths that must exist when succeeded |
| `digest_aliases` | Map legacy semantic digest key → relative path |

## StageRecord.output_digests

- **New writes**: `{ "<relpath>": "<sha256 hex>" }`
- **Legacy reads**: semantic keys remapped via `digest_aliases` for verification

## Energy cache sidecar

Path: `meta/energy/track_{index}.json`

```json
{
  "wav_sha256": "hex",
  "window_ms": 20,
  "algorithm_version": "a-wizard-2-energy-v1"
}
```

Companion: `meta/energy/track_{index}.npy` (float32 RMS windows).

## Source fingerprint

- `source.content_fingerprint`: content hash string (full or sampled as documented in research).
- Format change may stale extract once for older projects.

## Reconciliation result

```text
invalidated: list[str]
saved: bool
```

No new persisted top-level manifest entity; schema_version remains 2.
