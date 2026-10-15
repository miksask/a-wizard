"""Speaker attribution by per-track activity + optional per-channel diarization."""

from __future__ import annotations

import json
import math
import os
import tempfile
from bisect import bisect_left
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from a_wizard.adapters.media.energy import NumpyChannelEnergyProfiler, mean_energy
from a_wizard.application.activity import ActivityModel, TrackEvidence, build_activity
from a_wizard.domain.activity import DEFAULT_ACTIVITY_PARAMS, ActivityParams
from a_wizard.domain.freshness import (
    ATTRIBUTION_ALGORITHM_VERSION,
    ENERGY_ALGORITHM_VERSION,
    sha256_file,
)
from a_wizard.domain.models import (
    Segment,
    SpeakerTurn,
    Track,
    TrackMode,
    Word,
    canonical_plain_speaker,
    track_scoped_speaker,
)

CONFIDENT = "confident"
AMBIGUOUS = "ambiguous"
SILENT = "silent"

_NOISY_FLOOR_RMS = 330.0
_NO_SPEECH_RATIO = 0.002
_LEGACY_AMBIGUITY_RATIO = 1.15


@dataclass
class AttributionResult:
    segments: list[Segment]
    words: list[Word]
    report: dict[str, Any]


@dataclass
class TrackFilterResult:
    kept: dict[int, list[Word]]
    report: dict[str, Any]


class _IntervalIndex:
    """Overlap queries over intervals sorted by start (prefix max end bounds the scan)."""

    def __init__(self, intervals: Iterable[tuple[int, int, Any]]) -> None:
        self.items = sorted(intervals, key=lambda x: (x[0], x[1]))
        self.starts = [s for s, _, _ in self.items]
        self.prefix_end: list[int] = []
        self.prefix_arg: list[int] = []
        best_end, best_arg = -1, -1
        for i, (_, end, _) in enumerate(self.items):
            if end > best_end:
                best_end, best_arg = end, i
            self.prefix_end.append(best_end)
            self.prefix_arg.append(best_arg)

    def overlaps(self, start_ms: int, end_ms: int) -> list[tuple[int, Any]]:
        out: list[tuple[int, Any]] = []
        j = bisect_left(self.starts, end_ms) - 1
        while j >= 0 and self.prefix_end[j] > start_ms:
            s, e, value = self.items[j]
            overlap = min(end_ms, e) - max(start_ms, s)
            if overlap > 0:
                out.append((overlap, value))
            j -= 1
        return out

    def neighbors(self, start_ms: int, end_ms: int) -> list[Any]:
        """Closest interval ending before and starting after, nearest first (previous on ties)."""
        if not self.items:
            return []
        j = bisect_left(self.starts, start_ms)
        options: list[tuple[int, int, Any]] = []
        if j > 0:
            _, e, value = self.items[self.prefix_arg[j - 1]]
            options.append((max(0, start_ms - e), 0, value))
        if j < len(self.items):
            s, _, value = self.items[j]
            options.append((max(0, s - end_ms), 1, value))
        return [value for _, _, value in sorted(options, key=lambda x: (x[0], x[1]))]


class TurnIndex:
    """Speaker assignment against one track's diarization turns."""

    def __init__(self, turns: list[SpeakerTurn]) -> None:
        self._index = _IntervalIndex((t.start_ms, t.end_ms, t.speaker) for t in turns)

    def assign(
        self, start_ms: int, end_ms: int, majority: float
    ) -> tuple[str | None, bool, frozenset[str]]:
        """Return (speaker, strong, candidate speakers) for a word span."""
        shares: dict[str, int] = {}
        for overlap, speaker in self._index.overlaps(start_ms, end_ms):
            shares[speaker] = shares.get(speaker, 0) + overlap
        if shares:
            best = max(sorted(shares), key=lambda s: shares[s])
            strong = len(shares) == 1 or shares[best] / sum(shares.values()) >= majority
            return best, strong, frozenset(shares)
        around = self._index.neighbors(start_ms, end_ms)
        return (around[0] if around else None), False, frozenset(around)


def _span(word: Word, min_ms: int) -> tuple[int, int]:
    if word.end_ms - word.start_ms >= min_ms:
        return word.start_ms, word.end_ms
    center = (word.start_ms + word.end_ms) // 2
    half = min_ms // 2
    return max(0, center - half), center + half


