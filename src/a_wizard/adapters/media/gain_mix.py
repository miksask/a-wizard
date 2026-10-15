"""Streamed per-frame gain mixer for 16-bit mono WAV tracks (opt-in clean audio)."""

from __future__ import annotations

import os
import tempfile
import wave
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np

from a_wizard.domain.errors import AppError, UsageError


class WavGainMixer:
    adapter_id = "numpy-gain-mix"

    def mix(
        self,
        wavs: list[Path],
        gains: list[Any],
        out: Path,
        *,
        frame_ms: int = 20,
        chunk_ms: int = 30_000,
    ) -> Path:
        """Sum ``wav_i * gain_i(t)`` (gains per ``frame_ms``, interpolated per sample)."""
        if not wavs:
            raise UsageError("no wavs to mix", code="mixdown_empty")
        if len(gains) != len(wavs):
            raise UsageError("one gain curve per input is required", code="mixdown_gains")
        out = out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            readers = [stack.enter_context(wave.open(str(p), "rb")) for p in wavs]
            rate = readers[0].getframerate()
            for path, reader in zip(wavs, readers, strict=True):
                if (
                    reader.getsampwidth() != 2
                    or reader.getnchannels() != 1
                    or reader.getframerate() != rate
                ):
                    raise AppError(f"expected 16-bit mono {rate} Hz WAV: {path}", code="wav_format")
            total = max(r.getnframes() for r in readers)
            frame_len = max(1, rate * frame_ms // 1000)
            chunk = max(frame_len, rate * chunk_ms // 1000)
            curves = [np.asarray(g, dtype=np.float64) for g in gains]
            centers = [np.arange(len(c)) * frame_len + frame_len / 2.0 for c in curves]
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{out.name}.", suffix=".wav", dir=str(out.parent)
            )
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                with wave.open(str(tmp), "wb") as writer:
                    writer.setnchannels(1)
                    writer.setsampwidth(2)
                    writer.setframerate(rate)
                    for start in range(0, total, chunk):
                        length = min(chunk, total - start)
                        acc = np.zeros(length, dtype=np.float64)
                        positions = np.arange(start, start + length, dtype=np.float64)
                        for reader, curve, center in zip(readers, curves, centers, strict=True):
                            raw = reader.readframes(length)
                            data = np.frombuffer(raw, dtype="<i2").astype(np.float64)
                            if len(data) == 0:
                                continue
                            gain = (
                                np.interp(positions[: len(data)], center, curve)
                                if len(curve)
                                else np.ones(len(data))
                            )
                            acc[: len(data)] += data * gain
                        pcm = np.clip(np.round(acc), -32768, 32767).astype("<i2")
                        writer.writeframes(pcm.tobytes())
                os.replace(tmp, out)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
        return out
