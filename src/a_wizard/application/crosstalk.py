"""Crosstalk (bleed) detection and compensation between track energy envelopes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from a_wizard.domain.activity import ActivityParams

_EXCESS_CAP_DB = 40.0
_MIN_GAIN = 0.01


@dataclass(frozen=True)
class CrosstalkLink:
    """``dst`` contains a copy of ``src`` delayed by ``lag_frames``.

    Links with ``lag_frames == 0`` describe tracks that capture the same sound at the
    same time (same room); their direction is unknown, so they are reported but not
    compensated.
    """

    src: int
    dst: int
    lag_frames: int
    gain: float
    corr: float

    @property
    def compensated(self) -> bool:
        return self.lag_frames > 0 and self.gain > 0

    def to_dict(self, window_ms: int) -> dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "lag_ms": int(self.lag_frames * window_ms),
            "gain": round(float(self.gain), 4),
            "corr": round(float(self.corr), 4),
            "compensated": self.compensated,
        }


def excess_db(rms: np.ndarray, floor: np.ndarray) -> np.ndarray:
    """Level over the noise floor in dB, clipped to [0, 40]."""
    safe_floor = np.maximum(floor, 1e-9)
    ratio = np.maximum(rms, safe_floor) / safe_floor
    return np.clip(20.0 * np.log10(ratio), 0.0, _EXCESS_CAP_DB)


def lagged_correlation(a: np.ndarray, b: np.ndarray, max_lag: int) -> np.ndarray:
    """Pearson correlation of ``a[t]`` with ``b[t + lag]`` for ``lag`` in ``0..max_lag``."""
    n = min(len(a), len(b))
    out = np.zeros(max_lag + 1, dtype=np.float64)
    if n < 2:
        return out
    a = a[:n].astype(np.float64)
    b = b[:n].astype(np.float64)
    ca = np.concatenate([[0.0], np.cumsum(a)])
    ca2 = np.concatenate([[0.0], np.cumsum(a * a)])
    cb = np.concatenate([[0.0], np.cumsum(b)])
    cb2 = np.concatenate([[0.0], np.cumsum(b * b)])
    for lag in range(max_lag + 1):
        m = n - lag
        if m < 2:
            break
        mean_a = ca[m] / m
        mean_b = (cb[n] - cb[lag]) / m
        var_a = ca2[m] / m - mean_a * mean_a
        var_b = (cb2[n] - cb2[lag]) / m - mean_b * mean_b
        if var_a <= 1e-12 or var_b <= 1e-12:
            continue
        cov = float(np.dot(a[:m], b[lag:])) / m - mean_a * mean_b
        out[lag] = cov / math.sqrt(var_a * var_b)
    return out


def _side_peak(curve: np.ndarray, max_lag: int) -> tuple[int, float]:
    """Best lag ≥ 2 frames that is not on the outer edge of the search range."""
    if max_lag < 3:
        return 0, -1.0
    inner = curve[2:max_lag]
    if len(inner) == 0:
        return 0, -1.0
    lag = int(np.argmax(inner)) + 2
    return lag, float(curve[lag])


def _estimate_gain(
    src: np.ndarray,
    dst: np.ndarray,
    dst_floor: np.ndarray,
    strong_src: np.ndarray,
    lag: int,
) -> float:
    n = len(src)
    if lag >= n:
        return 0.0
    idx = np.nonzero(strong_src[: n - lag])[0]
    if len(idx) == 0:
        return 0.0
    excess_power = np.maximum(dst[idx + lag] ** 2 - dst_floor[idx + lag] ** 2, 0.0)
    ratios = np.sqrt(excess_power) / np.maximum(src[idx], 1e-9)
    return float(np.median(ratios))


def detect_crosstalk(
    rms: dict[int, np.ndarray],
    floors: dict[int, np.ndarray],
    params: ActivityParams,
) -> list[CrosstalkLink]:
    """Find delayed copies of one track inside another from their energy envelopes."""
    indices = sorted(rms)
    if len(indices) < 2:
        return []
    max_lag = max(0, params.crosstalk_max_lag_ms // params.window_ms)
    excess = {i: excess_db(rms[i], floors[i]) for i in indices}
    strong = {i: excess[i] >= params.crosstalk_strong_db for i in indices}
    links: list[CrosstalkLink] = []
    for pos, a in enumerate(indices):
        for b in indices[pos + 1 :]:
            forward = lagged_correlation(excess[a], excess[b], max_lag)  # b lags a
            backward = lagged_correlation(excess[b], excess[a], max_lag)  # a lags b
            full = np.concatenate([backward[:0:-1], forward])
            baseline = float(np.median(full))
            at_zero = float(forward[0])
            found = False
            for src, dst, curve in ((a, b, forward), (b, a, backward)):
                lag, peak = _side_peak(curve, max_lag)
                if (
                    peak < params.crosstalk_min_corr
                    or peak - baseline < params.crosstalk_min_peak_margin
                    or peak - at_zero < params.crosstalk_min_peak_margin / 2
                ):
                    continue
                if int(strong[src].sum()) < params.min_level_frames:
                    continue
                gain = _estimate_gain(rms[src], rms[dst], floors[dst], strong[src], lag)
                if gain < _MIN_GAIN:
                    continue
                links.append(
                    CrosstalkLink(src, dst, lag, min(gain, params.crosstalk_max_gain), peak)
                )
                found = True
            if (
                not found
                and at_zero >= params.crosstalk_min_corr
                and at_zero - baseline >= params.crosstalk_min_peak_margin
            ):
                links.append(CrosstalkLink(a, b, 0, 0.0, at_zero))
    return links


def _max_filter(x: np.ndarray, half: int) -> np.ndarray:
    if half <= 0 or len(x) == 0:
        return x
    padded = np.pad(x, (half, half), mode="edge")
    return sliding_window_view(padded, 2 * half + 1).max(axis=1)


def compensate_crosstalk(
    rms: dict[int, np.ndarray],
    links: list[CrosstalkLink],
    floors: dict[int, np.ndarray],
    params: ActivityParams,
) -> dict[int, np.ndarray]:
    """Subtract each detected copy in the power domain, never below the noise floor."""
    out = dict(rms)
    active = [link for link in links if link.compensated]
    if not active:
        return out
    spread = max(0, params.crosstalk_spread_ms // params.window_ms)
    alpha = params.crosstalk_over_subtraction
    subtract: dict[int, np.ndarray] = {}
    for link in active:
        src = rms[link.src]
        n = len(rms[link.dst])
        delayed = np.zeros(n, dtype=np.float64)
        if link.lag_frames < n:
            delayed[link.lag_frames :] = src[: n - link.lag_frames]
        ref = _max_filter(delayed, spread)
        acc = subtract.setdefault(link.dst, np.zeros(n, dtype=np.float64))
        acc += alpha * (link.gain**2) * ref**2
    for dst, amount in subtract.items():
        original = rms[dst].astype(np.float64)
        lower = np.minimum(original, floors[dst]) ** 2
        out[dst] = np.sqrt(np.maximum(original**2 - amount, lower))
    return out
