"""Whisper language table and normalization."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from a_wizard.domain.errors import UsageError
from a_wizard.domain.languages import (
    DEFAULT_LANGUAGE,
    LANGUAGE_ALIASES,
    LANGUAGE_AUTO,
    LEGACY_LANGUAGE,
    WHISPER_LANGUAGES,
    normalize_language,
    stored_language,
    whisper_language,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("de", "de"),
        ("DE", "de"),
        ("  de  ", "de"),
        ("German", "de"),
        ("GERMAN", "de"),
        ("german", "de"),
        ("немецкий", "de"),
        ("Немецкий", "de"),
        ("castilian", "es"),
        ("Mandarin", "zh"),
        ("haitian creole", "ht"),
        ("haitian_creole", "ht"),
        ("ru", "ru"),
        ("English", "en"),
        ("auto", "auto"),
        ("AUTO", "auto"),
        (" Auto ", "auto"),
    ],
)
def test_normalize_language_accepts_code_name_alias(raw: str, expected: str):
    assert normalize_language(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "klingon", "xx", "deutschland-ish"])
def test_normalize_language_rejects_unsupported(raw):
    with pytest.raises(UsageError) as exc:
        normalize_language(raw)
    assert exc.value.code == "bad_language"


def test_normalize_language_suggests_close_matches():
    with pytest.raises(UsageError) as exc:
        normalize_language("germna")
    assert "german (de)" in exc.value.message
    assert exc.value.code == "bad_language"


def test_different_spellings_share_one_code():
    assert normalize_language("De") == normalize_language("German") == normalize_language("de")


def test_defaults_and_legacy():
    assert DEFAULT_LANGUAGE == LANGUAGE_AUTO
    assert LEGACY_LANGUAGE == "ru"
    assert stored_language({"language": "de"}) == "de"
    assert stored_language({"language": "auto"}) == "auto"
    assert stored_language({}) == "ru"
    assert stored_language({"language": ""}) == "ru"
    assert stored_language(None) == "ru"


def test_whisper_language_maps_auto_to_none():
    assert whisper_language("auto") is None
    assert whisper_language("AUTO") is None
    assert whisper_language(None) is None
    assert whisper_language("") is None
    assert whisper_language("de") == "de"


def test_aliases_point_at_known_codes():
    assert set(LANGUAGE_ALIASES.values()) <= set(WHISPER_LANGUAGES)


def _mlx_tokenizer_source() -> Path | None:
    # Do not import mlx_whisper: importing mlx aborts without a Metal device.
    spec = importlib.util.find_spec("mlx_whisper")
    if spec is None or not spec.submodule_search_locations:
        return None
    path = Path(next(iter(spec.submodule_search_locations))) / "tokenizer.py"
    return path if path.is_file() else None


def test_language_table_matches_mlx_whisper():
    path = _mlx_tokenizer_source()
    if path is None:
        pytest.skip("mlx_whisper not installed")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mlx_languages: dict[str, str] | None = None
    mlx_aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "LANGUAGES":
                mlx_languages = ast.literal_eval(node.value)
            if isinstance(target, ast.Name) and target.id == "TO_LANGUAGE_CODE":
                assert isinstance(node.value, ast.Dict)
                for key, value in zip(node.value.keys, node.value.values, strict=True):
                    if key is not None:  # skip the **{...} unpacking entry
                        mlx_aliases[ast.literal_eval(key)] = ast.literal_eval(value)
    assert mlx_languages is not None, "LANGUAGES not found in mlx_whisper.tokenizer"
    assert WHISPER_LANGUAGES == mlx_languages
    assert LANGUAGE_ALIASES == mlx_aliases
