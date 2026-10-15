"""ASR adapters pass `auto` as no forced language (mocked Whisper packages)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from a_wizard.adapters.asr.engines import FasterWhisperAsrAdapter, MlxWhisperAsrAdapter


def _fake_mlx(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    mod = types.ModuleType("mlx_whisper")

    def transcribe(path: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"segments": []}

    mod.transcribe = transcribe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_whisper", mod)
    return captured


def _fake_faster(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    mod = types.ModuleType("faster_whisper")

    class WhisperModel:
        def __init__(self, model: str, **kwargs: Any) -> None:
            pass

        def transcribe(self, path: str, **kwargs: Any):
            captured.update(kwargs)
            return [], None

    mod.WhisperModel = WhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return captured


@pytest.mark.parametrize(("language", "expected"), [("auto", None), ("de", "de"), ("ru", "ru")])
def test_mlx_adapter_language(monkeypatch, tmp_path: Path, language: str, expected):
    captured = _fake_mlx(monkeypatch)
    MlxWhisperAsrAdapter().transcribe(tmp_path / "a.wav", language=language)
    assert captured["language"] == expected


@pytest.mark.parametrize(("language", "expected"), [("auto", None), ("de", "de"), ("ru", "ru")])
def test_faster_whisper_adapter_language(monkeypatch, tmp_path: Path, language: str, expected):
    captured = _fake_faster(monkeypatch)
    FasterWhisperAsrAdapter().transcribe(tmp_path / "a.wav", language=language)
    assert captured["language"] == expected


def test_adapters_default_to_auto(monkeypatch, tmp_path: Path):
    mlx = _fake_mlx(monkeypatch)
    MlxWhisperAsrAdapter().transcribe(tmp_path / "a.wav")
    assert mlx["language"] is None
    fw = _fake_faster(monkeypatch)
    FasterWhisperAsrAdapter().transcribe(tmp_path / "a.wav")
    assert fw["language"] is None
