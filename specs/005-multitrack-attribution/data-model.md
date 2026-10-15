# Data Model: Multitrack Attribution

## ActivityParams (domain, frozen)

| Field | Default | Meaning |
|-------|---------|---------|
| `window_ms` | 20 | RMS frame size (energy cache) |
| `floor_half_window_ms` | 15000 | Half width of the rolling noise-floor window |
| `floor_step_ms` | 500 | Step between floor estimates (interpolated) |
| `floor_low_percentile` | 10 | Lower envelope percentile (pass 1) |
| `floor_noise_band_db` | 6.0 | Frames within this band over the envelope count as noise |
| `floor_noise_percentile` | 50 | Percentile of noise frames (pass 2) |
| `min_floor_rms` | 30.0 | Absolute floor (≈ −61 dBFS) for digital silence |
| `gate_db` | 9.5 | Speech gate over floor |
| `strong_snr_db` | 18.0 | When any candidate reaches it, weaker candidates are dropped |
| `min_word_ms` | 100 | Minimum word window |
| `word_percentile` | 75 | Word level statistic over frames |
| `level_percentile` | 75 | Speech level over active frames |
| `dominance_ratio` | 1.25 | Relative-level ratio for a confident winner |
| `island_max_words` / `island_max_ms` / `island_max_gap_ms` | 2 / 700 / 1500 | Island smoothing limits |
| `island_strong_ratio` | 3.0 | Relative-level advantage that keeps an island |
| `hallucination_max_snr_db` | 6.0 | Words below this on every track are droppable |
| `hallucination_gap_ms` | 2000 | Isolation required to drop |
| `boundary_majority` | 0.6 | Turn overlap share for a strong diarized assignment |
| `crosstalk_max_lag_ms` | 1000 | Lag search range |
| `crosstalk_min_corr` / `crosstalk_min_peak_margin` | 0.3 / 0.1 | Detection thresholds |
| `crosstalk_over_subtraction` | 2.0 | Power over-subtraction factor |
| `crosstalk_spread_ms` | 40 | Reference max-filter half width |

Serialized into the attribute signature with `ATTRIBUTION_ALGORITHM_VERSION = "a-wizard-2-attr-v2"`.

## CleanupParams (domain, frozen)

| Field | Default |
|-------|---------|
| `gate_db` | 6.0 |
| `pre_roll_ms` / `hangover_ms` | 120 / 400 |
| `closed_gain_db` | −18.0 |
| `target_level_dbfs` | −20.0 |
| `max_gain_db` | 12.0 |

Serialized into mixdown / per-track transcribe signatures with `CLEANUP_ALGORITHM_VERSION` only when `audio_cleanup` is on.

## Word (extended)

Existing `start_ms`, `end_ms`, `text`, `speaker`, `channel`, `ambiguous`; new optional flags serialized only when true:

- `silent`: no track carried speech in the word window
- `dropped`: excluded from segments as an isolated hallucination

`ambiguous` is true when the channel came from context, smoothing, or fallback rather than from energy alone.

## Attribution report (`meta/attribution.json`)

See [contracts/attribution-report.schema.json](./contracts/attribution-report.schema.json). Keeps legacy keys (`word_count`, `ambiguous_count`, `ambiguous_ratio`, `channels`) and adds `algorithm_version`, `kept_word_count`, `silent_count`, `context_resolved_count`, `smoothed_count`, `dropped_count`, `fallback`, `tracks[]`, `crosstalk[]`, `warnings[]`.

## Per-track filter report (`meta/track_filter.json`)

`algorithm_version`, `fallback`, `crosstalk[]`, `tracks[] {index, mode, unit ("words"|"segments"), input_count, kept_count, dropped_hallucination, dropped_crosstalk, dropped_dominated}`, `warnings[]`.

## Diarization cache

- `meta/diar/track_{n}.json`: list of turns `{start_ms, end_ms, speaker}` (normalized labels)
- `meta/diar/track_{n}.meta.json`: `{wav_sha256, adapter_id, algorithm_version: "a-wizard-2-diar-v1"}`

Valid only when all three match. Adapters with `cacheable = False` (mock) always re-run.

## Per-track words

`transcripts/track_{n}.words.json`: list of `Word` dicts with track-scoped speakers and `channel = n`. Optional output of `transcribe:{n}` (not required for freshness, so older projects stay fresh).

## Manifest additions (schema_version 2)

`transcription_defaults`:

- `audio_cleanup`: bool, optional, default false
- `hallucination_silence_threshold`: number (seconds) or null, optional, default null

Absent keys equal defaults; signatures ignore them while at defaults.

## Invalidation additions

| Change | Stale |
|--------|-------|
| attribution algorithm / params | attribute + merge + minimize (mixdown); merge + minimize (per_track) |
| `audio_cleanup` | mixdown + transcribe:mix + attribute + merge + minimize; per_track: active transcribe:N + merge + minimize |
| `hallucination_silence_threshold` | same as ASR config (`asr_config`) |
