"""Channel RMS energy profiling."""

from __future__ import annotations

from pathlib import Path

import wave

from a_wizard.domain.errors import AppError


class NumpyChannelEnergyProfiler:
    """RMS energy windows (default 20 ms) for a mono PCM WAV."""

    def profile(self, wav: Path, *, window_ms: int = 20):
        try:
            import numpy as np
        except ImportError as e:
            raise AppError(
                "numpy is required for energy profiling",
                code="numpy_missing",
                next_step="uv sync",
                cause=e,
            ) from e

        wav = Path(wav)
        with wave.open(str(wav), "rb") as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            rate = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
        if sw != 2:
            raise AppError(f"expected 16-bit PCM, got sampwidth={sw}", code="wav_format")
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if nch > 1:
            audio = audio.reshape(-1, nch).mean(axis=1)
        win = max(1, int(rate * window_ms / 1000))
        n = (len(audio) // win) * win
        if n == 0:
            return np.zeros(0, dtype=np.float32)
        frames = audio[:n].reshape(-1, win)
        rms = np.sqrt(np.mean(frames * frames, axis=1)).astype(np.float32)
        return rms


def mean_energy(profile, start_ms: int, end_ms: int, *, window_ms: int = 20) -> float:
    import numpy as np

    if profile is None or len(profile) == 0:
        return 0.0
    i0 = max(0, int(start_ms // window_ms))
    i1 = min(len(profile), max(i0 + 1, int(np.ceil(end_ms / window_ms))))
    return float(np.mean(profile[i0:i1])) if i1 > i0 else 0.0
