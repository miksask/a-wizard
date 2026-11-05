"""Speech script domain types for TTS (no ML imports)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

SPEAK_ALGO_VERSION = "speak-v1"
DEFAULT_PAUSE_MS = 250
DEFAULT_SPEAKER_CHANGE_PAUSE_MS = 400
DEFAULT_MAX_CHUNK_CHARS = 280

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_POLISH_DIACRITICS_RE = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_PREFIX_RE = re.compile(r"^([^:\n]{1,64}):\s*(.+)$")
_MINIMIZE_HEADER_RE = re.compile(r"^(\[[^\]]+\]):\s*(.+)$")
_MINIMIZE_TS_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\]\s+")


class SpeechSource(str, Enum):
    PROJECT = "project"
    TXT = "txt"


@dataclass(frozen=True)
class SpeechLine:
    text: str
    speaker: str
    lang: str
    start_ms: int | None = None
    end_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("speech line text must be non-empty")
        if not self.speaker:
            raise ValueError("speech line speaker required")
        if not self.lang:
            raise ValueError("speech line lang required")


@dataclass
class SpeechScript:
    lines: list[SpeechLine] = field(default_factory=list)
    source: SpeechSource = SpeechSource.PROJECT

    @property
    def speakers(self) -> list[str]:
        seen: list[str] = []
        for line in self.lines:
            if line.speaker not in seen:
                seen.append(line.speaker)
        return seen


def detect_lang(text: str) -> str:
    """Heuristic language: Polish diacritics → pl, Cyrillic → ru, else en."""
    if _POLISH_DIACRITICS_RE.search(text):
        return "pl"
    if _CYRILLIC_RE.search(text):
        return "ru"
    return "en"


def chunk_text(text: str, *, max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> list[str]:
    """Split text into synthesis-sized chunks on sentence boundaries when possible."""
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences = _SENTENCE_SPLIT_RE.split(text)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if not buf:
            buf = sentence
            continue
        candidate = f"{buf} {sentence}"
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.extend(_hard_wrap(buf, max_chars))
            buf = sentence
    if buf:
        chunks.extend(_hard_wrap(buf, max_chars))
    return chunks or [text[:max_chars]]


def _hard_wrap(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    words = text.split()
    buf = ""
    for word in words:
        if not buf:
            if len(word) > max_chars:
                for i in range(0, len(word), max_chars):
                    out.append(word[i : i + max_chars])
                buf = ""
            else:
                buf = word
            continue
        candidate = f"{buf} {word}"
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            out.append(buf)
            if len(word) > max_chars:
                for i in range(0, len(word), max_chars):
                    piece = word[i : i + max_chars]
                    if i + max_chars < len(word):
                        out.append(piece)
                    else:
                        buf = piece
            else:
                buf = word
    if buf:
        out.append(buf)
    return out


def parse_txt_lines(
    text: str,
    *,
    lang: str | None = None,
    speakers_from_prefix: bool = False,
    default_speaker: str = "SPEAKER_00",
) -> list[SpeechLine]:
    """Parse a plain text file into speech lines.

    Blank lines are skipped. By default every line is one speaker. When
    ``speakers_from_prefix`` is true, lines matching ``Name: body`` become
    separate speakers.
    """
    lines: list[SpeechLine] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        speaker = default_speaker
        body = raw
        if speakers_from_prefix:
            m = _PREFIX_RE.match(raw)
            if m:
                speaker = m.group(1).strip()
                body = m.group(2).strip()
        if not body:
            continue
        resolved = lang if lang and lang != "auto" else detect_lang(body)
        lines.append(SpeechLine(text=body, speaker=speaker, lang=resolved))
    return lines


def parse_minimize_txt(
    text: str,
    *,
    lang: str | None = None,
) -> list[SpeechLine]:
    """Parse ``dialog.minimize.txt`` using glyph→speaker header mapping."""
    glyph_to_speaker: dict[str, str] = {}
    body_started = False
    lines: list[SpeechLine] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            if glyph_to_speaker:
                body_started = True
            continue
        if not body_started:
            hm = _MINIMIZE_HEADER_RE.match(stripped)
            if hm and hm.group(2).startswith("SPEAKER_"):
                glyph_to_speaker[hm.group(1)] = hm.group(2).strip()
                continue
            body_started = True
        # strip optional timestamp prefix from minimize.ts forms
        body = _MINIMIZE_TS_RE.sub("", stripped)
        m = _MINIMIZE_HEADER_RE.match(body)
        if not m:
            continue
        glyph, content = m.group(1), m.group(2).strip()
        if not content:
            continue
        speaker = glyph_to_speaker.get(glyph, glyph.strip("[]"))
        resolved = lang if lang and lang != "auto" else detect_lang(content)
        lines.append(SpeechLine(text=content, speaker=speaker, lang=resolved))
    return lines


def expand_script_chunks(
    script: SpeechScript,
    *,
    max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> SpeechScript:
    """Expand each line into sentence-sized chunks (timings kept on first chunk only)."""
    out: list[SpeechLine] = []
    for line in script.lines:
        pieces = chunk_text(line.text, max_chars=max_chars)
        for i, piece in enumerate(pieces):
            out.append(
                SpeechLine(
                    text=piece,
                    speaker=line.speaker,
                    lang=line.lang,
                    start_ms=line.start_ms if i == 0 else None,
                    end_ms=line.end_ms if i == 0 else None,
                )
            )
    return SpeechScript(lines=out, source=script.source)
