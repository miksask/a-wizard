"""Deterministic fake TTS for tests (no ML imports)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# ~12 chars per second of "speech"
_CHARS_PER_SEC = 12.0
_DEFAULT_SR = 24_000


class FakeTtsAdapter:
    adapter_id = "fake-tts"
    sample_rate = _DEFAULT_SR
    has_preset_voices = True

    def __init__(self, *, model_id: str = "fake-tts") -> None:
        self.model_id = model_id
        self.calls: list[dict[str, object]] = []

    def voices(self) -> list[str]:
        return ["fake_a", "fake_b", "fake_c", "fake_d"]

    def synthesize(
        self,
        text: str,
        *,
        lang: str,
        voice: str | None = None,
        ref_audio: Path | None = None,
        ref_text: str | None = None,
        speed: float = 1.0,
    ) -> np.ndarray:
        self.calls.append(
            {
                "text_len": len(text),
                "lang": lang,
                "voice": voice,
                "ref_audio": str(ref_audio) if ref_audio else None,
                "ref_text_len": len(ref_text) if ref_text else 0,
                "speed": speed,
            }
        )
        speed = max(0.5, float(speed) or 1.0)
        duration = max(0.05, len(text) / _CHARS_PER_SEC / speed)
        n = int(round(duration * self.sample_rate))
        # Deterministic soft tone keyed by voice/lang so tests can compare.
        seed = sum(ord(c) for c in (voice or "default") + lang) % 10_000
        t = np.arange(n, dtype=np.float32) / self.sample_rate
        freq = 220.0 + (seed % 200)
        audio = (0.2 * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)
        return audio
