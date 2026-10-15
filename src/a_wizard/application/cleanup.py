"""Opt-in ASR input cleanup: per-frame gains derived from the activity model."""

from __future__ import annotations

import numpy as np

from a_wizard.application.activity import ActivityModel
from a_wizard.domain.activity import DEFAULT_CLEANUP_PARAMS, CleanupParams

_FULL_SCALE = 32768.0


def dilate(mask: np.ndarray, before: int, after: int) -> np.ndarray:
    """Open frame ``k`` when any active frame lies in ``[k - after, k + before]``."""
    if len(mask) == 0 or (before <= 0 and after <= 0):
        return mask.astype(bool).copy()
    kernel = np.ones(before + after + 1, dtype=np.int64)
    conv = np.convolve(mask.astype(np.int64), kernel, mode="full")
    return conv[before : before + len(mask)] > 0


def cleanup_gains(
    model: ActivityModel, params: CleanupParams = DEFAULT_CLEANUP_PARAMS
) -> dict[int, np.ndarray]:
    """Gain per 20 ms frame: inactive frames attenuated, speech levels normalized."""
    frame_ms = model.params.window_ms
    gate = 10.0 ** (params.gate_db / 20.0)
    closed = 10.0 ** (params.closed_gain_db / 20.0)
    target = _FULL_SCALE * 10.0 ** (params.target_level_dbfs / 20.0)
    limit = 10.0 ** (params.max_gain_db / 20.0)
    before = max(0, params.pre_roll_ms // frame_ms)
    after = max(0, params.hangover_ms // frame_ms)
    smooth = np.ones(3) / 3.0
    gains: dict[int, np.ndarray] = {}
    for index, track in model.tracks.items():
        opened = dilate(track.rms >= track.floor * gate, before, after)
        curve = np.where(opened, 1.0, closed)
        if len(curve) >= 3:
            curve = np.convolve(curve, smooth, mode="same")
        normalize = float(np.clip(target / max(track.level, 1.0), 1.0 / limit, limit))
        gains[index] = (curve * normalize).astype(np.float32)
    return gains
