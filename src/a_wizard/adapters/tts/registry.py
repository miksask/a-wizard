"""TTS model registry: per-language defaults and override order."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from a_wizard.adapters.tts.fake import FakeTtsAdapter
from a_wizard.domain.errors import UsageError

DEFAULT_MODELS: dict[str, str] = {
    "en": "mlx-community/Kokoro-82M-bf16",
    "ru": "mlx-community/chatterbox-multilingual-v3",
    "pl": "mlx-community/chatterbox-multilingual-v3",
}

# Stable Kokoro preset rotation for multi-speaker English.
KOKORO_VOICES: list[str] = [
    "af_heart",
    "am_michael",
    "bf_emma",
    "bm_george",
    "af_bella",
    "am_adam",
    "bf_isabella",
    "bm_lewis",
]

_ENV_MODEL_RE = re.compile(r"^A_WIZARD_TTS_MODEL_([A-Z]{2,8})$")


def env_model_overrides() -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        m = _ENV_MODEL_RE.match(key)
        if m and value.strip():
            out[m.group(1).lower()] = value.strip()
    return out


def resolve_model_id(
    lang: str,
    *,
    yaml_models: dict[str, str] | None = None,
    flag_models: dict[str, str] | None = None,
) -> str:
    """Resolve model id: default < env < speak.yaml < --model flag."""
    code = (lang or "en").strip().lower()
    model = DEFAULT_MODELS.get(code) or DEFAULT_MODELS["en"]
    env = env_model_overrides()
    if code in env:
        model = env[code]
    if yaml_models and code in yaml_models and yaml_models[code].strip():
        model = yaml_models[code].strip()
    if flag_models and code in flag_models and flag_models[code].strip():
        model = flag_models[code].strip()
    return model


def model_kind(model_id: str) -> str:
    low = model_id.lower()
    if "kokoro" in low:
        return "kokoro"
    if "chatterbox" in low:
        return "chatterbox"
    if "qwen3-tts" in low or "qwen3_tts" in low:
        return "qwen3"
    return "generic"


def model_has_preset_voices(model_id: str) -> bool:
    kind = model_kind(model_id)
    return kind in ("kokoro", "qwen3")


def assign_voices(
    speakers: list[str],
    *,
    models_by_lang: dict[str, str],
    speaker_langs: dict[str, str],
    yaml_voices: dict[str, str] | None = None,
    flag_voices: dict[str, str] | None = None,
) -> tuple[dict[str, str | None], list[str]]:
    """Assign voice presets per speaker. Returns (voices, warnings)."""
    voices: dict[str, str | None] = {}
    warnings: list[str] = []
    preset_index = 0
    yaml_voices = yaml_voices or {}
    flag_voices = flag_voices or {}
    warned_models: set[str] = set()

    for spk in speakers:
        lang = speaker_langs.get(spk, "en")
        model = models_by_lang.get(lang) or resolve_model_id(lang)
        if spk in flag_voices and flag_voices[spk].strip():
            voices[spk] = flag_voices[spk].strip()
            continue
        if spk in yaml_voices and yaml_voices[spk].strip():
            voices[spk] = yaml_voices[spk].strip()
            continue
        if model_has_preset_voices(model):
            pool = KOKORO_VOICES if model_kind(model) == "kokoro" else KOKORO_VOICES
            voices[spk] = pool[preset_index % len(pool)]
            preset_index += 1
        else:
            voices[spk] = None
            if model not in warned_models:
                warnings.append("chatterbox_no_presets")
                warned_models.add(model)
    return voices, warnings


def parse_kv_flags(values: list[str] | None, *, what: str) -> dict[str, str]:
    """Parse repeated KEY=VALUE CLI flags."""
    out: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise UsageError(
                f"invalid {what} {raw!r}; expected KEY=VALUE",
                code="speak_config",
                next_step=f"use e.g. --{what} en=mlx-community/Kokoro-82M-bf16",
            )
        key, value = raw.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise UsageError(
                f"invalid {what} {raw!r}; expected KEY=VALUE",
                code="speak_config",
            )
        out[key] = value
    return out


def load_speak_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise UsageError("speak.yaml must be a mapping", code="speak_config")
    return data


def resolve_tts_adapter(
    model_id: str,
    *,
    mock: bool = False,
) -> Any:
    if mock or model_id in ("mock", "fake", "fake-tts"):
        return FakeTtsAdapter(model_id=model_id)
    from a_wizard.adapters.tts.mlx_audio import MlxAudioTtsAdapter

    return MlxAudioTtsAdapter(model_id=model_id)
