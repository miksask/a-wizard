# Data Model additions (002)

## New types

### Word
- `start_ms`, `end_ms`, `text`

### SpeakerTurn
- `start_ms`, `end_ms`, `speaker`

### TranscriptResult
- `segments: Segment[]`
- `words: Word[]`

## Project fields

- `processing_mode`: `mixdown` | `per_track` (default `mixdown`)
- `mix`: `{ wav: "tracks/mix.wav", segments: "transcripts/mix.segments.json", transcript_txt: "transcripts/mix.txt" }`
- `adapters.asr`: `mlx-whisper` | `faster-whisper` | `mock-asr`
- `adapters.diarization`: `fluidaudio` | `sherpa-onnx` | `speakrs-coreml` | `pyannote-community-1` | `mock-diar`

## Stages (mixdown path)

`extract` → `mixdown` → configure gates (project prompt+language; track mode) → `transcribe:mix` → `attribute` → `merge` → `minimize`

Optional: `diarize:{track}` as sub-step inside attribute for diarized channels.

## Invalidation

| Change | Stale |
|--------|-------|
| extract / source | all mixdown downstream |
| mixdown params / skipped set | mixdown + ASR + attribute + merge |
| ASR model/prompt/language (project) | transcribe:mix + attribute + merge |
| channel roles / plain_speaker | attribute + merge (ASR kept) |
| diar adapter | attribute for diarized channels + merge |
| glyphs | minimize only |
