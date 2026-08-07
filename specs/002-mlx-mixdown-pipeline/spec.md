# Feature Specification: MLX Mixdown Pipeline

**Feature Branch**: `002-mlx-mixdown-pipeline`

**Created**: 2026-08-06

**Status**: Draft

**Input**: MLX ASR + CoreML diarization + mixdown mode with channel-energy speaker attribution

## User Scenarios & Testing

### User Story 1 - Fast mixdown transcription on Apple Silicon (Priority: P1)

The operator runs `a-wizard run VIDEO --processing-mode mixdown`. The system extracts the tracks, mixes them into one WAV, performs one ASR pass through MLX Whisper, and assigns speakers based on source-channel energy.

**Why this priority**: This provides the main speed improvement on M3/M4.

**Independent Test**: A synthetic two-track fixture with mock ASR/energy produces correct segments without WhisperX.

**Acceptance Scenarios**:

1. **Given** a two-track video, **When** a mixdown run completes, **Then** `tracks/mix.wav` exists and exactly one ASR pass was performed.
2. **Given** track 0 is plain/`__EMPLOYEE__` and track 1 is diarized, **When** attribution runs, **Then** words dominated by track 0 energy receive `__EMPLOYEE__`.

---

### User Story 2 - Separated neural diarization (Priority: P1)

For channels with multiple voices (`diarized`), the system invokes a standalone diarizer (FluidAudio / sherpa-onnx) only on that channel and maps sub-speakers to ASR words.

**Why this priority**: This eliminates the repeated ASR pass inside WhisperX.

**Independent Test**: A mock diarizer returns turns; attribution applies them only within the channel windows.

---

### User Story 3 - Adapter auto-selection (Priority: P2)

On Apple Silicon, doctor/run select mlx-whisper plus fluidaudio when available, otherwise sherpa-onnx; other platforms use the faster-whisper fallback.

---

### User Story 4 - Bench diar backends (Priority: P3)

`a-wizard bench diar --input WAV` compares RTFx for fluidaudio / sherpa-onnx / speakrs-coreml.

## Requirements

- **FR-001**: System MUST support `processing_mode: mixdown | per_track` (default mixdown for new projects).
- **FR-002**: Mixdown MUST mix non-skipped tracks via ffmpeg amix into `tracks/mix.wav`.
- **FR-003**: ASR MUST use word-level timestamps; default backend mlx-whisper turbo on Apple Silicon.
- **FR-004**: Speaker attribution MUST use per-channel RMS energy before neural diarization.
- **FR-005**: Neural diarization MUST be ASR-free (`diarize(wav) -> turns`).
- **FR-006**: Default diar adapter: fluidaudio; fallback: sherpa-onnx; experimental: speakrs-coreml.
- **FR-007**: WhisperX / pyannote 3.1 MUST NOT be required; optional community-1 only via extra.
- **FR-008**: Changing channel roles MUST invalidate attribute/merge/minimize but keep mix ASR if mix wav unchanged.

## Success Criteria

- **SC-001**: Mixdown e2e with mocks completes without importing whisperx.
- **SC-002**: Deterministic energy attribution assigns alternating windows to correct channels.
- **SC-003**: `doctor` reports mlx / fluidaudio / sherpa availability with install hints.
- **SC-004**: Existing per_track mode still works with new adapter interfaces.
