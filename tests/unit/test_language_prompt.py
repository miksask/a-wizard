"""Interactive project language question (auto / ru / en / other)."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from a_wizard.cli.app import _prompt_language


def _feed(monkeypatch: pytest.MonkeyPatch, answers: Iterable[str]) -> None:
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(it))


def test_options_order_and_auto_default(monkeypatch, capsys):
    _feed(monkeypatch, [""])
    assert _prompt_language("auto") == "auto"
    err = capsys.readouterr().err
    assert err.index("[1] auto (default)") < err.index("[2] ru") < err.index("[3] en")
    assert err.index("[3] en") < err.index("[4] other")


@pytest.mark.parametrize(("answer", "expected"), [("1", "auto"), ("2", "ru"), ("3", "en")])
def test_select_listed_language(monkeypatch, answer, expected):
    _feed(monkeypatch, [answer])
    assert _prompt_language("auto") == expected


def test_default_follows_stored_ru_and_en(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt_language("ru") == "ru"
    _feed(monkeypatch, [""])
    assert _prompt_language("en") == "en"


def test_other_normalizes_name(monkeypatch):
    _feed(monkeypatch, ["4", "German"])
    assert _prompt_language("auto") == "de"


def test_other_reasks_on_unsupported(monkeypatch, capsys):
    _feed(monkeypatch, ["4", "klingon", "", "немецкий"])
    assert _prompt_language("auto") == "de"
    err = capsys.readouterr().err
    assert "unsupported language" in err
    assert "required" in err


def test_stored_other_is_default_and_enter_keeps_it(monkeypatch, capsys):
    _feed(monkeypatch, ["", ""])  # Enter at the menu, then Enter at the language prompt
    assert _prompt_language("de") == "de"
    assert "[4] other (current: de) (default)" in capsys.readouterr().err


def test_stored_other_can_be_replaced(monkeypatch):
    _feed(monkeypatch, ["4", "pl"])
    assert _prompt_language("de") == "pl"
    _feed(monkeypatch, ["1"])
    assert _prompt_language("de") == "auto"


def test_none_current_defaults_to_auto(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt_language(None) == "auto"
