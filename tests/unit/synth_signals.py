"""Synthetic 20 ms RMS profiles and ASR words for attribution tests."""

from __future__ import annotations

import numpy as np

from a_wizard.domain.models import Word

FRAME_MS = 20


def frames(seconds: float) -> int:
    return int(round(seconds * 1000 / FRAME_MS))


def profile(
    seconds: float,
    spans: list[tuple[float, float]] | tuple = (),
    *,
    level: float = 4000.0,
    floor: float = 0.0,
    jitter: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    """Constant floor (optionally jittered) plus speech-like bursts in ``spans`` (seconds)."""
    rng = np.random.default_rng(seed)
    n = frames(seconds)
    base = np.full(n, float(floor))
    if jitter and floor:
        base *= rng.uniform(1.0 - jitter, 1.0 + jitter, n)
    speech = np.zeros(n)
    for start, end in spans:
        i0, i1 = frames(start), frames(end)
        speech[i0:i1] = level * rng.uniform(0.6, 1.4, i1 - i0)
    return np.sqrt(base**2 + speech**2)


def flat(seconds: float, spans: list[tuple[float, float, float]], floor: float = 0.0):
    """Deterministic profile: ``floor`` everywhere, exact level inside (start, end, level)."""
    x = np.full(frames(seconds), float(floor))
    for start, end, level in spans:
        x[frames(start) : frames(end)] = level
    return x


def turn_taking(seconds: float, seed: int) -> tuple[list, list]:
    """Alternating utterance spans for two parties (no overlap)."""
    rng = np.random.default_rng(seed)
    a: list[tuple[float, float]] = []
    b: list[tuple[float, float]] = []
    t = 0.5
    while t < seconds - 5:
        d = rng.uniform(0.8, 2.5)
        a.append((t, t + d))
        t += d + rng.uniform(0.5, 1.0)
        d = rng.uniform(0.5, 2.0)
        b.append((t, t + d))
        t += d + rng.uniform(0.5, 1.0)
    return a, b


def with_copy(dst: np.ndarray, src: np.ndarray, *, lag_s: float, gain: float) -> np.ndarray:
    """``dst`` plus ``gain`` × ``src`` delayed by ``lag_s`` (power sum)."""
    lag = frames(lag_s)
    delayed = np.zeros_like(src)
    if lag < len(src):
        delayed[lag:] = src[: len(src) - lag]
    return np.sqrt(dst**2 + (gain * delayed) ** 2)


def words_in(start: float, end: float, count: int, label: str = "w") -> list[Word]:
    """``count`` evenly spaced words filling 80 % of their slots inside [start, end] s."""
    step = (end - start) / count
    return [
        Word(
            int(round((start + k * step) * 1000)),
            int(round((start + k * step + 0.8 * step) * 1000)),
            f"{label}{k}",
        )
        for k in range(count)
    ]
