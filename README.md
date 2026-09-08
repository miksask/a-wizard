# A-WIZARD

Local, resume-safe multitrack ASR — fast on Apple Silicon (~20× realtime with MLX): one Whisper pass on the mix, energy-based speakers, clean dialog. For interviews, one-on-one calls, and OBS.

<p align="center">
  <img src="A-WIZARD.png" alt="UnGPT icon"/>
</p>

The project is organized with [GitHub Spec Kit](https://github.com/github/spec-kit): see `.specify/`, `specs/001-multitrack-asr-wizard/`, and `specs/002-mlx-mixdown-pipeline/`.

## Features

- **Mixdown (default)**: one ASR pass over `tracks/mix.wav` (MLX Whisper) plus speaker attribution based on source-channel energy
- Extraction of N audio tracks (ffmpeg) as mono 16 kHz PCM
- Channel modes: `plain` / `diarized` / `skipped`
- ASR-free diarization: FluidAudio (CoreML), sherpa-onnx, and experimental speakrs
- Fallback ASR: faster-whisper (non-Apple platforms)
- Merge → canonical `dialog.json` → `dialog.minimize.txt`
- Atomic manifest, project lock, freshness/invalidation
- Commands: `run`, `status`, `plan`, `init`, `configure`, `track`, `speakers`, `stage`, `doctor`, `bench diar`

## Installation

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

Expected performance on M3 16 GB / M4 24 GB: mlx-whisper turbo at roughly 5–10× real time; FluidAudio diarization at hundreds of times real time (order of magnitude).

## Running from Any Directory

After `uv sync`, the command can be run outside the `a-wizard/` directory. Below, `~/path/to/a-wizard` is the path to the project clone (zsh/bash expands the tilde).

### 1. Alias through `uv run`

In `~/.zshrc` (or `~/.bashrc`):

```bash
alias a-wizard='uv run --project ~/path/to/a-wizard a-wizard'
```

```bash
alias a-wizard='uv run --project ~/prj/_poligon/a-wizard a-wizard'
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

uv run a-wizard run /path/to/recording.project --status-only
uv run a-wizard plan /path/to/recording.project --json

# re-enter language / prompt / track modes (does not run ASR)
uv run a-wizard configure /path/to/recording.project
uv run a-wizard configure /path/to/recording.project \
  --language en --no-prompt --track 0:diarized --track 1:skipped
uv run a-wizard run /path/to/recording.project

# non-interactive
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

Primary output: `recording.project/dialog/dialog.minimize.txt`.

In mixdown mode:

1. extract → per-track WAV
2. configure: project prompt + language; track mode only (plain → `SPEAKER_T{n}`)
3. mixdown → `tracks/mix.wav` (excluding `skipped` tracks)
4. ASR (one pass with word timestamps)
5. attribute: channel RMS energy; neural diarization → `SPEAKER_T{n}D{k}`
6. merge → minimize (timing summary at the end of the run)

## Tests

```bash
uv sync --extra dev
uv run pytest
```

Synthetic fixtures only—no real recordings or tokens. Real MLX/CoreML models are used only in opt-in `@pytest.mark.slow` tests.

