"""TTS model registry override order tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from a_wizard.adapters.tts.registry import (
    DEFAULT_MODELS,
    assign_voices,
    env_model_overrides,
    model_has_preset_voices,
    parse_kv_flags,
    resolve_model_id,
)
from a_wizard.domain.errors import UsageError


def test_defaults():
    assert "Kokoro" in resolve_model_id("en")
    assert "chatterbox" in resolve_model_id("ru").lower()
    assert "chatterbox" in resolve_model_id("pl").lower()


def test_override_order_flag_beats_yaml_beats_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("A_WIZARD_TTS_MODEL_RU", "env-model")
    assert resolve_model_id("ru") == "env-model"
    assert resolve_model_id("ru", yaml_models={"ru": "yaml-model"}) == "yaml-model"
    assert (
        resolve_model_id(
            "ru",
            yaml_models={"ru": "yaml-model"},
            flag_models={"ru": "flag-model"},
        )
        == "flag-model"
    )


def test_env_model_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("A_WIZARD_TTS_MODEL_PL", "pl-env")
    monkeypatch.setenv("A_WIZARD_TTS_MODEL_EN", "en-env")
    overs = env_model_overrides()
    assert overs["pl"] == "pl-env"
    assert overs["en"] == "en-env"


def test_parse_kv_flags():
    assert parse_kv_flags(["en=foo", "ru=bar"], what="model") == {
        "en": "foo",
        "ru": "bar",
    }
    with pytest.raises(UsageError):
        parse_kv_flags(["nocolon"], what="model")


def test_assign_voices_kokoro_presets():
    models = {"en": DEFAULT_MODELS["en"]}
    voices, warnings = assign_voices(
        ["SPEAKER_T0", "SPEAKER_T1"],
        models_by_lang=models,
        speaker_langs={"SPEAKER_T0": "en", "SPEAKER_T1": "en"},
    )
    assert voices["SPEAKER_T0"] != voices["SPEAKER_T1"]
    assert warnings == []


def test_assign_voices_chatterbox_warns():
    models = {"ru": DEFAULT_MODELS["ru"]}
    voices, warnings = assign_voices(
        ["SPEAKER_T0", "SPEAKER_T1"],
        models_by_lang=models,
        speaker_langs={"SPEAKER_T0": "ru", "SPEAKER_T1": "ru"},
    )
    assert voices["SPEAKER_T0"] is None
    assert "chatterbox_no_presets" in warnings


def test_assign_voices_flag_override():
    models = {"en": DEFAULT_MODELS["en"]}
    voices, _ = assign_voices(
        ["SPEAKER_T0"],
        models_by_lang=models,
        speaker_langs={"SPEAKER_T0": "en"},
        flag_voices={"SPEAKER_T0": "am_adam"},
    )
    assert voices["SPEAKER_T0"] == "am_adam"


def test_model_has_preset_voices():
    assert model_has_preset_voices(DEFAULT_MODELS["en"])
    assert not model_has_preset_voices(DEFAULT_MODELS["ru"])


def test_default_ref_reuses_existing_wav(tmp_path: Path):
    from a_wizard.adapters.tts.default_ref import ensure_default_chatterbox_ref
    from a_wizard.application.speak import write_wav_mono

    path = tmp_path / "ref.wav"
    write_wav_mono(path, np.zeros(2400, dtype=np.float32), 24_000)
    assert ensure_default_chatterbox_ref(path) == path
    assert path.stat().st_size > 1000


def test_load_speak_yaml(tmp_path: Path):
    from a_wizard.adapters.tts.registry import load_speak_yaml

    path = tmp_path / "speak.yaml"
    path.write_text("models:\n  ru: custom-ru\nvoices:\n  SPEAKER_T0: af_heart\n")
    data = load_speak_yaml(path)
    assert data["models"]["ru"] == "custom-ru"
    assert load_speak_yaml(tmp_path / "missing.yaml") == {}
