# CLI contract: `a-wizard configure`

```text
a-wizard configure TARGET
  [--language CODE|NAME|auto]
  [--prompt TEXT | --no-prompt]
  [--track N:mode]...
```

`TARGET` is a video file with an existing `.project` beside it, or a `.project` directory. Same resolution as `run` / `status`.

## Flags

| Flag | Meaning |
|------|---------|
| `--language CODE\|NAME\|auto` | Project ASR language: a Whisper language code (`de`), a language name (`German`, `немецкий`), or `auto` for Whisper detection. Normalized to a code before storing. Unsupported value → usage error (exit 2) with suggestions |
| `--prompt TEXT` | Set Whisper `initial_prompt` |
| `--no-prompt` | Clear `initial_prompt` |
| `--track N:mode` | Repeatable. `mode` is `plain`, `diarized`, or `skipped`. Optional `N:mode:reason` for skip reason |

A supplied flag skips the matching interactive question.

## Interactive questions (TTY, missing flags)

1. Project initial prompt: leave unchanged / disable / enter custom
2. Project language (same question as the first-run gate in `run`):
   ```text
   Project language:
     [1] auto (default)
     [2] ru
     [3] en
     [4] other
   ```
   `other` prompts `Language (code or name): `. Input is normalized (case-insensitive, trimmed); an unsupported value prints close matches and re-asks.
3. Each track: `plain` / `diarized` / `skipped`

Current stored values are the defaults. For language: `auto` when none was chosen; the matching item for stored `auto` / `ru` / `en`; `[4] other (current: de)` for any other stored code (Enter keeps it).

## Language values

- Stored in `transcription_defaults.language` as `auto` or a canonical Whisper code (`de`, `pl`, ...).
- `auto` → adapters call Whisper without a forced language.
- Error code for unsupported input: `bad_language`.

## Non-TTY

If stdin is not a terminal, every setting not supplied by flags is a usage (2) or blocked (3) error. No preset, no guessing.

## Behavior

- Requires an initialized project. Does not `init` or extract.
- Acquires the project lock.
- Does not run extract, mixdown, transcription, attribute, merge, or minimize.
- One atomic manifest save after all settings are known.
- Stdout: short settings summary and `a-wizard run <project>`.
- JSONL events may include language and track modes; not the full prompt.

## Exit codes

Same classes as the rest of the CLI: 0 success, 2 usage, 3 blocked, 5 lock/corrupt, 130 interrupt.
