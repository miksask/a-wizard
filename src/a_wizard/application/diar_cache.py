"""Per-track diarization turns cached by WAV digest and adapter identity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from a_wizard.adapters.persistence.store import atomic_write_text
from a_wizard.domain.freshness import DIAR_CACHE_VERSION, sha256_file
from a_wizard.domain.models import SpeakerTurn, Track


def diar_cache_paths(project_dir: Path, track_index: int) -> tuple[Path, Path]:
    base = project_dir / "meta" / "diar"
    return base / f"track_{track_index}.json", base / f"track_{track_index}.meta.json"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_cached(turns_path: Path, meta_path: Path, expected: dict[str, str]) -> list | None:
    meta = _read_json(meta_path)
    if not isinstance(meta, dict) or any(meta.get(k) != v for k, v in expected.items()):
        return None
    raw = _read_json(turns_path)
    if not isinstance(raw, list):
        return None
    try:
        return [SpeakerTurn.from_dict(item) for item in raw]
    except (KeyError, TypeError, ValueError):
        return None


def load_or_diarize(project_dir: Path, track: Track, diar: Any) -> list[SpeakerTurn]:
    """Return cached turns when WAV digest, adapter id, and cache version match."""
    wav = project_dir / track.wav
    turns_path, meta_path = diar_cache_paths(project_dir, track.index)
    cacheable = bool(getattr(diar, "cacheable", True))
    expected: dict[str, str] = {}
    if cacheable:
        expected = {
            "wav_sha256": sha256_file(wav),
            "adapter_id": str(getattr(diar, "adapter_id", "diar")),
            "algorithm_version": DIAR_CACHE_VERSION,
        }
        cached = _load_cached(turns_path, meta_path, expected)
        if cached is not None:
            return cached
    turns = list(diar.diarize(wav))
    payload = json.dumps([t.to_dict() for t in turns], ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(turns_path, payload)
    if cacheable:
        atomic_write_text(meta_path, json.dumps(expected, indent=2) + "\n")
    else:
        meta_path.unlink(missing_ok=True)
    return turns
