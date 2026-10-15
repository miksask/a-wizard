# Quickstart: Multitrack Attribution

## Existing project (re-attribute without ASR)

```bash
uv run a-wizard status records/call.project   # attribute/merge/minimize show as pending (stale)
uv run a-wizard run records/call.project      # redoes attribute → merge → minimize only
cat records/call.project/meta/attribution.json
```

The report lists per-track noise floor, speech level, active ratio, detected crosstalk, and warnings such as a very noisy microphone or a track without speech.

## Several diarized tracks / rooms

```bash
uv run a-wizard configure call.project --language en --no-prompt \
  --track 0:diarized --track 1:diarized --track 2:plain --track 3:plain
uv run a-wizard run call.project
```

Speakers are `SPEAKER_T{track}D{n}` per diarized track and `SPEAKER_T{track}` per plain track.

## Opt-in ASR cleanup

```bash
uv run a-wizard options call.project                      # show current values
uv run a-wizard options call.project --audio-cleanup --hallucination-silence 2
uv run a-wizard run call.project                          # redoes mixdown + ASR + downstream
uv run a-wizard options call.project --no-audio-cleanup --no-hallucination-silence
```

## Tests

```bash
uv run pytest tests/unit/test_activity.py tests/unit/test_crosstalk.py tests/unit/test_attribution.py
./scripts/quality-gate.sh
```
