# Fast Install Instructions

```
uv sync --extra dev
uv sync --extra mlx --extra diar-onnx

mkdir -p external-libs && cd external-libs
git clone --depth=1 https://github.com/FluidInference/FluidAudio.git
cd FluidAudio
swift build -c release

mkdir -p ~/.local/bin
ln -sf "$(pwd)/.build/release/fluidaudiocli" ~/.local/bin/fluidaudio
# ensure ~/.local/bin is in PATH

```