def _nearest_first(
    spans: list[tuple[int, int]], anchors: list[int], k: int
) -> list[int]:
    """Anchor indices around ``k`` ordered by time gap (previous wins ties)."""
    pos = bisect_left(anchors, k)
    options: list[tuple[int, int, int]] = []
    if pos > 0:
        j = anchors[pos - 1]
        options.append((spans[k][0] - spans[j][1], 0, j))
    if pos < len(anchors) and anchors[pos] == k:
        pos += 1
    if pos < len(anchors):
        j = anchors[pos]
        options.append((spans[j][0] - spans[k][1], 1, j))
    return [j for _, _, j in sorted(options)]


def _diarized_speakers(
    spans: list[tuple[int, int]], index: TurnIndex, majority: float
) -> list[str]:
    raw: list[str | None] = []
    strong: list[bool] = []
    candidates: list[frozenset[str]] = []
    for start, end in spans:
        speaker, is_strong, cands = index.assign(start, end, majority)
        raw.append(speaker)
        strong.append(is_strong and speaker is not None)
        candidates.append(cands)
    anchors = [k for k, is_strong in enumerate(strong) if is_strong]
    for k in range(len(spans)):
        if strong[k] or not candidates[k]:
            continue
        for j in _nearest_first(spans, anchors, k):
            if raw[j] in candidates[k]:
                raw[k] = raw[j]
                break
    return [speaker or "SPEAKER_00" for speaker in raw]


def assign_speakers_by_turns(
    words: list[Word],
    turns: list[SpeakerTurn],
    *,
    track_index: int,
    params: ActivityParams = DEFAULT_ACTIVITY_PARAMS,
) -> list[Word]:
    spans = [_span(w, params.min_word_ms) for w in words]
    raw = _diarized_speakers(spans, TurnIndex(turns), params.boundary_majority)
    return [
        Word(
            w.start_ms,
            w.end_ms,
            w.text,
            speaker=track_scoped_speaker(track_index, speaker),
            channel=track_index,
        )
        for w, speaker in zip(words, raw, strict=True)
    ]


def _decide(
    evidence: list[dict[int, TrackEvidence]], order: list[int], params: ActivityParams
) -> tuple[list[str], list[int | None], list[tuple[int, ...]]]:
    states: list[str] = []
    channels: list[int | None] = []
    ties: list[tuple[int, ...]] = []
    for ev in evidence:
        active = [i for i in order if ev[i].snr_db >= params.gate_db]
        if not active:
            states.append(SILENT)
            channels.append(None)
            ties.append(())
            continue
        if len(active) > 1 and any(ev[i].snr_db >= params.strong_snr_db for i in active):
            active = [i for i in active if ev[i].snr_db >= params.strong_snr_db]
        active.sort(key=lambda i: ev[i].score, reverse=True)
        channels.append(active[0])
        if len(active) == 1:
            states.append(CONFIDENT)
            ties.append(())
            continue
        top = ev[active[0]].score
        if top >= params.dominance_ratio * max(ev[active[1]].score, 1e-12):
            states.append(CONFIDENT)
            ties.append(())
        else:
            states.append(AMBIGUOUS)
            ties.append(tuple(i for i in active if ev[i].score * params.dominance_ratio >= top))
    return states, channels, ties


def _resolve_by_context(
    spans: list[tuple[int, int]],
    states: list[str],
    channels: list[int | None],
    ties: list[tuple[int, ...]],
) -> None:
    anchors = [k for k, s in enumerate(states) if s == CONFIDENT]
    for k, state in enumerate(states):
        if state == CONFIDENT:
            continue
        neighbors = _nearest_first(spans, anchors, k)
        if state == AMBIGUOUS:
            channels[k] = next(
                (channels[j] for j in neighbors if channels[j] in ties[k]), channels[k]
            )
        elif neighbors:
            channels[k] = channels[neighbors[0]]


