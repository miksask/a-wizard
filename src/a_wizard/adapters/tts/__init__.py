"""TTS adapters (mlx-audio + fake)."""

from __future__ import annotations

from a_wizard.adapters.tts.fake import FakeTtsAdapter
from a_wizard.adapters.tts.registry import (
    DEFAULT_MODELS,
    KOKORO_VOICES,
    resolve_model_id,
    resolve_tts_adapter,
)

__all__ = [
    "DEFAULT_MODELS",
    "FakeTtsAdapter",
    "KOKORO_VOICES",
    "resolve_model_id",
    "resolve_tts_adapter",
]
