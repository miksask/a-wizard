"""Speaker attribution by channel energy + optional per-channel diarization."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a_wizard.adapters.media.energy import NumpyChannelEnergyProfiler, mean_energy
from a_wizard.domain.freshness import ENERGY_ALGORITHM_VERSION, sha256_file
from a_wizard.domain.models import (
    Segment,
    SpeakerTurn,
    Track,
    TrackMode,
    Word,
    canonical_plain_speaker,
    track_scoped_speaker,
)


@dataclass
class AttributionResult:
    segments: list[Segment]
    words: list[Word]
    report: dict[str, Any]


def _speaker_at(turns: list[SpeakerTurn], mid_ms: int) -> str | None:
    for t in turns:
        if t.start_ms <= mid_ms < t.end_ms:
            return t.speaker
    # nearest turn
    best = None
    best_dist = None
    for t in turns:
        if mid_ms < t.start_ms:
            dist = t.start_ms - mid_ms
        elif mid_ms >= t.end_ms:
            dist = mid_ms - t.end_ms
        else:
            return t.speaker
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = t.speaker
    return best


def attribute_words(
    words: list[Word],
    tracks: list[Track],
    profiles: dict[int, Any],
    channel_turns: dict[int, list[SpeakerTurn]],
    *,
    window_ms: int = 20,
    ambiguity_ratio: float = 1.15,
) -> AttributionResult:
    """Assign each word to a channel by max RMS, then to a speaker."""
    active = [t for t in tracks if t.mode in (TrackMode.PLAIN, TrackMode.DIARIZED)]
    if not active:
        return AttributionResult(segments=[], words=[], report={"ambiguous_ratio": 0.0})

    attributed: list[Word] = []
    ambiguous_count = 0
    prev_speaker: str | None = None

    for w in words:
        energies: list[tuple[Track, float]] = []
        for t in active:
            e = mean_energy(profiles.get(t.index), w.start_ms, w.end_ms, window_ms=window_ms)
            energies.append((t, e))
        energies.sort(key=lambda x: x[1], reverse=True)
        winner, top = energies[0]
        second = energies[1][1] if len(energies) > 1 else 0.0
        ambiguous = top > 0 and second > 0 and (top / max(second, 1e-12)) < ambiguity_ratio
        if top == 0 and second == 0:
            ambiguous = True

        channel = winner.index
        speaker: str | None = None

        if winner.mode == TrackMode.PLAIN:
            speaker = winner.plain_speaker or canonical_plain_speaker(winner.index)
        else:
            turns = channel_turns.get(winner.index) or []
            raw = _speaker_at(turns, (w.start_ms + w.end_ms) // 2) or "SPEAKER_00"
            speaker = track_scoped_speaker(winner.index, raw)

        if ambiguous:
            ambiguous_count += 1
            if prev_speaker is not None:
                speaker = prev_speaker
            # else keep winner channel speaker

        attributed.append(
            Word(
                w.start_ms,
                w.end_ms,
                w.text,
                speaker=speaker,
                channel=channel,
                ambiguous=ambiguous,
            )
        )
        prev_speaker = speaker

    segments = words_to_segments(attributed)
    report = {
        "word_count": len(attributed),
        "ambiguous_count": ambiguous_count,
        "ambiguous_ratio": (ambiguous_count / len(attributed)) if attributed else 0.0,
        "channels": [t.index for t in active],
    }
    return AttributionResult(segments=segments, words=attributed, report=report)


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


def assign_speakers_by_turns(
    words: list[Word],
    turns: list[SpeakerTurn],
    *,
    track_index: int,
) -> list[Word]:
    out: list[Word] = []
    for w in words:
        raw = _speaker_at(turns, (w.start_ms + w.end_ms) // 2) or "SPEAKER_00"
        out.append(
            Word(
                w.start_ms,
                w.end_ms,
                w.text,
                speaker=track_scoped_speaker(track_index, raw),
                channel=track_index,
                ambiguous=False,
            )
        )
    return out