def _isolated_runs(words: list[Word], flagged: list[bool], gap_ms: int) -> list[int]:
    """Indices of flagged runs that are ≥ ``gap_ms`` away from every unflagged word.

    Runs split at internal pauses ≥ ``gap_ms``, so an isolated group is not kept alive
    by a flagged word that happens to sit next to real speech.
    """
    n = len(words)
    prev_end: list[float] = [-math.inf] * n
    last_end = -math.inf
    for k in range(n):
        prev_end[k] = last_end
        if not flagged[k]:
            last_end = max(last_end, words[k].end_ms)
    next_start: list[float] = [math.inf] * n
    first_start = math.inf
    for k in range(n - 1, -1, -1):
        next_start[k] = first_start
        if not flagged[k]:
            first_start = min(first_start, words[k].start_ms)
    out: list[int] = []
    k = 0
    while k < n:
        if not flagged[k]:
            k += 1
            continue
        first = k
        k += 1
        while k < n and flagged[k] and words[k].start_ms - words[k - 1].end_ms < gap_ms:
            k += 1
        last = k - 1
        if (
            words[first].start_ms - prev_end[first] >= gap_ms
            and next_start[last] - words[last].end_ms >= gap_ms
        ):
            out.extend(range(first, last + 1))
    return out


def _smooth_islands(
    words: list[Word],
    states: list[str],
    channels: list[int | None],
    evidence: list[dict[int, TrackEvidence]],
    dropped: list[bool],
    params: ActivityParams,
) -> list[int]:
    runs: list[list[int]] = []
    for k in range(len(words)):
        if dropped[k]:
            continue
        if runs and channels[runs[-1][-1]] == channels[k]:
            runs[-1].append(k)
        else:
            runs.append([k])
    changed: list[int] = []
    for r in range(1, len(runs) - 1):
        prev, cur, nxt = runs[r - 1], runs[r], runs[r + 1]
        around = channels[prev[-1]]
        own = channels[cur[0]]
        if around is None or own is None or around != channels[nxt[0]] or around == own:
            continue
        if len(cur) > params.island_max_words:
            continue
        if words[cur[-1]].end_ms - words[cur[0]].start_ms > params.island_max_ms:
            continue
        if words[cur[0]].start_ms - words[prev[-1]].end_ms > params.island_max_gap_ms:
            continue
        if words[nxt[0]].start_ms - words[cur[-1]].end_ms > params.island_max_gap_ms:
            continue
        strong = all(
            states[k] == CONFIDENT
            and evidence[k][own].score
            >= params.island_strong_ratio * max(evidence[k][around].score, 1e-9)
            for k in cur
        )
        if strong:
            continue
        for k in cur:
            channels[k] = around
            changed.append(k)
    return changed


def _legacy_channels(
    words: list[Word], active: list[Track], profiles: dict[int, Any], params: ActivityParams
) -> tuple[list[int], list[bool]]:
    """Loudest-channel rule, used only when no track shows any activity."""
    channels: list[int] = []
    ambiguous: list[bool] = []
    prev: int | None = None
    for w in words:
        energies = [
            (t.index, mean_energy(profiles.get(t.index), w.start_ms, w.end_ms,
                                  window_ms=params.window_ms))
            for t in active
        ]
        energies.sort(key=lambda x: x[1], reverse=True)
        winner, top = energies[0]
        second = energies[1][1] if len(energies) > 1 else 0.0
        is_ambiguous = (
            top > 0 and second > 0 and top / max(second, 1e-12) < _LEGACY_AMBIGUITY_RATIO
        ) or (top == 0 and second == 0)
        channel = prev if is_ambiguous and prev is not None else winner
        channels.append(channel)
        ambiguous.append(is_ambiguous)
        prev = channel
    return channels, ambiguous


def _dbfs(rms: float) -> float:
    return 20.0 * math.log10(max(rms, 1e-9) / 32768.0)


