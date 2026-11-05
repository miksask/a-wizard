"""Speak: synthesize speech from dialog.json or a text file."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from a_wizard.adapters.persistence.store import atomic_write_bytes, atomic_write_text
from a_wizard.adapters.tts.registry import (
    assign_voices,
    load_speak_yaml,
    model_kind,
    resolve_model_id,
    resolve_tts_adapter,
)
from a_wizard.domain.errors import UsageError
from a_wizard.domain.freshness import sha256_bytes, sha256_file
from a_wizard.domain.languages import stored_language
from a_wizard.domain.models import Project, Segment, StageStatus
from a_wizard.domain.speech import (
    DEFAULT_PAUSE_MS,
    DEFAULT_SPEAKER_CHANGE_PAUSE_MS,
    SPEAK_ALGO_VERSION,
    SpeechLine,
    SpeechScript,
    SpeechSource,
    detect_lang,
    expand_script_chunks,
    parse_minimize_txt,
    parse_txt_lines,
)

_PLAIN_SPK_RE = re.compile(r"^SPEAKER_T(\d+)$")
_DIAR_SPK_RE = re.compile(r"^SPEAKER_T(\d+)D(\d+)$")

SPEECH_WAV_REL = "dialog/speech.wav"
SPEECH_JSON_REL = "dialog/speech.json"
SPEECH_CACHE_REL = "dialog/speech/cache"
SPEECH_REFS_REL = "dialog/speech/refs"
SPEAK_YAML_NAME = "speak.yaml"

_REF_MIN_MS = 6_000
_REF_MAX_MS = 12_000
_FIT_MAX_SPEED = 1.5


@dataclass
class SpeakOptions:
    timeline: bool = False
    fit: bool = False
    pause_ms: int = DEFAULT_PAUSE_MS
    speaker_change_pause_ms: int = DEFAULT_SPEAKER_CHANGE_PAUSE_MS
    language: str | None = None  # auto / code / None → project or detect
    models: dict[str, str] = field(default_factory=dict)
    voices: dict[str, str] = field(default_factory=dict)
    clone_all: bool = False
    clone_speakers: set[str] = field(default_factory=set)
    refs: dict[str, Path] = field(default_factory=dict)
    speed: float = 1.0
    format: str = "wav"
    output: Path | None = None
    force: bool = False
    mock: bool = False
    speakers_from_prefix: bool = False


@dataclass
class SpeakResult:
    output: Path
    speech_json: Path | None
    skipped: bool
    cache_hits: int
    cache_misses: int
    overruns: int
    warnings: list[str]
    line_count: int
    sample_rate: int


def load_script_from_dialog(
    project_dir: Path,
    project: Project,
    *,
    language: str | None = None,
) -> SpeechScript:
    path = project_dir / "dialog" / "dialog.json"
    if not path.is_file():
        raise UsageError(
            "dialog/dialog.json not found",
            code="merge_required",
            next_step="run a-wizard run until merge succeeds",
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise UsageError("dialog.json must be a list of segments", code="speak_config")
    segs = [Segment.from_dict(x) for x in raw]
    project_lang = language or stored_language(project.transcription_defaults)
    lines: list[SpeechLine] = []
    for s in segs:
        if project_lang and project_lang != "auto":
            lang = project_lang
        else:
            lang = detect_lang(s.text)
        lines.append(
            SpeechLine(
                text=s.text,
                speaker=s.speaker,
                lang=lang,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
            )
        )
    return SpeechScript(lines=lines, source=SpeechSource.PROJECT)


def load_script_from_txt(
    path: Path,
    *,
    language: str | None = None,
    speakers_from_prefix: bool = False,
) -> SpeechScript:
    text = path.read_text(encoding="utf-8")
    # Prefer minimize-style if header looks like glyph map
    if re.search(r"^\[.+\]:\s*SPEAKER_", text, re.MULTILINE):
        lines = parse_minimize_txt(text, lang=language)
    else:
        lines = parse_txt_lines(
            text,
            lang=language,
            speakers_from_prefix=speakers_from_prefix,
        )
    if not lines:
        raise UsageError("no speakable lines in text file", code="speak_config")
    return SpeechScript(lines=lines, source=SpeechSource.TXT)


def _speaker_track_index(speaker: str) -> int | None:
    m = _PLAIN_SPK_RE.match(speaker)
    if m:
        return int(m.group(1))
    m = _DIAR_SPK_RE.match(speaker)
    if m:
        return int(m.group(1))
    return None


def _read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sw != 2:
        raise UsageError(f"expected 16-bit PCM wav: {path}", code="wav_format")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        audio = audio.reshape(-1, nch).mean(axis=1)
    return audio, rate


def write_wav_mono(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    import io

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    atomic_write_bytes(path, bio.getvalue())


def extract_clone_ref(
    project_dir: Path,
    project: Project,
    speaker: str,
    segments: list[Segment],
    *,
    out_path: Path,
) -> tuple[Path, str]:
    """Cut 6–12 s of speaker audio from their track; return (path, ref_text)."""
    track_idx = _speaker_track_index(speaker)
    if track_idx is None:
        raise UsageError(
            f"cannot resolve track for speaker {speaker}",
            code="clone_requires_ref",
            next_step="pass --ref SPEAKER=path.wav",
        )
    track = next((t for t in project.tracks if t.index == track_idx), None)
    if track is None:
        raise UsageError(
            f"track {track_idx} missing for speaker {speaker}",
            code="clone_requires_ref",
        )
    wav_path = project_dir / track.wav
    if not wav_path.is_file():
        raise UsageError(
            f"track wav missing: {track.wav}",
            code="clone_requires_ref",
            next_step="run extract first",
        )
    spk_segs = [s for s in segments if s.speaker == speaker]
    spk_segs.sort(key=lambda s: (s.end_ms - s.start_ms), reverse=True)
    audio, rate = _read_wav_mono(wav_path)
    pieces: list[np.ndarray] = []
    texts: list[str] = []
    total_ms = 0
    for s in spk_segs:
        if total_ms >= _REF_MAX_MS:
            break
        start = max(0, int(s.start_ms * rate / 1000))
        end = min(len(audio), int(s.end_ms * rate / 1000))
        if end <= start:
            continue
        pieces.append(audio[start:end])
        texts.append(s.text)
        total_ms += s.end_ms - s.start_ms
        if total_ms >= _REF_MIN_MS and total_ms >= _REF_MAX_MS:
            break
    if not pieces:
        raise UsageError(
            f"no audio segments for speaker {speaker}",
            code="clone_requires_ref",
        )
    ref_audio = np.concatenate(pieces)
    max_samples = int(_REF_MAX_MS * rate / 1000)
    if len(ref_audio) > max_samples:
        ref_audio = ref_audio[:max_samples]
    write_wav_mono(out_path, ref_audio, rate)
    return out_path, " ".join(texts)


def cache_key(
    *,
    text: str,
    lang: str,
    model_id: str,
    voice: str | None,
    ref_digest: str | None,
    speed: float,
) -> str:
    payload = "|".join(
        [
            SPEAK_ALGO_VERSION,
            text,
            lang,
            model_id,
            voice or "",
            ref_digest or "",
            f"{float(speed):.4f}",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_sequential(
    clips: list[np.ndarray],
    speakers: list[str],
    *,
    sample_rate: int,
    pause_ms: int,
    speaker_change_pause_ms: int,
) -> np.ndarray:
    if not clips:
        return np.zeros(0, dtype=np.float32)
    pause = np.zeros(int(sample_rate * pause_ms / 1000), dtype=np.float32)
    change = np.zeros(int(sample_rate * speaker_change_pause_ms / 1000), dtype=np.float32)
    parts: list[np.ndarray] = []
    prev_spk: str | None = None
    for clip, spk in zip(clips, speakers, strict=True):
        if parts:
            parts.append(change if prev_spk is not None and spk != prev_spk else pause)
        parts.append(clip.astype(np.float32, copy=False))
        prev_spk = spk
    return np.concatenate(parts).astype(np.float32, copy=False)


def render_timeline(
    clips: list[np.ndarray],
    starts_ms: list[int | None],
    ends_ms: list[int | None],
    *,
    sample_rate: int,
    fit: bool,
) -> tuple[np.ndarray, int]:
    """Place clips at start_ms; return (audio, overrun_count)."""
    if not clips:
        return np.zeros(0, dtype=np.float32), 0
    processed: list[np.ndarray] = []
    overruns = 0
    for i, clip in enumerate(clips):
        start = starts_ms[i] if starts_ms[i] is not None else 0
        # next start defines the slot
        next_starts = [s for s in starts_ms[i + 1 :] if s is not None]
        slot_end = next_starts[0] if next_starts else None
        if ends_ms[i] is not None and (slot_end is None or ends_ms[i] < slot_end):
            # prefer segment end as soft bound when tighter
            pass
        audio = clip.astype(np.float32, copy=False)
        if slot_end is not None and start is not None:
            budget_ms = max(1, slot_end - int(start))
            budget_samples = int(sample_rate * budget_ms / 1000)
            if len(audio) > budget_samples:
                overruns += 1
                if fit:
                    ratio = len(audio) / budget_samples
                    speed = min(_FIT_MAX_SPEED, max(1.0, ratio))
                    audio = _atempo(audio, sample_rate, speed)
                    if len(audio) > budget_samples:
                        audio = audio[:budget_samples]
        processed.append(audio)

    # total length
    total = 0
    placements: list[tuple[int, np.ndarray]] = []
    cursor = 0
    for i, audio in enumerate(processed):
        start = starts_ms[i]
        if start is None:
            offset = cursor
        else:
            offset = int(sample_rate * int(start) / 1000)
        placements.append((offset, audio))
        cursor = max(cursor, offset + len(audio))
        total = max(total, offset + len(audio))
    buf = np.zeros(total, dtype=np.float32)
    for offset, audio in placements:
        end = offset + len(audio)
        if end > len(buf):
            buf = np.pad(buf, (0, end - len(buf)))
        # mix with soft clip
        mixed = buf[offset:end] + audio
        buf[offset:end] = np.clip(mixed, -1.0, 1.0)
    return buf, overruns


def _atempo(audio: np.ndarray, sample_rate: int, speed: float) -> np.ndarray:
    """Speed up via ffmpeg atempo (≤ 1.5 per call; chain if needed)."""
    import tempfile

    speed = float(speed)
    if speed <= 1.001:
        return audio
    with tempfile.TemporaryDirectory(prefix="a-wizard-atempo-") as tmp:
        tmp_path = Path(tmp)
        inp = tmp_path / "in.wav"
        outp = tmp_path / "out.wav"
        write_wav_mono(inp, audio, sample_rate)
        # chain atempo filters for speeds > 2.0 (we cap at 1.5)
        factors: list[float] = []
        remaining = speed
        while remaining > 1.001:
            step = min(_FIT_MAX_SPEED, remaining)
            factors.append(step)
            remaining /= step
        filt = ",".join(f"atempo={f:.4f}" for f in factors)
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(inp),
            "-filter:a",
            filt,
            str(outp),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            # fallback: naive resample truncate
            new_len = max(1, int(len(audio) / speed))
            idx = np.linspace(0, len(audio) - 1, new_len)
            return np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
        out_audio, _ = _read_wav_mono(outp)
        return out_audio


def convert_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(mp3_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError as e:
        raise UsageError(
            "ffmpeg required for mp3 output",
            code="ffmpeg_missing",
            next_step="install ffmpeg",
        ) from e
    except subprocess.CalledProcessError as e:
        raise UsageError(
            f"ffmpeg mp3 conversion failed: {e}",
            code="ffmpeg_failed",
        ) from e


def speech_signature(
    *,
    dialog_digest: str,
    models: dict[str, str],
    voices: dict[str, str | None],
    refs: dict[str, str],
    layout: str,
    pause_ms: int,
    speed: float,
    fit: bool,
    fmt: str,
) -> str:
    payload = {
        "algo": SPEAK_ALGO_VERSION,
        "dialog": dialog_digest,
        "models": models,
        "voices": voices,
        "refs": refs,
        "layout": layout,
        "pause_ms": pause_ms,
        "speed": speed,
        "fit": fit,
        "format": fmt,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return sha256_bytes(blob)


def _engine_for_model(
    model_id: str,
    *,
    mock: bool,
    cache: dict[str, Any],
) -> Any:
    if model_id not in cache:
        cache[model_id] = resolve_tts_adapter(model_id, mock=mock)
    return cache[model_id]


def run_speak(
    *,
    script: SpeechScript,
    options: SpeakOptions,
    project_dir: Path | None = None,
    project: Project | None = None,
    output_wav: Path,
    speech_json_path: Path | None = None,
    cache_dir: Path | None = None,
    refs_dir: Path | None = None,
    yaml_path: Path | None = None,
    source_digest: str,
    log: Callable[..., None] | None = None,
) -> SpeakResult:
    """Synthesize script to output_wav. Never logs transcript text."""

    def _log(msg: str) -> None:
        if log:
            log(msg)

    if project is not None and project_dir is not None:
        if project.stage("merge").status != StageStatus.SUCCEEDED:
            raise UsageError(
                "Merge not done",
                code="merge_required",
                next_step="run a-wizard run until merge succeeds",
            )

    yaml_data = load_speak_yaml(yaml_path) if yaml_path else {}
    yaml_models = {
        str(k): str(v) for k, v in (yaml_data.get("models") or {}).items() if v
    }
    yaml_voices = {
        str(k): str(v) for k, v in (yaml_data.get("voices") or {}).items() if v
    }

    script = expand_script_chunks(script)
    if not script.lines:
        raise UsageError("no speakable lines", code="speak_config")

    # Resolve models per language used
    langs = sorted({line.lang for line in script.lines})
    models_by_lang: dict[str, str] = {}
    for lang in langs:
        models_by_lang[lang] = resolve_model_id(
            lang,
            yaml_models=yaml_models,
            flag_models=options.models,
        )

    speaker_langs: dict[str, str] = {}
    for line in script.lines:
        speaker_langs.setdefault(line.speaker, line.lang)

    voices, warnings = assign_voices(
        script.speakers,
        models_by_lang=models_by_lang,
        speaker_langs=speaker_langs,
        yaml_voices=yaml_voices,
        flag_voices=options.voices,
    )

    # Clone refs
    ref_paths: dict[str, Path] = dict(options.refs)
    ref_texts: dict[str, str] = {}
    ref_digests: dict[str, str] = {}

    need_clone: set[str] = set()
    if options.clone_all:
        need_clone = set(script.speakers)
    need_clone |= set(options.clone_speakers)

    if need_clone and script.source == SpeechSource.TXT:
        missing = [s for s in need_clone if s not in ref_paths]
        if missing:
            raise UsageError(
                "voice cloning in txt mode requires --ref SPEAKER=path.wav",
                code="clone_requires_ref",
            )

    segments_for_clone: list[Segment] = []
    if project_dir and project and need_clone:
        dialog_path = project_dir / "dialog" / "dialog.json"
        if dialog_path.is_file():
            raw = json.loads(dialog_path.read_text(encoding="utf-8"))
            segments_for_clone = [Segment.from_dict(x) for x in raw]

    if refs_dir is None and project_dir is not None:
        refs_dir = project_dir / SPEECH_REFS_REL

    for spk in sorted(need_clone):
        if spk in ref_paths:
            continue
        if project is None or project_dir is None or refs_dir is None:
            raise UsageError(
                f"cannot clone speaker {spk} without a project",
                code="clone_requires_ref",
            )
        safe = re.sub(r"[^\w\-]+", "_", spk)
        out_ref = refs_dir / f"{safe}.wav"
        path, ref_text = extract_clone_ref(
            project_dir, project, spk, segments_for_clone, out_path=out_ref
        )
        ref_paths[spk] = path
        ref_texts[spk] = ref_text

    if not options.mock:
        needs_default = [
            spk
            for spk, lang in speaker_langs.items()
            if spk not in ref_paths and model_kind(models_by_lang[lang]) == "chatterbox"
        ]
        if needs_default:
            from a_wizard.adapters.tts.default_ref import ensure_default_chatterbox_ref

            _log(
                "speak: Chatterbox has no built-in voice; "
                "using a local default reference "
                "(pass --ref SPEAKER=file.wav to replace it)"
            )
            default_ref = ensure_default_chatterbox_ref()
            for spk in needs_default:
                ref_paths[spk] = default_ref

    for spk, path in ref_paths.items():
        if path.is_file():
            ref_digests[spk] = sha256_file(path)

    layout = "timeline" if options.timeline else "sequential"
    sig = speech_signature(
        dialog_digest=source_digest,
        models=models_by_lang,
        voices=voices,
        refs=ref_digests,
        layout=layout,
        pause_ms=options.pause_ms,
        speed=options.speed,
        fit=options.fit,
        fmt=options.format,
    )

    if (
        not options.force
        and speech_json_path is not None
        and speech_json_path.is_file()
        and output_wav.is_file()
    ):
        try:
            prev = json.loads(speech_json_path.read_text(encoding="utf-8"))
            if prev.get("signature") == sig:
                _log("speak: up to date (signature match)")
                return SpeakResult(
                    output=output_wav,
                    speech_json=speech_json_path,
                    skipped=True,
                    cache_hits=int(prev.get("cache_hits", 0)),
                    cache_misses=0,
                    overruns=int(prev.get("overruns", 0)),
                    warnings=list(prev.get("warnings") or []),
                    line_count=int(prev.get("line_count", 0)),
                    sample_rate=int(prev.get("sample_rate", 24_000)),
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    if cache_dir is None and project_dir is not None:
        cache_dir = project_dir / SPEECH_CACHE_REL
    if cache_dir is None:
        cache_dir = output_wav.parent / ".speak-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    engines: dict[str, Any] = {}
    announced: set[str] = set()
    cache_hits = 0
    cache_misses = 0
    clips: list[np.ndarray] = []
    clip_speakers: list[str] = []
    starts: list[int | None] = []
    ends: list[int | None] = []
    sample_rate = 24_000

    # Group by model for hot cache, but keep order for rendering via index map
    for line in script.lines:
        model_id = models_by_lang[line.lang]
        if model_id not in announced:
            _log(
                f"speak: loading model {model_id} (MLX); "
                "first run may download weights"
            )
            announced.add(model_id)
        engine = _engine_for_model(model_id, mock=options.mock, cache=engines)
        sample_rate = getattr(engine, "sample_rate", sample_rate) or sample_rate
        voice = voices.get(line.speaker)
        ref = ref_paths.get(line.speaker)
        ref_digest = ref_digests.get(line.speaker)
        key = cache_key(
            text=line.text,
            lang=line.lang,
            model_id=model_id,
            voice=voice,
            ref_digest=ref_digest,
            speed=options.speed,
        )
        cached = cache_dir / f"{key}.wav"
        if not options.force and cached.is_file():
            audio, sr = _read_wav_mono(cached)
            if sr != sample_rate and len(audio) > 0:
                # simple resample via linspace if rates differ
                new_len = int(len(audio) * sample_rate / sr)
                idx = np.linspace(0, len(audio) - 1, new_len)
                audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
            cache_hits += 1
        else:
            audio = engine.synthesize(
                line.text,
                lang=line.lang,
                voice=voice,
                ref_audio=ref,
                ref_text=ref_texts.get(line.speaker),
                speed=options.speed,
            )
            write_wav_mono(cached, audio, sample_rate)
            cache_misses += 1
        clips.append(audio)
        clip_speakers.append(line.speaker)
        starts.append(line.start_ms)
        ends.append(line.end_ms)

    for w in warnings:
        if w == "chatterbox_no_presets":
            _log(
                "speak: warning: this model has no preset voices; "
                "speakers share one reference voice "
                "(use --ref or --clone for a different voice, "
                "or --model LANG=… for a model with presets)"
            )

    overruns = 0
    if options.timeline:
        mixed, overruns = render_timeline(
            clips,
            starts,
            ends,
            sample_rate=sample_rate,
            fit=options.fit,
        )
        if overruns:
            _log(f"speak: timeline overruns={overruns}")
    else:
        mixed = render_sequential(
            clips,
            clip_speakers,
            sample_rate=sample_rate,
            pause_ms=options.pause_ms,
            speaker_change_pause_ms=options.speaker_change_pause_ms,
        )

    write_wav_mono(output_wav, mixed, sample_rate)
    final_out = output_wav
    if options.format == "mp3":
        mp3_path = output_wav.with_suffix(".mp3")
        if options.output and options.output.suffix.lower() == ".mp3":
            mp3_path = options.output
        convert_to_mp3(output_wav, mp3_path)
        final_out = mp3_path

    meta = {
        "algo_version": SPEAK_ALGO_VERSION,
        "signature": sig,
        "dialog_digest": source_digest,
        "models": models_by_lang,
        "voices": voices,
        "refs": {k: str(v) for k, v in ref_paths.items()},
        "layout": layout,
        "pause_ms": options.pause_ms,
        "speed": options.speed,
        "fit": options.fit,
        "format": options.format,
        "sample_rate": sample_rate,
        "line_count": len(script.lines),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "overruns": overruns,
        "output": (
            str(final_out.name)
            if project_dir and final_out.is_relative_to(project_dir)
            else str(final_out)
        ),
        "warnings": warnings,
    }
    if speech_json_path is not None:
        atomic_write_text(
            speech_json_path,
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        )

    _log(
        f"speak: done lines={len(script.lines)} "
        f"cache_hits={cache_hits} cache_misses={cache_misses}"
    )
    return SpeakResult(
        output=final_out,
        speech_json=speech_json_path,
        skipped=False,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        overruns=overruns,
        warnings=warnings,
        line_count=len(script.lines),
        sample_rate=sample_rate,
    )


def speak_project(
    project_dir: Path,
    project: Project,
    options: SpeakOptions,
    *,
    log: Callable[..., None] | None = None,
) -> SpeakResult:
    script = load_script_from_dialog(
        project_dir, project, language=options.language
    )
    digest = sha256_file(project_dir / "dialog" / "dialog.json")
    out = options.output
    if out is None:
        if options.format == "mp3":
            out = project_dir / "dialog" / "speech.mp3"
            wav_path = project_dir / SPEECH_WAV_REL
        else:
            wav_path = project_dir / SPEECH_WAV_REL
            out = wav_path
    else:
        wav_path = out if out.suffix.lower() == ".wav" else out.with_suffix(".wav")
    return run_speak(
        script=script,
        options=options,
        project_dir=project_dir,
        project=project,
        output_wav=wav_path,
        speech_json_path=project_dir / SPEECH_JSON_REL,
        cache_dir=project_dir / SPEECH_CACHE_REL,
        refs_dir=project_dir / SPEECH_REFS_REL,
        yaml_path=project_dir / SPEAK_YAML_NAME,
        source_digest=digest,
        log=log,
    )


def speak_txt(
    path: Path,
    options: SpeakOptions,
    *,
    log: Callable[..., None] | None = None,
) -> SpeakResult:
    script = load_script_from_txt(
        path,
        language=options.language,
        speakers_from_prefix=options.speakers_from_prefix,
    )
    digest = sha256_file(path)
    if options.output is not None:
        out = options.output
        wav_path = out if out.suffix.lower() == ".wav" else out.with_suffix(".wav")
    else:
        wav_path = path.parent / f"{path.stem}.speech.wav"
        out = path.parent / f"{path.stem}.speech.{options.format}"
    meta_path = wav_path.with_suffix(".json")
    return run_speak(
        script=script,
        options=options,
        output_wav=wav_path,
        speech_json_path=meta_path,
        cache_dir=wav_path.parent / f".{path.stem}.speak-cache",
        yaml_path=path.parent / SPEAK_YAML_NAME,
        source_digest=digest,
        log=log,
    )
