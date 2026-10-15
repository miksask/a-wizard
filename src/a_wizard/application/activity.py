"""Per-track activity model: local noise floors, speech levels, word evidence."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from a_wizard.application.crosstalk import (
    CrosstalkLink,
    compensate_crosstalk,
    detect_crosstalk,
)
from a_wizard.domain.activity import DEFAULT_ACTIVITY_PARAMS, ActivityParams

_BATCH = 2048


@dataclass(frozen=True)
class TrackEvidence:
    energy: float
    snr_db: float
    raw_snr_db: float
    score: float


@dataclass
class TrackActivity:
    index: int
    rms: np.ndarray
    raw_rms: np.ndarray
    floor: np.ndarray
    raw_floor: np.ndarray
    level: float
    floor_median: float
    active_ratio: float

    @property
    def dynamic(self) -> float:
        return max(self.level - self.floor_median, 1.0)


def _rolling_percentile(
    x: np.ndarray,
    centers: np.ndarray,
    half: int,
    q: float,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    values = x.astype(np.float64)
    if mask is not None:
        values = np.where(mask, values, np.nan)
    padded = np.pad(values, (half, half), constant_values=np.nan)
    windows = sliding_window_view(padded, 2 * half + 1)
    out = np.empty(len(centers), dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        for start in range(0, len(centers), _BATCH):
            chunk = centers[start : start + _BATCH]
            batch = windows[chunk]
            if np.isnan(batch).any():
                out[start : start + len(chunk)] = np.nanpercentile(batch, q, axis=1)
            else:
                out[start : start + len(chunk)] = np.percentile(batch, q, axis=1)
    return out


def noise_floor(rms: np.ndarray, params: ActivityParams = DEFAULT_ACTIVITY_PARAMS) -> np.ndarray:
    """Two-pass rolling noise floor: low envelope, then median of frames near it."""
    n = len(rms)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    w = params.window_ms
    half = max(1, params.floor_half_window_ms // w)
    step = max(1, params.floor_step_ms // w)
    centers = np.arange(0, n, step)
    frames = np.arange(n)
    low = _rolling_percentile(rms, centers, half, params.floor_low_percentile)
    low = np.maximum(np.nan_to_num(low, nan=params.min_floor_rms), params.min_floor_rms)
    band = 10.0 ** (params.floor_noise_band_db / 20.0)
    noise_frames = rms <= np.interp(frames, centers, low) * band
    typical = _rolling_percentile(
        rms, centers, half, params.floor_noise_percentile, mask=noise_frames
    )
    typical = np.where(np.isnan(typical), low, typical)
    return np.maximum(np.interp(frames, centers, typical), params.min_floor_rms)


def speech_level(
    rms: np.ndarray, floor: np.ndarray, params: ActivityParams = DEFAULT_ACTIVITY_PARAMS
) -> tuple[float, float, float]:
    """Return (speech level, median floor, active frame ratio)."""
    if len(rms) == 0:
        floor_median = params.min_floor_rms
        return floor_median * 10.0 ** ((params.gate_db + 10.0) / 20.0), floor_median, 0.0
    gate = 10.0 ** (params.gate_db / 20.0)
    active = rms >= floor * gate
    floor_median = float(np.median(floor))
    if int(active.sum()) >= params.min_level_frames:
        level = float(np.percentile(rms[active], params.level_percentile))
    else:
        level = floor_median * 10.0 ** ((params.gate_db + 10.0) / 20.0)
    return max(level, floor_median * gate), floor_median, float(active.mean())


@dataclass
class ActivityModel:
    tracks: dict[int, TrackActivity]
    links: list[CrosstalkLink]
    params: ActivityParams
    n_frames: int

    def window(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        p = self.params
        start, end = float(start_ms), float(end_ms)
        if end - start < p.min_word_ms:
            center = (start + end) / 2.0
            start, end = center - p.min_word_ms / 2.0, center + p.min_word_ms / 2.0
        i0 = max(0, int(math.floor(start / p.window_ms)))
        i1 = max(i0 + 1, int(math.ceil(end / p.window_ms)))
        return min(i0, self.n_frames), min(i1, self.n_frames)

    def evidence(self, start_ms: int, end_ms: int) -> dict[int, TrackEvidence]:
        i0, i1 = self.window(start_ms, end_ms)
        q = self.params.word_percentile
        out: dict[int, TrackEvidence] = {}
        for index, track in self.tracks.items():
            if i1 <= i0:
                out[index] = TrackEvidence(0.0, -math.inf, -math.inf, 0.0)
                continue
            energy, snr = _level(track.rms, track.floor, i0, i1, q)
            if track.rms is track.raw_rms:
                raw_snr = snr
            else:
                _, raw_snr = _level(track.raw_rms, track.raw_floor, i0, i1, q)
            floor = float(track.floor[i0:i1].mean())
            score = max(energy - floor, 0.0) / track.dynamic
            out[index] = TrackEvidence(energy, snr, raw_snr, score)
        return out

    def links_report(self) -> list[dict[str, Any]]:
        return [link.to_dict(self.params.window_ms) for link in self.links]


def _level(
    rms: np.ndarray, floor: np.ndarray, i0: int, i1: int, q: float
) -> tuple[float, float]:
    energy = float(np.percentile(rms[i0:i1], q))
    base = max(float(floor[i0:i1].mean()), 1e-9)
    return energy, 20.0 * math.log10(max(energy, 1e-9) / base)


def build_activity(
    profiles: dict[int, Any],
    params: ActivityParams = DEFAULT_ACTIVITY_PARAMS,
    *,
    crosstalk: bool = True,
) -> ActivityModel:
    """Build per-track activity from RMS profiles (missing profiles count as silence)."""
    arrays = {
        index: (np.asarray(p, dtype=np.float64) if p is not None else np.zeros(0))
        for index, p in profiles.items()
    }
    n = max((len(a) for a in arrays.values()), default=0)
    arrays = {i: np.pad(a, (0, n - len(a))) for i, a in arrays.items()}
    raw_floors = {i: noise_floor(a, params) for i, a in arrays.items()}
    links = detect_crosstalk(arrays, raw_floors, params) if crosstalk else []
    compensated = compensate_crosstalk(arrays, links, raw_floors, params)
    tracks: dict[int, TrackActivity] = {}
    for index, raw in arrays.items():
        rms = compensated[index]
        floor = raw_floors[index] if rms is raw else noise_floor(rms, params)
        level, floor_median, active_ratio = speech_level(rms, floor, params)
        tracks[index] = TrackActivity(
            index=index,
            rms=rms,
            raw_rms=raw,
            floor=floor,
            raw_floor=raw_floors[index],
            level=level,
            floor_median=floor_median,
            active_ratio=active_ratio,
        )
    return ActivityModel(tracks=tracks, links=links, params=params, n_frames=n)
