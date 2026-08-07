# CLI contract additions (002)

## `a-wizard run|init`

- `--processing-mode {mixdown,per_track}` — default `mixdown` for new projects
- `--asr-adapter {auto,mlx-whisper,faster-whisper,mock-asr}`
- `--diar-adapter {auto,fluidaudio,sherpa-onnx,speakrs-coreml,pyannote-community-1,mock-diar}`

## `a-wizard doctor`

Checks: ffmpeg/ffprobe, mlx_whisper, fluidaudio binary, sherpa_onnx, Swift (hint), model caches.

## `a-wizard bench diar`

```
a-wizard bench diar --input WAV [--backends fluidaudio,sherpa-onnx,speakrs-coreml]
```

Prints table: backend, wall seconds, RTFx, speaker count, error.
