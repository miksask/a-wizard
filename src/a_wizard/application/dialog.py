"""Dialog merge and minimize."""

from __future__ import annotations

import re
from typing import Iterable

from a_wizard.domain.models import Segment, short_speaker_id

SPEAKER_RE = re.compile(r"^SPEAKER_T(\d+)(?:D(\d+))?$")
_LEGACY_SPEAKER_RE = re.compile(r"^(?:T\d+/)?SPEAKER_(\d+)$")


def fmt_ts(ms: int) -> str:
    if ms < 0:
        ms = 0
    sec = ms / 1000.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def segs_to_txt(segs: Iterable[Segment]) -> str:
    lines = [
        f"[{fmt_ts(s.start_ms)}–{fmt_ts(s.end_ms)}] {s.speaker}: {s.text}" for s in segs
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def merge_by_time(*lists: list[Segment]) -> list[Segment]:
    all_segs: list[Segment] = []
    for lst in lists:
        all_segs.extend(lst)
    all_segs.sort(key=lambda x: (x.start_ms, x.end_ms, x.speaker))
    return all_segs


def apply_speaker_map(segs: list[Segment], speaker_map: dict[str, str]) -> list[Segment]:
    out: list[Segment] = []
    for s in segs:
        role = speaker_map.get(s.speaker, s.speaker)
        # also try raw label if track-scoped (legacy T{n}/SPEAKER_XX)
        if role == s.speaker and "/" in s.speaker:
            raw = s.speaker.split("/", 1)[1]
            role = speaker_map.get(raw, role)
        out.append(Segment(s.start_ms, s.end_ms, s.text, role))
    return out


def default_speaker_glyph(speaker_id: str, index: int, used: set[str]) -> str:
    if SPEAKER_RE.match(speaker_id) or _LEGACY_SPEAKER_RE.match(speaker_id):
        short = short_speaker_id(speaker_id)
        candidates = [f"[{short}]", f"[{speaker_id}]"]
    else:
        cleaned = speaker_id.strip("_") or str(index)
        candidates = [f"[{cleaned}]"]
    for g in candidates:
        if g not in used:
            return g
    base = candidates[0].rstrip("]")
    n = 0
    while True:
        g = f"{base}.{n}]"
        if g not in used:
            return g
        n += 1


def minimize_segments(segs: list[Segment], glyphs: dict[str, str]) -> str:
    speakers_seen: list[str] = []
    for s in segs:
        if s.speaker not in speakers_seen:
            speakers_seen.append(s.speaker)

    prefixes: dict[str, str] = {}
    used: set[str] = set()
    for i, spk in enumerate(speakers_seen):
        if spk in glyphs and glyphs[spk] not in used:
            g = glyphs[spk]
        else:
            g = default_speaker_glyph(spk, i, used)
        prefixes[spk] = g
        used.add(g)

    lines = [f"{prefixes[spk]}: {spk}" for spk in speakers_seen]
    lines.append("")

    current: str | None = None
    buf: list[str] = []
    for s in segs:
        if s.speaker == current:
            buf.append(s.text)
        else:
            if buf and current is not None:
                lines.append(f"{prefixes[current]}: {' '.join(buf)}")
            current = s.speaker
            buf = [s.text]
    if buf and current is not None:
        lines.append(f"{prefixes[current]}: {' '.join(buf)}")
    return "\n".join(lines).rstrip() + "\n"


def safe_filename(label: str) -> str:
    return re.sub(r"[^\w\-]+", "_", label.strip("_"))
