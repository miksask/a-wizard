"""mlx-audio TTS adapter (lazy import; Apple Silicon)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from a_wizard.adapters.tts.registry import model_has_preset_voices, model_kind
from a_wizard.domain.errors import UsageError

_MODEL_CACHE: dict[str, Any] = {}


def _to_numpy(audio: Any) -> np.ndarray:
    if isinstance(audio, np.ndarray):
        arr = audio.astype(np.float32, copy=False)
    else:
        # mlx array
        try:
            import mlx.core as mx

            arr = np.array(mx.array(audio), dtype=np.float32)
        except Exception:
            arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr


class MlxAudioTtsAdapter:
    """Wraps mlx-audio load_model + generate for Kokoro / Chatterbox / generic."""

    def __init__(self, *, model_id: str) -> None:
        self.model_id = model_id
        self.adapter_id = f"mlx-audio:{model_id}"
        self._model: Any | None = None
        self._sample_rate = 24_000
        self.has_preset_voices = model_has_preset_voices(model_id)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model
        if self.model_id in _MODEL_CACHE:
            self._model = _MODEL_CACHE[self.model_id]
            return self._model
        try:
            from mlx_audio.tts.utils import load_model
        except ImportError as e:
            raise UsageError(
                "mlx-audio is not installed",
                code="tts_missing",
                next_step="uv sync --extra tts",
            ) from e
        model = load_model(self.model_id)
        sr = getattr(model, "sample_rate", None) or getattr(model, "sampling_rate", None)
        if isinstance(sr, int) and sr > 0:
            self._sample_rate = sr
        _MODEL_CACHE[self.model_id] = model
        self._model = model
        return model

    def voices(self) -> list[str]:
        model = self._ensure_loaded()
        for attr in ("voices", "get_supported_speakers", "available_voices"):
            fn = getattr(model, attr, None)
            if callable(fn):
                try:
                    result = fn()
                    if isinstance(result, (list, tuple)):
                        return [str(x) for x in result]
                except Exception:
                    pass
            elif isinstance(fn, (list, tuple)):
                return [str(x) for x in fn]
        from a_wizard.adapters.tts.registry import KOKORO_VOICES

        if model_kind(self.model_id) == "kokoro":
            return list(KOKORO_VOICES)
        return []

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
        model = self._ensure_loaded()
        kind = model_kind(self.model_id)
        kwargs: dict[str, Any] = {"text": text, "speed": float(speed)}

        if kind == "kokoro":
            # Kokoro uses single-letter lang codes historically; pass ISO when supported.
            kwargs["lang_code"] = _kokoro_lang_code(lang)
            if voice:
                kwargs["voice"] = voice
        elif kind == "chatterbox":
            kwargs["lang_code"] = lang
            if ref_audio is not None:
                kwargs["ref_audio"] = str(ref_audio)
            if ref_text:
                kwargs["ref_text"] = ref_text
        elif kind == "qwen3":
            if voice:
                kwargs["speaker"] = voice
                kwargs["language"] = _qwen_language_name(lang)
            if ref_audio is not None:
                kwargs["ref_audio"] = str(ref_audio)
            if ref_text:
                kwargs["ref_text"] = ref_text
        else:
            if voice:
                kwargs["voice"] = voice
            kwargs["lang_code"] = lang
            if ref_audio is not None:
                kwargs["ref_audio"] = str(ref_audio)
            if ref_text:
                kwargs["ref_text"] = ref_text

        chunks: list[np.ndarray] = []
        generate = getattr(model, "generate", None)
        generate_custom = getattr(model, "generate_custom_voice", None)

        try:
            if kind == "qwen3" and voice and callable(generate_custom):
                iterator = generate_custom(
                    text,
                    speaker=voice,
                    language=_qwen_language_name(lang),
                )
            elif callable(generate):
                iterator = generate(**kwargs)
            else:
                raise UsageError(
                    f"TTS model {self.model_id} has no generate() method",
                    code="tts_missing",
                )
            for result in iterator:
                audio = getattr(result, "audio", result)
                chunks.append(_to_numpy(audio))
        except UsageError:
            raise
        except TypeError:
            # Retry with a smaller kwargs set for API drift.
            fallback = {"text": text}
            if voice and kind == "kokoro":
                fallback["voice"] = voice
            if ref_audio is not None:
                fallback["ref_audio"] = str(ref_audio)
            for result in model.generate(**fallback):
                audio = getattr(result, "audio", result)
                chunks.append(_to_numpy(audio))
        except Exception as e:
            missing_frontend = "misaki" in str(e).lower()
            raise UsageError(
                f"TTS synthesis failed for model {self.model_id}: {e}",
                code="tts_missing" if missing_frontend else "tts_failed",
                next_step="uv sync --extra tts",
            ) from e

        if not chunks:
            return np.zeros(0, dtype=np.float32)
        if len(chunks) == 1:
            return chunks[0]
        return np.concatenate(chunks).astype(np.float32, copy=False)


def _kokoro_lang_code(lang: str) -> str:
    # Kokoro classic codes: a=American EN, b=British, etc. Prefer ISO if recent mlx-audio.
    mapping = {
        "en": "a",
        "ja": "j",
        "zh": "z",
        "fr": "f",
        "es": "e",
        "it": "i",
        "pt": "p",
        "hi": "h",
    }
    return mapping.get(lang, lang)


def _qwen_language_name(lang: str) -> str:
    names = {
        "en": "English",
        "ru": "Russian",
        "pl": "Polish",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "de": "German",
        "fr": "French",
        "es": "Spanish",
    }
    return names.get(lang, lang)
