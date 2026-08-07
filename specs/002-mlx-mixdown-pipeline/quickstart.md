# Quickstart: Mixdown mode

```bash
cd a-wizard
uv sync --extra mlx --extra diar-onnx

# Optional FluidAudio CLI (Apple Silicon CoreML) — see README:
# mkdir -p external-libs && cd external-libs
# git clone https://github.com/FluidInference/FluidAudio.git && cd FluidAudio
# swift build -c release
# ln -sf "$(pwd)/.build/release/fluidaudiocli" ~/.local/bin/fluidaudio
# # or: export A_WIZARD_FLUIDAUDIO_BIN=.../fluidaudiocli

uv run a-wizard doctor
uv run a-wizard run /path/to/recording.mkv --yes --preset obs-interview
# defaults to --processing-mode mixdown

# Compare diar backends
uv run a-wizard bench diar --input /path/to/track.wav --backends fluidaudio,sherpa-onnx
```

Expected: one ASR pass on `tracks/mix.wav`, speakers from channel energy + optional per-channel diarization.
