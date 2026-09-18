# CLI Contract: a-wizard

## Entry point

```bash
a-wizard --help
uv run a-wizard ...
```

## Commands

### `run TARGET`
Interactive/automated run until completion or a human gate.

Flags:
- `--status-only` — show status only
- `--dry-run` — show one next step without mutations
- `--preset obs-interview` — auto-configure tracks
- `--allow-raw-speakers` — allow merging with raw labels
- `--json` — machine-readable result
- `--no-color`
- `-v/--verbose`, `--debug`

### `status TARGET [--json]`
Checklist plus next step; validates artifacts and freshness.

### `plan TARGET [--json]`
Full DAG with statuses and blocked/stale reasons.

### `init VIDEO`
Create a project directory, an empty typed manifest, and probe metadata.

### `track set --project P --track N --mode plain|diarized|skipped ...`
Configure mode/speaker/language/prompt.

### `speakers map --project P --track N --map SPEAKER_00=__MANAGER__`
Assign roles and set the reviewed flag.

### `stage run --project P --stage KEY [--track N] [--rerun]`
Run one stage selectively.

### `doctor [TARGET]`
Check ffmpeg, extras, token presence (without printing values), and schema.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 2 | usage/config error |
| 3 | blocked prerequisite (token, human gate) |
| 4 | stage/adapter failure |
| 5 | corrupted project state |
| 70 | internal error |
| 130 | interrupted |

## Outputs (stable names)

```text
<stem>.project/
  manifest.yaml
  meta/source.json
  tracks/track_N.wav
  transcripts/track_N.segments.json
  transcripts/track_N.txt
  dialog/dialog.json
  dialog/dialog.txt
  dialog/dialog.minimize.txt
  dialog/transcript.txt
  dialog/spk_*.txt
  logs/run-*.jsonl
```
