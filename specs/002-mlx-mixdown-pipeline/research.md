# Research: MLX Mixdown Pipeline

**Feature**: 002-mlx-mixdown-pipeline | **Date**: 2026-08-06

## Decisions

### D1. Mixdown + channel energy first
- One MLX ASR pass on `tracks/mix.wav`.
- Speakers attributed by RMS energy of source tracks (OBS track 0 = employee mic).
- Neural diarization only for channels marked `diarized`.

### D2. ASR: mlx-whisper turbo
- Default: `mlx-community/whisper-large-v3-turbo`.
- Flags: `word_timestamps=True`, `condition_on_previous_text=False`.
- Fallback: faster-whisper (non-Apple).

### D3. Diarization backends
- Primary: FluidAudio CLI offline (CoreML/ANE, Community-1 pipeline).
- Fallback: sherpa-onnx CPU (segmentation 3.0 + TitaNet Small).
- Experimental: speakrs coreml (bench only).
- Optional Python: pyannote community-1 (not 3.1).
- WhisperX removed.

### D4. Track modes in mixdown
- `plain` = single-speaker channel → fixed id `SPEAKER_T{n}`.
- `diarized` = multi-speaker channel → neural diarize that channel only → `SPEAKER_T{n}D{k}`.
- `skipped` = excluded from mix.

## Benchmark orientation

| Component | Expected on M3/M4 |
|-----------|-------------------|
| mlx-whisper turbo | ~5–10× realtime |
| FluidAudio CoreML | hundreds× realtime for diarization-only |
| speakrs coreml | experimental, similar order |
| WhisperX CPU (old) | ~1× or slower end-to-end |

## Supersedes

- Feature 001 research D6 (faster-whisper + WhisperX defaults) superseded for Apple Silicon defaults.
