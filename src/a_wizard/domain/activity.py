"""Parameters of the track activity model (pure data, no numpy)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ActivityParams:
    window_ms: int = 20
    floor_half_window_ms: int = 15_000
    floor_step_ms: int = 500
    floor_low_percentile: float = 10.0
    floor_noise_band_db: float = 6.0
    floor_noise_percentile: float = 50.0
    min_floor_rms: float = 30.0
    gate_db: float = 9.5
    strong_snr_db: float = 18.0
    min_word_ms: int = 100
    word_percentile: float = 75.0
    level_percentile: float = 75.0
    min_level_frames: int = 50
    dominance_ratio: float = 1.25
    island_max_words: int = 2
    island_max_ms: int = 700
    island_max_gap_ms: int = 1500
    island_strong_ratio: float = 3.0
    hallucination_max_snr_db: float = 6.0
    hallucination_gap_ms: int = 2000
    boundary_majority: float = 0.6
    crosstalk_max_lag_ms: int = 1000
    crosstalk_min_corr: float = 0.3
    crosstalk_min_peak_margin: float = 0.1
    crosstalk_strong_db: float = 20.0
    crosstalk_over_subtraction: float = 2.0
    crosstalk_spread_ms: int = 40
    crosstalk_max_gain: float = 4.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CleanupParams:
    gate_db: float = 6.0
    pre_roll_ms: int = 120
    hangover_ms: int = 400
    closed_gain_db: float = -18.0
    target_level_dbfs: float = -20.0
    max_gain_db: float = 12.0
    chunk_ms: int = 30_000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_ACTIVITY_PARAMS = ActivityParams()
DEFAULT_CLEANUP_PARAMS = CleanupParams()