def _track_rows(
    active: list[Track],
    model: ActivityModel,
    word_counts: Counter,
    segment_counts: Counter,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for t in active:
        activity = model.tracks.get(t.index)
        floor = activity.floor_median if activity else 0.0
        rows.append(
            {
                "index": t.index,
                "mode": t.mode.value,
                "noise_floor_rms": round(floor, 1),
                "speech_level_rms": round(activity.level if activity else 0.0, 1),
                "active_ratio": round(activity.active_ratio if activity else 0.0, 4),
                "word_count": int(word_counts.get(t.index, 0)),
                "segment_count": int(segment_counts.get(t.index, 0)),
            }
        )
        if activity is None:
            continue
        if activity.active_ratio < _NO_SPEECH_RATIO and not word_counts.get(t.index):
            warnings.append(f"track {t.index}: no speech detected; consider marking it skipped")
        if floor > _NOISY_FLOOR_RMS:
            warnings.append(
                f"track {t.index}: noisy channel (noise floor {_dbfs(floor):.0f} dBFS); "
                "attribution compensates, a cleaner source improves results"
            )
    return rows, warnings


def _crosstalk_warnings(model: ActivityModel) -> list[str]:
    out: list[str] = []
    for link in model.links:
        if link.compensated:
            out.append(
                f"crosstalk: track {link.dst} contains track {link.src} delayed by "
                f"{link.lag_frames * model.params.window_ms} ms (compensated)"
            )
        else:
            out.append(
                f"crosstalk: tracks {link.src} and {link.dst} capture the same sound "
                "(same room?); not compensated"
            )
    return out


def _attribution_report(
    words_out: list[Word],
    segments: list[Segment],
    active: list[Track],
    model: ActivityModel,
    states: list[str],
    resolution: list[str],
    fallback: bool,
) -> dict[str, Any]:
    n = len(words_out)
    kept = [w for w in words_out if not w.dropped]
    speaker_channel: dict[str, int | None] = {}
    for w in kept:
        if w.speaker is not None:
            speaker_channel.setdefault(w.speaker, w.channel)
    segment_counts = Counter(speaker_channel.get(s.speaker) for s in segments)
    word_counts = Counter(w.channel for w in kept)
    rows, warnings = _track_rows(active, model, word_counts, segment_counts)
    warnings.extend(_crosstalk_warnings(model))
    if fallback:
        warnings.append("no speech activity detected on any track; used loudest-channel rule")
    ambiguous_count = sum(1 for w in words_out if w.ambiguous)
    return {
        "algorithm_version": ATTRIBUTION_ALGORITHM_VERSION,
        "word_count": n,
        "kept_word_count": len(kept),
        "ambiguous_count": ambiguous_count,
        "ambiguous_ratio": (ambiguous_count / n) if n else 0.0,
        "silent_count": sum(1 for s in states if s == SILENT),
        "context_resolved_count": sum(1 for r in resolution if r == "context"),
        "smoothed_count": sum(1 for r in resolution if r == "smoothed"),
        "dropped_count": n - len(kept),
        "fallback": fallback,
        "channels": [t.index for t in active],
        "tracks": rows,
        "crosstalk": model.links_report(),
        "warnings": warnings,
    }


def _speakers_for(
    words: list[Word],
    channels: list[int],
    dropped: list[bool],
    by_index: dict[int, Track],
    channel_turns: dict[int, list[SpeakerTurn]],
    params: ActivityParams,
) -> list[str]:
    speakers: list[str] = [""] * len(words)
    for index, track in by_index.items():
        members = [k for k, c in enumerate(channels) if c == index]
        if not members:
            continue
        if track.mode == TrackMode.PLAIN:
            label = track.plain_speaker or canonical_plain_speaker(index)
            for k in members:
                speakers[k] = label
            continue
        turns = TurnIndex(channel_turns.get(index) or [])
        for group in ([k for k in members if not dropped[k]], [k for k in members if dropped[k]]):
            spans = [_span(words[k], params.min_word_ms) for k in group]
            for k, raw in zip(group, _diarized_speakers(spans, turns, params.boundary_majority),
                              strict=True):
                speakers[k] = track_scoped_speaker(index, raw)
    return speakers


def attribute_words(
    words: list[Word],
    tracks: list[Track],
    profiles: dict[int, Any],
    channel_turns: dict[int, list[SpeakerTurn]],
    *,
    window_ms: int = 20,
    ambiguity_ratio: float | None = None,
    params: ActivityParams | None = None,
    drop_hallucinations: bool = True,
    model: ActivityModel | None = None,
) -> AttributionResult:
    """Assign each ASR word of the mix to a track, then to a speaker on that track."""
    params = params or DEFAULT_ACTIVITY_PARAMS
    if window_ms != params.window_ms:
        params = replace(params, window_ms=window_ms)
    if ambiguity_ratio is not None:
        params = replace(params, dominance_ratio=ambiguity_ratio)
    active = [t for t in tracks if t.mode in (TrackMode.PLAIN, TrackMode.DIARIZED)]
    if model is None:
        model = build_activity({t.index: profiles.get(t.index) for t in active}, params)
    if not active:
        return AttributionResult([], [], _attribution_report([], [], [], model, [], [], False))

    order = [t.index for t in active]
    by_index = {t.index: t for t in active}
    n = len(words)
    spans = [(w.start_ms, w.end_ms) for w in words]
    evidence = [model.evidence(w.start_ms, w.end_ms) for w in words]
    states, decided, ties = _decide(evidence, order, params)
    fallback = n > 0 and CONFIDENT not in states
    dropped = [False] * n
    if fallback:
        channels, ambiguous = _legacy_channels(words, active, profiles, params)
        resolution = ["fallback"] * n
    else:
        resolution = ["energy" if s == CONFIDENT else "context" for s in states]
        _resolve_by_context(spans, states, decided, ties)
        if drop_hallucinations:
            droppable = [
                max(e.snr_db for e in ev.values()) < params.hallucination_max_snr_db
                for ev in evidence
            ]
            for k in _isolated_runs(words, droppable, params.hallucination_gap_ms):
                dropped[k] = True
        for k in _smooth_islands(words, states, decided, evidence, dropped, params):
            resolution[k] = "smoothed"
        channels = [c if c is not None else order[0] for c in decided]
        ambiguous = [r != "energy" for r in resolution]

    speakers = _speakers_for(words, channels, dropped, by_index, channel_turns, params)
    words_out = [
        Word(
            w.start_ms,
            w.end_ms,
            w.text,
            speaker=speakers[k],
            channel=channels[k],
            ambiguous=ambiguous[k],
            silent=states[k] == SILENT,
            dropped=dropped[k],
        )
        for k, w in enumerate(words)
    ]
    segments = words_to_segments([w for w in words_out if not w.dropped])
    report = _attribution_report(words_out, segments, active, model, states, resolution, fallback)
    return AttributionResult(segments=segments, words=words_out, report=report)


def filter_track_words(
    track_words: dict[int, list[Word]],
    tracks: list[Track],
    profiles: dict[int, Any],
    *,
    units: dict[int, str] | None = None,
    params: ActivityParams | None = None,
    model: ActivityModel | None = None,
) -> TrackFilterResult:
    """Per-track mode: keep a track's own words only where that track carries speech."""
    params = params or DEFAULT_ACTIVITY_PARAMS
    units = units or {}
    active = [t for t in tracks if t.mode in (TrackMode.PLAIN, TrackMode.DIARIZED)]
    if model is None:
        model = build_activity({t.index: profiles.get(t.index) for t in active}, params)
    evidence = {
        index: [model.evidence(w.start_ms, w.end_ms) for w in ws]
        for index, ws in track_words.items()
    }
    informative = any(
        index in ev and ev[index].snr_db >= params.gate_db
        for index, evs in evidence.items()
        for ev in evs
    )
    indexes = {
        index: _IntervalIndex((w.start_ms, w.end_ms, None) for w in ws)
        for index, ws in track_words.items()
    }
    kept: dict[int, list[Word]] = {}
    rows: list[dict[str, Any]] = []
    for t in active:
        ws = track_words.get(t.index, [])
        evs = evidence.get(t.index, [])
        reasons: list[str | None] = [None] * len(ws)
        if informative and t.index in model.tracks:
            for k, (w, ev) in enumerate(zip(ws, evs, strict=True)):
                own = ev[t.index]
                others = [j for j in ev if j != t.index and ev[j].snr_db >= params.gate_db]
                if own.raw_snr_db >= params.gate_db and own.snr_db < params.gate_db and others:
                    reasons[k] = "crosstalk"
                elif own.snr_db >= params.gate_db and any(
                    (
                        ev[j].score >= params.island_strong_ratio * max(own.score, 1e-9)
                        or (own.snr_db < params.strong_snr_db <= ev[j].snr_db)
                    )
                    and j in indexes
                    and indexes[j].overlaps(w.start_ms, w.end_ms)
                    for j in others
                ):
                    reasons[k] = "dominated"
            droppable = [ev[t.index].raw_snr_db < params.hallucination_max_snr_db for ev in evs]
            for k in _isolated_runs(ws, droppable, params.hallucination_gap_ms):
                if reasons[k] is None:
                    reasons[k] = "hallucination"
        kept[t.index] = [w for w, reason in zip(ws, reasons, strict=True) if reason is None]
        counts = Counter(reasons)
        rows.append(
            {
                "index": t.index,
                "mode": t.mode.value,
                "unit": units.get(t.index, "words"),
                "input_count": len(ws),
                "kept_count": len(kept[t.index]),
                "dropped_hallucination": counts.get("hallucination", 0),
                "dropped_crosstalk": counts.get("crosstalk", 0),
                "dropped_dominated": counts.get("dominated", 0),
            }
        )
    warnings = _crosstalk_warnings(model)
    if not informative:
        warnings.append("no speech activity detected on any track; nothing filtered")
    report = {
        "algorithm_version": ATTRIBUTION_ALGORITHM_VERSION,
        "fallback": not informative,
        "crosstalk": model.links_report(),
        "tracks": rows,
        "warnings": warnings,
    }
    return TrackFilterResult(kept=kept, report=report)


def words_to_segments(words: list[Word], *, max_gap_ms: int = 400) -> list[Segment]:
    """Collapse consecutive same-speaker words into segments."""
    if not words:
        return []
    segs: list[Segment] = []
    cur_speaker = words[0].speaker or "SPEAKER_00"
    cur_start = words[0].start_ms
    cur_end = words[0].end_ms
    cur_texts = [words[0].text]
    for w in words[1:]:
        spk = w.speaker or "SPEAKER_00"
        gap = w.start_ms - cur_end
        if spk == cur_speaker and gap <= max_gap_ms:
            cur_end = w.end_ms
            cur_texts.append(w.text)
        else:
            text = _join_words(cur_texts)
            if text.strip():
                segs.append(Segment(cur_start, cur_end, text, cur_speaker))
            cur_speaker = spk
            cur_start = w.start_ms
            cur_end = w.end_ms
            cur_texts = [w.text]
    text = _join_words(cur_texts)
    if text.strip():
        segs.append(Segment(cur_start, cur_end, text, cur_speaker))
    return segs


def _join_words(parts: list[str]) -> str:
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and (p.startswith("'") or p in {",", ".", "!", "?", ";", ":"}):
            out[-1] = out[-1] + p
        else:
            out.append(p)
    return " ".join(out)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_energy_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("wav_sha256") or not data.get("window_ms") or not data.get("algorithm_version"):
        return None
    return data


def _cache_valid(
    meta: dict[str, Any] | None,
    *,
    wav_sha: str,
    window_ms: int,
) -> bool:
    if not meta:
        return False
    return (
        meta.get("wav_sha256") == wav_sha
        and int(meta.get("window_ms") or 0) == window_ms
        and meta.get("algorithm_version") == ENERGY_ALGORITHM_VERSION
    )


def load_or_compute_profiles(
    project_dir: Path,
    tracks: list[Track],
    *,
    window_ms: int = 20,
    profiler: NumpyChannelEnergyProfiler | None = None,
) -> dict[int, Any]:
    import numpy as np

    profiler = profiler or NumpyChannelEnergyProfiler()
    energy_dir = project_dir / "meta" / "energy"
    energy_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[int, Any] = {}
    for t in tracks:
        if t.mode not in (TrackMode.PLAIN, TrackMode.DIARIZED):
            continue
        wav = project_dir / t.wav
        cache = energy_dir / f"track_{t.index}.npy"
        meta_path = energy_dir / f"track_{t.index}.json"
        wav_sha = sha256_file(wav) if wav.is_file() else ""
        meta = _read_energy_meta(meta_path)
        if cache.is_file() and _cache_valid(meta, wav_sha=wav_sha, window_ms=window_ms):
            try:
                profiles[t.index] = np.load(cache)
                continue
            except Exception:
                pass
        profile = profiler.profile(wav, window_ms=window_ms)
        # Atomic write npy via tempfile
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".track_{t.index}.",
            suffix=".npy",
            dir=str(energy_dir),
        )
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            np.save(tmp, profile)
            os.replace(tmp, cache)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        sidecar = {
            "wav_sha256": wav_sha or sha256_file(wav),
            "window_ms": window_ms,
            "algorithm_version": ENERGY_ALGORITHM_VERSION,
        }
        _atomic_write_bytes(
            meta_path,
            (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        profiles[t.index] = profile
    return profiles
