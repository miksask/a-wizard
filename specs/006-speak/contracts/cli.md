# CLI Contract: speak

## Command

```
a-wizard speak <target>
  [--timeline] [--fit] [--pause-ms 250]
  [--language auto|en|ru|pl|…]
  [--model LANG=ID]… [--voice SPK=VOICE]…
  [--clone [SPK]]… [--ref SPK=WAV]…
  [--speed 1.0] [--format wav|mp3] [-o OUT]
  [--force] [--mock] [--list-voices]
  [--speakers-from-prefix / --no-speakers-from-prefix]
  # default: off — a .txt file is one speaker (SPEAKER_00)
```

## Target

- Directory ending in `.project` or containing `manifest.yaml` → **project mode**
- File ending in `.txt` (or other text) → **txt mode**
- Otherwise: resolve via existing `resolve_target` helpers when possible

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| UsageError codes | `merge_required`, `bad_language`, `tts_missing`, `clone_requires_ref`, `speak_config` |
| Internal | unexpected |

## stdout / stderr

- **stdout**: absolute or relative path to the written audio file (one line)
- **stderr**: progress, model announcements, warnings, overrun counts — never transcript text

## doctor

```
OK mlx-audio installed
OPTIONAL mlx-audio not installed (uv sync --extra tts)
```

## --list-voices

Prints voices available for the resolved English (or `--language`) model via the adapter; exits 0 without synthesizing.
