# Data Model: Configure CLI

No new persisted entities. Configure updates existing project fields and stage records.

## Fields written

### `transcription_defaults`

- `language`: `ru` | `en`
- `initial_prompt`: string or null
- `initial_prompt_reviewed`: always `true` after a successful configure

### `tracks[]`

- `mode`: `plain` | `diarized` | `skipped` (configure does not leave `pending`)
- `plain_speaker`: `SPEAKER_T{n}` when mode is `plain`
- `skip_reason`: optional when mode is `skipped`
- `language`: kept in sync with project language (legacy field)
- `status`: per-track transcription reset to `extracted` when ASR config changes in `per_track` mode

### `stages[*].status`

Become `stale` per the configure invalidation matrix in [spec.md](./spec.md). Extract is never marked stale by configure.

## Validation

- Target must already be an initialized project (manifest present).
- Language must be `ru` or `en`.
- Every track index in `--track` must exist; non-interactive mode requires a mode for every track.
- `--prompt` and `--no-prompt` are mutually exclusive.
- Track mode must be `plain`, `diarized`, or `skipped`.

## State transitions

```text
configure (settings collected)
  → persist transcription_defaults + track modes
  → if language/prompt changed: asr_config stale
  → if plain↔diarized: existing track:{n} stale
  → if skipped set changed: existing skipped_set stale
  → if nothing changed: no stage status change
  → stop (no stage runners)
```
