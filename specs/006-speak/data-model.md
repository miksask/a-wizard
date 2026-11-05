# Data Model: Speak

## SpeechLine

| Field | Type | Notes |
|-------|------|-------|
| text | str | non-empty after strip |
| speaker | str | e.g. `SPEAKER_T0` or `Alice` |
| lang | str | Whisper code: `en`, `ru`, `pl`, … |
| start_ms | int \| None | from dialog.json; None in txt mode |
| end_ms | int \| None | optional |

## SpeechScript

Ordered list of `SpeechLine` plus `source` (`project` \| `txt`) and optional `project_dir`.

## SpeakConfig

| Field | Notes |
|-------|-------|
| models | map lang → model id |
| voices | map speaker → preset voice name |
| refs | map speaker → Path (manual clone refs) |
| clone_speakers | set of speakers or all |
| layout | `sequential` \| `timeline` |
| pause_ms | default 250 |
| speaker_change_pause_ms | longer pause on speaker change |
| speed | float, default 1.0 |
| fit | bool |
| format | `wav` \| `mp3` |
| force | bool |

## speech.json (artifact)

```json
{
  "algo_version": "speak-v1",
  "signature": "<hex>",
  "dialog_digest": "<sha256 of dialog.json or txt>",
  "models": {"en": "...", "ru": "..."},
  "voices": {"SPEAKER_T0": "af_heart"},
  "layout": "sequential",
  "pause_ms": 250,
  "speed": 1.0,
  "fit": false,
  "format": "wav",
  "sample_rate": 24000,
  "line_count": 12,
  "cache_hits": 10,
  "cache_misses": 2,
  "overruns": 0,
  "output": "dialog/speech.wav",
  "warnings": ["chatterbox_no_presets"]
}
```

## Cache key

`sha256(algo_version | text | lang | model_id | voice_or_ref_digest | speed)` → `dialog/speech/cache/<sha>.wav`

## speak.yaml (optional, project root)

```yaml
models:
  ru: mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit
voices:
  SPEAKER_T0: af_heart
  SPEAKER_T1: am_michael
```
