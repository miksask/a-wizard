"""Unit tests for domain speech helpers."""

from __future__ import annotations

from a_wizard.domain.speech import (
    SpeechLine,
    SpeechScript,
    SpeechSource,
    chunk_text,
    detect_lang,
    expand_script_chunks,
    parse_minimize_txt,
    parse_txt_lines,
)


def test_detect_lang_cyrillic():
    assert detect_lang("Привет, как дела?") == "ru"


def test_detect_lang_polish():
    assert detect_lang("Cześć, jak się masz?") == "pl"


def test_detect_lang_english():
    assert detect_lang("Hello there") == "en"


def test_chunk_text_short():
    assert chunk_text("Hello.") == ["Hello."]


def test_chunk_text_sentences():
    text = "One. " + ("word " * 40) + "Two. Three."
    chunks = chunk_text(text, max_chars=80)
    assert len(chunks) >= 2
    assert all(len(c) <= 80 or " " not in c for c in chunks)


def test_parse_txt_plain():
    lines = parse_txt_lines("hello\n\nworld\n", lang="en")
    assert len(lines) == 2
    assert lines[0].speaker == "SPEAKER_00"
    assert lines[0].text == "hello"


def test_parse_txt_prefixes_off_by_default():
    lines = parse_txt_lines("Alice: hi\nBob: bye\n")
    assert [x.speaker for x in lines] == ["SPEAKER_00", "SPEAKER_00"]
    assert lines[0].text == "Alice: hi"


def test_parse_txt_prefixes():
    lines = parse_txt_lines("Alice: hi\nBob: bye\n", speakers_from_prefix=True)
    assert [x.speaker for x in lines] == ["Alice", "Bob"]
    assert lines[0].text == "hi"


def test_parse_minimize_txt():
    text = (
        "[ST0]: SPEAKER_T0\n"
        "[ST1]: SPEAKER_T1\n"
        "\n"
        "[ST0]: hello there\n"
        "[ST1]: hi back\n"
    )
    lines = parse_minimize_txt(text, lang="en")
    assert len(lines) == 2
    assert lines[0].speaker == "SPEAKER_T0"
    assert lines[1].speaker == "SPEAKER_T1"
    assert lines[0].text == "hello there"


def test_expand_script_chunks_keeps_timing_on_first():
    script = SpeechScript(
        lines=[
            SpeechLine(
                text="First sentence. Second sentence that is also here.",
                speaker="SPEAKER_T0",
                lang="en",
                start_ms=1000,
                end_ms=5000,
            )
        ],
        source=SpeechSource.PROJECT,
    )
    expanded = expand_script_chunks(script, max_chars=20)
    assert len(expanded.lines) >= 2
    assert expanded.lines[0].start_ms == 1000
    assert expanded.lines[1].start_ms is None
