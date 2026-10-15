"""Whisper language table and normalization (no ASR packages required).

The project language is stored as ``auto`` or a canonical Whisper language code.
Operators may type a code (``de``), an English name or alias (``German``,
``castilian``), or a Russian name (``немецкий``).
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any

from a_wizard.domain.errors import UsageError

LANGUAGE_AUTO = "auto"
# New projects: let Whisper detect the language until the operator chooses.
DEFAULT_LANGUAGE = LANGUAGE_AUTO
# A manifest with no stored language was written when `ru` was the only default.
LEGACY_LANGUAGE = "ru"

# Whisper language code -> English name. Must match mlx_whisper.tokenizer.LANGUAGES
# (checked by tests/unit/test_languages.py when mlx_whisper is installed).
WHISPER_LANGUAGES: dict[str, str] = {
    "en": "english",
    "zh": "chinese",
    "de": "german",
    "es": "spanish",
    "ru": "russian",
    "ko": "korean",
    "fr": "french",
    "ja": "japanese",
    "pt": "portuguese",
    "tr": "turkish",
    "pl": "polish",
    "ca": "catalan",
    "nl": "dutch",
    "ar": "arabic",
    "sv": "swedish",
    "it": "italian",
    "id": "indonesian",
    "hi": "hindi",
    "fi": "finnish",
    "vi": "vietnamese",
    "he": "hebrew",
    "uk": "ukrainian",
    "el": "greek",
    "ms": "malay",
    "cs": "czech",
    "ro": "romanian",
    "da": "danish",
    "hu": "hungarian",
    "ta": "tamil",
    "no": "norwegian",
    "th": "thai",
    "ur": "urdu",
    "hr": "croatian",
    "bg": "bulgarian",
    "lt": "lithuanian",
    "la": "latin",
    "mi": "maori",
    "ml": "malayalam",
    "cy": "welsh",
    "sk": "slovak",
    "te": "telugu",
    "fa": "persian",
    "lv": "latvian",
    "bn": "bengali",
    "sr": "serbian",
    "az": "azerbaijani",
    "sl": "slovenian",
    "kn": "kannada",
    "et": "estonian",
    "mk": "macedonian",
    "br": "breton",
    "eu": "basque",
    "is": "icelandic",
    "hy": "armenian",
    "ne": "nepali",
    "mn": "mongolian",
    "bs": "bosnian",
    "kk": "kazakh",
    "sq": "albanian",
    "sw": "swahili",
    "gl": "galician",
    "mr": "marathi",
    "pa": "punjabi",
    "si": "sinhala",
    "km": "khmer",
    "sn": "shona",
    "yo": "yoruba",
    "so": "somali",
    "af": "afrikaans",
    "oc": "occitan",
    "ka": "georgian",
    "be": "belarusian",
    "tg": "tajik",
    "sd": "sindhi",
    "gu": "gujarati",
    "am": "amharic",
    "yi": "yiddish",
    "lo": "lao",
    "uz": "uzbek",
    "fo": "faroese",
    "ht": "haitian creole",
    "ps": "pashto",
    "tk": "turkmen",
    "nn": "nynorsk",
    "mt": "maltese",
    "sa": "sanskrit",
    "lb": "luxembourgish",
    "my": "myanmar",
    "bo": "tibetan",
    "tl": "tagalog",
    "mg": "malagasy",
    "as": "assamese",
    "tt": "tatar",
    "haw": "hawaiian",
    "ln": "lingala",
    "ha": "hausa",
    "ba": "bashkir",
    "jw": "javanese",
    "su": "sundanese",
    "yue": "cantonese",
}

# Extra English names Whisper accepts, name -> code.
LANGUAGE_ALIASES: dict[str, str] = {
    "burmese": "my",
    "valencian": "ca",
    "flemish": "nl",
    "haitian": "ht",
    "letzeburgesch": "lb",
    "pushto": "ps",
    "panjabi": "pa",
    "moldavian": "ro",
    "moldovan": "ro",
    "sinhalese": "si",
    "castilian": "es",
    "mandarin": "zh",
}

# Russian names accepted as typed input only, name -> code.
RUSSIAN_LANGUAGE_NAMES: dict[str, str] = {
    "английский": "en",
    "русский": "ru",
    "немецкий": "de",
    "французский": "fr",
    "испанский": "es",
    "итальянский": "it",
    "португальский": "pt",
    "польский": "pl",
    "украинский": "uk",
    "белорусский": "be",
    "чешский": "cs",
    "словацкий": "sk",
    "болгарский": "bg",
    "сербский": "sr",
    "хорватский": "hr",
    "румынский": "ro",
    "венгерский": "hu",
    "греческий": "el",
    "турецкий": "tr",
    "арабский": "ar",
    "иврит": "he",
    "персидский": "fa",
    "хинди": "hi",
    "китайский": "zh",
    "японский": "ja",
    "корейский": "ko",
    "вьетнамский": "vi",
    "тайский": "th",
    "индонезийский": "id",
    "нидерландский": "nl",
    "голландский": "nl",
    "шведский": "sv",
    "норвежский": "no",
    "датский": "da",
    "финский": "fi",
    "эстонский": "et",
    "латышский": "lv",
    "литовский": "lt",
    "грузинский": "ka",
    "армянский": "hy",
    "азербайджанский": "az",
    "казахский": "kk",
    "узбекский": "uz",
    "татарский": "tt",
    "латынь": "la",
    "латинский": "la",
    "идиш": "yi",
}


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    lookup.update({name: code for code, name in WHISPER_LANGUAGES.items()})
    lookup.update(LANGUAGE_ALIASES)
    lookup.update(RUSSIAN_LANGUAGE_NAMES)
    lookup.update({code: code for code in WHISPER_LANGUAGES})
    return lookup


_LOOKUP = _build_lookup()


def _canonical_key(raw: str) -> str:
    return " ".join(raw.strip().lower().replace("_", " ").split())


def _bad_language(raw: str) -> UsageError:
    key = _canonical_key(raw)
    hint = ""
    if key:
        seen: list[str] = []
        for match in difflib.get_close_matches(key, list(_LOOKUP), n=5, cutoff=0.6):
            code = _LOOKUP[match]
            if code not in seen:
                seen.append(code)
        if seen:
            options = ", ".join(f"{WHISPER_LANGUAGES[c]} ({c})" for c in seen[:3])
            hint = f"; did you mean: {options}?"
    return UsageError(
        f"unsupported language {raw!r}{hint}",
        code="bad_language",
        next_step="use a Whisper language code or name (e.g. de, German), or auto",
    )


def normalize_language(raw: str | None) -> str:
    """Return ``auto`` or a canonical Whisper language code.

    Accepts a code, an English name or alias, or a Russian name; case-insensitive,
    whitespace-trimmed. Raises ``UsageError(code="bad_language")`` otherwise.
    """
    key = _canonical_key(raw or "")
    if key == LANGUAGE_AUTO:
        return LANGUAGE_AUTO
    code = _LOOKUP.get(key)
    if code is None:
        raise _bad_language(raw or "")
    return code


def stored_language(defaults: Mapping[str, Any] | None) -> str:
    """Language stored in transcription defaults (legacy manifests read as ``ru``)."""
    value = (defaults or {}).get("language")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return LEGACY_LANGUAGE


def whisper_language(language: str | None) -> str | None:
    """Language argument for a Whisper adapter: ``None`` requests auto-detection."""
    if language is None:
        return None
    value = language.strip().lower()
    if not value or value == LANGUAGE_AUTO:
        return None
    return value
