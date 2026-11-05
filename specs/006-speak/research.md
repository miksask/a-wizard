# Research: Speak (TTS)

**Date**: 2026-10-28 | **Spec**: [spec.md](./spec.md)

## R1. Stay inside a-wizard vs separate project

**Decision**: Implement as `a-wizard speak` inside this repo when the primary input is project `dialog.json`; arbitrary txt is a secondary mode of the same synthesizer.

**Rationale**: Speak consumes ASR project artifacts one-way (merge required). It does not extend the run DAG. Ports/adapters, local-first logging, and atomic writes already match the constitution. A separate repo would duplicate CLI/doctor/lock patterns for little gain.

**Alternatives considered**: Sibling CLI only — rejected for dialog.json path; can revisit if TTS grows into a product with its own state model.

## R2. MLX model choices for en / ru / pl

**Decision**:

| Lang | Default model | Why |
|------|---------------|-----|
| en | `mlx-community/Kokoro-82M-bf16` | Fast on Apple Silicon; preset voices; no ru/pl |
| ru | `mlx-community/chatterbox-multilingual-v3` | MLX; supports Russian; cloning via `ref_audio` |
| pl | `mlx-community/chatterbox-multilingual-v3` | Same; Polish in Chatterbox language list |

**Rationale**: User required normal Russian and Polish, preferred MLX for all three, and wanted English to stay on a fast model. Per-language overrides allow swapping ru/pl later without code changes.

**Alternatives considered**:

- **KugelAudio** (`kugelaudio/kugelaudio-0-open`): strong European languages including ru/pl, but ~7B / ~17 GB — too heavy as default.
- **OmniVoice**: 646+ languages + cloning, but needs `ref_text` carefully aligned; heavier ops.
- **Qwen3-TTS CustomVoice**: presets + multilingual; good override candidate if Chatterbox quality disappoints.

## R3. Chatterbox has no preset voices

**Decision**: Without `--clone` or `--ref`, ru/pl still run on Chatterbox. The MLX checkpoint has no `conds.safetensors`, so speak creates a local default reference once (Kokoro, cached under `~/.cache/a-wizard/tts/`) and passes it as `ref_audio`. Speakers share that voice until the operator supplies `--ref` or `--clone`. `--model ru=…` can still switch to a preset-capable model.

## R4. Not a DAG stage

**Decision**: `detect_next_action` still ends at `minimize`. Speak is an explicit command; `speech.json` holds its own signature outside `SCHEMA_VERSION`.

**Rationale**: Avoid downloading TTS on every `run`; keep ASR pipeline signatures stable.

## R5. Cache and rendering

**Decision**: Per-line atomic WAV cache keyed by sha256(text, lang, model, voice|ref digest, speed, algo version). Sequential concat with pauses by default; timeline placement with optional ffmpeg `atempo` fit ≤ 1.5×.

**Rationale**: Matches resume-safe constitution; makes voice iteration cheap.

## R6. Library

**Decision**: Optional extra `tts` → `mlx-audio>=0.6.2` plus Kokoro's text frontend (`misaki`, `num2words`, `spacy`, `phonemizer-fork`, `espeakng-loader`) on darwin/arm64. Lazy import in adapters only. Fake adapter for CI.

**API**: `mlx_audio.tts.utils.load_model` + `model.generate(...)` / `generate_audio`; Kokoro uses `voice=` / `lang_code=`; Chatterbox uses `ref_audio=` / `lang_code=`.
