# A-WIZARD

Local, resume-safe multitrack ASR — fast on Apple Silicon (mlx-whisper turbo ~5–10× realtime): one Whisper pass on the mix, energy-based speakers, clean dialog. For interviews, one-on-one calls, and OBS.

<p align="center">
  <img src="A-WIZARD.png" alt="UnGPT icon"/>
</p>

The project is organized with [GitHub Spec Kit](https://github.com/github/spec-kit): see `.specify/`, `specs/001-multitrack-asr-wizard/`, `specs/002-mlx-mixdown-pipeline/`, `specs/003-configure-cli/`, `specs/004-pipeline-hardening/`, and `specs/005-multitrack-attribution/`.

## Features

- **Mixdown (default)**: one ASR pass over `tracks/mix.wav` (MLX Whisper) plus speaker attribution based on per-track activity (level over each track's own noise floor)
- Extraction of N audio tracks (ffmpeg) as mono 16 kHz PCM
- Channel modes: `plain` / `diarized` / `skipped`; any number of tracks, several of them diarized
- Automatic crosstalk detection between tracks (rooms that hear each other) and removal of Whisper hallucinations in silence
- ASR-free diarization: FluidAudio (CoreML), sherpa-onnx, and experimental speakrs (cached per track)
- Fallback ASR: faster-whisper (non-Apple platforms)
- Merge → canonical `dialog.json` → `dialog.minimize.ts.txt` / `dialog.minimize.ts.creation.txt` → `dialog.minimize.txt` (+ `transcript.txt` copy)
- Atomic manifest, project lock, freshness/invalidation
- Commands: `run`, `status`, `plan`, `init`, `configure`, `options`, `track`, `speakers`, `stage`, `doctor`, `bench diar`

## Installation

Short checklist: [README-FAST-INSTALL.md](README-FAST-INSTALL.md).

```bash
cd a-wizard
uv sync --extra dev

# Apple Silicon (recommended):
uv sync --extra mlx --extra diar-onnx
# diar-onnx (sherpa) is the fallback diarization backend; it is optional when FluidAudio is installed

# Non-Apple ASR fallback:
uv sync --extra asr

# Optional Python diarization quality fallback:
uv sync --extra diar-pyannote
export HF_TOKEN=hf_...   # only for pyannote-community-1
```

### FluidAudio CLI (Apple Silicon, CoreML/ANE)

The primary diarization backend. It is **not** available through Homebrew and must be built from source (Swift / Xcode CLT required). Repository: [FluidInference/FluidAudio](https://github.com/FluidInference/FluidAudio).

```bash
# from the a-wizard root (external-libs/ is in .gitignore)
mkdir -p external-libs && cd external-libs
git clone --depth=1 https://github.com/FluidInference/FluidAudio.git
cd FluidAudio
swift build -c release

# the binary is named fluidaudiocli; a-wizard looks for the name fluidaudio
mkdir -p ~/.local/bin
ln -sf "$(pwd)/.build/release/fluidaudiocli" ~/.local/bin/fluidaudio
# ensure ~/.local/bin is in PATH
```

Alternative without a symlink:

```bash
export A_WIZARD_FLUIDAUDIO_BIN=/path/to/a-wizard/external-libs/FluidAudio/.build/release/fluidaudiocli
```

Verify with `uv run a-wizard doctor` → `OK fluidaudio: ...`. Without FluidAudio, the `sherpa-onnx` fallback is used (`--extra diar-onnx`).

Requirements: Python 3.13, `ffmpeg`, and `ffprobe`. Swift is recommended on Apple Silicon for building FluidAudio.

Expected performance on M3 16 GB / M4 24 GB: mlx-whisper turbo at roughly 5–10× realtime; FluidAudio diarization at hundreds of times realtime (order of magnitude).

## Running from Any Directory

After `uv sync`, the command can be run outside the `a-wizard/` directory. Below, `~/path/to/a-wizard` is the path to the project clone (zsh/bash expands the tilde).

### 1. Alias through `uv run`

In `~/.zshrc` (or `~/.bashrc`):

```bash
alias a-wizard='uv run --project ~/path/to/a-wizard a-wizard'
```

After `source ~/.zshrc`:

```bash
a-wizard doctor
a-wizard run ./recording.mkv
```

`uv` will load the project environment; relative paths to recordings are resolved from the current directory.

### 2. Alias to the `.venv` binary

This is faster because it avoids the `uv run` wrapper. The script path remains the same after `uv sync`:

```bash
alias a-wizard='~/path/to/a-wizard/.venv/bin/a-wizard'
```

### 3. Installation in PATH

```bash
uv tool install --editable ~/path/to/a-wizard
```

The `a-wizard` command will appear in `~/.local/bin` (which must be in `PATH`). `--editable` picks up code changes without reinstallation.

Set environment variables such as `HF_TOKEN` and `A_WIZARD_FLUIDAUDIO_BIN` separately in the shell configuration; the alias does not supply them.

## Quickstart

```bash
uv run a-wizard doctor
uv run a-wizard run /path/to/recording.mkv
# new projects default to --processing-mode mixdown
# first run asks for prompt, language, and track modes (unless --preset)

uv run a-wizard run /path/to/recording.project --status-only
uv run a-wizard plan /path/to/recording.project --json

# re-enter language / prompt / track modes later (does not run ASR;
# marks only dependent stages stale, then resume with run)
uv run a-wizard configure /path/to/recording.project
uv run a-wizard configure /path/to/recording.project \
  --language en --no-prompt --track 0:diarized --track 1:skipped
uv run a-wizard run /path/to/recording.project

# non-interactive first run
uv run a-wizard run recording.mkv --preset obs-interview

# explicit adapter selection
uv run a-wizard run recording.mkv --asr-adapter mlx-whisper --diar-adapter fluidaudio

# legacy per-track mode
uv run a-wizard run recording.mkv --processing-mode per_track --preset obs-interview

# compare diarization backends
uv run a-wizard bench diar --input /path/to/track.wav --backends fluidaudio,sherpa-onnx

# test with mock engines
uv run a-wizard run recording.mkv --preset obs-interview --mock
```

Primary output: `recording.project/dialog/dialog.minimize.txt` (timed from zero: `dialog.minimize.ts.txt`; timed from file-creation clock time: `dialog.minimize.ts.creation.txt`; same untimed content also as `dialog/transcript.txt`).

In mixdown mode (`run` stage order):

1. extract → per-track WAV
2. first-run gates (during `run`): project prompt + language; track mode (`plain` → `SPEAKER_T{n}`, `diarized` → later `SPEAKER_T{n}D{k}`, `skipped` excluded from mix)
3. mixdown → `tracks/mix.wav` (excluding `skipped` tracks)
4. ASR (one pass with word timestamps)
5. attribute: per-track activity (see below); neural diarization on diarized channels → `SPEAKER_T{n}D{k}`
6. merge → minimize (timing summary at the end of the run)

To change settings after a finished (or mid) project, use `a-wizard configure` (not `run`): language/prompt changes stale mix transcription and downstream stages; track-mode-only changes keep mix ASR when possible. Extracted WAVs are never invalidated by configure.

### Speaker attribution

Each ASR word is attributed to a track by comparing tracks against their own noise floor, never by raw loudness across tracks (a microphone's room noise would otherwise beat a desktop track's digital silence and steal words from remote speakers):

- a track is a candidate for a word only when it is ≥ 9.5 dB over its local noise floor; when one candidate is ≥ 18 dB, weaker ones are ignored (loudspeaker bleed, room noise);
- several candidates are compared by level relative to each track's typical speech level, so microphones with different gains (separate rooms) are compared fairly;
- words without a clear winner join the nearest confidently attributed word; 1–2 word islands without strong evidence are merged into the surrounding speaker;
- a delayed copy of one track inside another (rooms on one call hearing each other) is detected and subtracted automatically;
- words with no speech under them that are ≥ 2 s away from real speech (Whisper hallucinations such as "Thank you.") are left out of the dialog; they stay in `transcripts/mix.raw.json` and are flagged `dropped` in `transcripts/mix.segments.json`.

`meta/attribution.json` reports per-track noise floor, speech level, active ratio, word/segment counts, detected crosstalk, and warnings (noisy channel, track without speech). In `per_track` mode the same model filters each track's own transcript at merge time (`meta/track_filter.json`): hallucinations on silent tracks and duplicates caused by crosstalk are removed.

Projects processed with an older attribution version redo only attribute → merge → minimize on the next `run` (no new ASR).

### Opt-in ASR options

Off by default; enabling them redoes ASR (minutes per recording):

```bash
uv run a-wizard options /path/to/recording.project                       # show
uv run a-wizard options /path/to/recording.project --audio-cleanup       # gate inactive tracks + level-normalize before ASR
uv run a-wizard options /path/to/recording.project --hallucination-silence 2   # Whisper hallucination_silence_threshold (s)
uv run a-wizard options /path/to/recording.project --no-audio-cleanup --no-hallucination-silence
```

`--audio-cleanup` helps recordings with several noisy microphones; it can attenuate very quiet speech in a very noisy microphone, so check the result.

## Tests

```bash
uv sync --extra dev
uv run pytest
./scripts/quality-gate.sh   # ruff + pytest coverage + build + hygiene
```

Optional local git hooks (one-time per clone):

```bash
git config core.hooksPath hooks
```

Synthetic fixtures only—no real recordings or tokens. Real MLX/CoreML models are used only in opt-in `@pytest.mark.slow` tests.
