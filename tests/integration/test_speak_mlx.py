"""Optional real mlx-audio smoke tests (skipped when package missing)."""

from __future__ import annotations

import pytest

pytest.importorskip("mlx_audio")

from a_wizard.adapters.tts.registry import resolve_model_id, resolve_tts_adapter


@pytest.mark.slow
def test_kokoro_english_smoke():
    model_id = resolve_model_id("en")
    engine = resolve_tts_adapter(model_id, mock=False)
    audio = engine.synthesize("Hello from a-wizard.", lang="en", voice="af_heart")
    assert audio is not None
    assert len(audio) > 1000


@pytest.mark.slow
@pytest.mark.parametrize("lang,text", [("ru", "Привет."), ("pl", "Cześć.")])
def test_chatterbox_multilingual_smoke(lang: str, text: str):
    model_id = resolve_model_id(lang)
    engine = resolve_tts_adapter(model_id, mock=False)
    audio = engine.synthesize(text, lang=lang)
    assert audio is not None
    assert len(audio) > 100
