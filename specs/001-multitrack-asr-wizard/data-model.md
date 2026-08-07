# Data Model: Multitrack ASR Wizard

## Entities

### Project
- `schema_version`: int (2)
- `project_id`: uuid/str
- `created_at`, `updated_at`: ISO-8601 UTC
- `source`: SourceMedia
- `transcription_defaults`: AsrDefaults
- `tracks`: Track[]
- `stages`: map[StageKey → StageRecord]
- `speaker_glyphs`: map[role → glyph]
- `adapters`: selected adapter ids
- `lock`/`active_run_id`: optional runtime hints (not secrets)

### SourceMedia
- `path_rel` or `path` relative to project when possible
- `basename`
- `duration_ms`
- `audio_stream_count`
- `content_fingerprint` (size+mtime or hash when available)

### Track
- `index`: int (0-based)
- `stream_index`: int
- `wav_rel`: `tracks/track_N.wav`
- `mode`: `pending | plain | diarized | skipped`
- `language`: str (legacy field; ASR uses project `transcription_defaults.language`)
- `plain_speaker`: auto `SPEAKER_T{n}` for plain mode (custom names not used in new runs)
- `skip_reason`: optional str
- `initial_prompt`: legacy field; ASR uses project `transcription_defaults.initial_prompt` only
- `speaker_map`: optional legacy remap (raw → role); not required for merge
- `speaker_map_reviewed`: bool (legacy)
- `segments_rel`, `transcript_txt_rel`

### Segment
- `start_ms`, `end_ms`: int ≥ 0, end ≥ start
- `text`: non-empty str
- `speaker`: `SPEAKER_T{n}` (plain) or `SPEAKER_T{n}D{k}` (diarized); short glyph form `STn` / `STnDk`

### StageRecord
- `key`: e.g. `extract`, `transcribe:0`, `diarize:0`, `relabel:0`, `merge`, `minimize`
- `status`: `pending | running | succeeded | failed | stale | interrupted`
- `signature`: str
- `attempt_id`: str
- `started_at`, `finished_at`
- `adapter_id`, `adapter_version`, `model_id`, `model_revision`
- `input_digests`, `output_digests`
- `error_code`, `error_message` (user-facing, no secrets)
- `log_rel`

### ArtifactRef
- `rel_path` (must stay under project dir)
- `digest` (sha256)
- `bytes`
- `format`: `wav16k_mono | segments_v1 | dialog_v1 | minimize_v1 | ...`

## Stage DAG

```text
probe/extract
  → configure gates (project prompt + language; track mode only)
  → for each active track:
      transcribe
      diarize? (diarized only)
      attribute/relabel
  → merge → dialog.json
  → render txt / spk_* / minimize
```

## Invalidation matrix (summary)

| Change | Stale |
|--------|-------|
| source media | all |
| extract params | extract+downstream |
| ASR config/adapter/model/prompt/language (project) | transcribe+downstream |
| diar config | diarize+downstream; ASR kept |
| plain_speaker / channel mode | attribute+merge+render (mixdown) or transcribe+merge |
| legacy speaker_map | merge+render |
| glyphs | minimize only |
| skip/unskip | merge+render |

## Validation rules

- Unique track indexes
- plain auto-assigns `plain_speaker=SPEAKER_T{n}`
- skipped excluded from merge inputs
- artifact paths relative and confined
- Fixed `SPEAKER_T*` labels are merge-ready without review
