# CLI contract: `a-wizard options`

```text
a-wizard options TARGET
  [--audio-cleanup | --no-audio-cleanup]
  [--hallucination-silence SECONDS | --no-hallucination-silence]
```

`TARGET` is a video file with an existing `.project` beside it, or a `.project` directory (same resolution as `run` / `status` / `configure`).

## Flags

| Flag | Meaning |
|------|---------|
| `--audio-cleanup` | Attenuate inactive track frames and normalize track levels before ASR (mixdown: gated `tracks/mix.wav`; per_track: `tracks/track_{n}.clean.wav`) |
| `--no-audio-cleanup` | Back to plain mixing (default) |
| `--hallucination-silence SECONDS` | Pass Whisper `hallucination_silence_threshold` (seconds, > 0) |
| `--no-hallucination-silence` | Clear it (default) |

## Behavior

- Requires an initialized project; metadata-only (does not load ASR/diarization engines).
- Without flags: prints current values, changes nothing, exit 0.
- With flags: acquires the project lock, updates `transcription_defaults`, invalidates only dependent stages, saves once, prints the new values and `Next: a-wizard run <project>`.
- Unchanged values are a no-op (no stale marks).
- Mutually exclusive pairs (`--hallucination-silence` with `--no-hallucination-silence`) or a non-positive threshold are usage errors (2).

## Invalidation

| Option | mixdown | per_track |
|--------|---------|-----------|
| `audio_cleanup` | mixdown, transcribe:mix, attribute, merge, minimize | active transcribe:N, merge, minimize |
| `hallucination_silence_threshold` | transcribe:mix, attribute, merge, minimize | active transcribe:N, merge, minimize |

## Status

`status` / `run --status-only` print an `Options:` line only when an option differs from its default.

## Exit codes

Same classes as the rest of the CLI: 0 success, 2 usage, 5 lock/corrupt.
