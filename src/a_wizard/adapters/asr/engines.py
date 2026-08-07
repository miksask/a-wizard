"""ASR adapters: mock, mlx-whisper, faster-whisper."""

from __future__ import annotations

import platform
from pathlib import Path

from a_wizard.domain.errors import AppError
from a_wizard.domain.models import DEFAULT_MLX_MODEL, Segment, TranscriptResult, Word


class MockAsrAdapter:
    adapter_id = "mock-asr"

    def __init__(
        self,
        segments: list[Segment] | None = None,
        words: list[Word] | None = None,
        result: TranscriptResult | None = None,
    ) -> None:
        self._result = result
        self._segments = segments
        self._words = words

    def transcribe(
        self,
        wav: Path,
        *,
        speaker: str | None = None,
        model: str = "large-v3",
        language: str = "ru",
        compute_type: str = "int8",
        device: str = "auto",
        initial_prompt: str | None = None,
    ) -> TranscriptResult:
        if self._result is not None:
            spk = speaker
            segs = [
                Segment(s.start_ms, s.end_ms, s.text, spk if spk else s.speaker)
                for s in self._result.segments
            ]
            return TranscriptResult(segments=segs, words=list(self._result.words))
        if self._segments is not None:
            spk = speaker or "SPEAKER_00"
            segs = [
                Segment(s.start_ms, s.end_ms, s.text, spk if speaker else s.speaker)
                for s in self._segments
            ]
            words = list(self._words) if self._words is not None else []
            if not words:
                words = [
                    Word(s.start_ms, s.end_ms, s.text, speaker=spk if speaker else s.speaker)
                    for s in segs
                ]
            return TranscriptResult(segments=segs, words=words)
        spk = speaker or "SPEAKER_00"
        segs = [
            Segment(0, 1000, f"mock utterance from {wav.name}", spk),
            Segment(1200, 2200, "second mock line", spk),
        ]
        words = [
            Word(0, 400, "mock", speaker=spk),
            Word(400, 1000, "utterance", speaker=spk),
            Word(1200, 1600, "second", speaker=spk),
            Word(1600, 2200, "line", speaker=spk),
        ]
        return TranscriptResult(segments=segs, words=words)


class MlxWhisperAsrAdapter:
    adapter_id = "mlx-whisper"

    def transcribe(
        self,
        wav: Path,
        *,
        speaker: str | None = None,
        model: str = DEFAULT_MLX_MODEL,
        language: str = "ru",
        compute_type: str = "int8",
        device: str = "auto",
        initial_prompt: str | None = None,
    ) -> TranscriptResult:
        try:
            import mlx_whisper
        except ImportError as e:
            raise AppError(
                "mlx-whisper is not installed. Run: uv sync --extra mlx",
                code="asr_dep_missing",
                next_step="uv sync --extra mlx",
                cause=e,
            ) from e

        repo = model or DEFAULT_MLX_MODEL
        # Accept short names like large-v3-turbo
        if "/" not in repo and not repo.startswith("mlx-community/"):
            if repo in ("large-v3-turbo", "turbo"):
                repo = DEFAULT_MLX_MODEL
            elif not repo.startswith("whisper-"):
                repo = f"mlx-community/whisper-{repo}"

        kwargs: dict = {
            "path_or_hf_repo": repo,
            "language": language,
            "word_timestamps": True,
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        result = mlx_whisper.transcribe(str(wav), **kwargs)
        spk = speaker or "SPEAKER_00"
        segs: list[Segment] = []
        words: list[Word] = []
        for seg in result.get("segments") or []:
            text = (seg.get("text") or "").strip()
            if text:
                segs.append(
                    Segment.from_seconds(
                        float(seg.get("start", 0)),
                        float(seg.get("end", 0)),
                        text,
                        spk,
                    )
                )
            for w in seg.get("words") or []:
                wtext = (w.get("word") or w.get("text") or "").strip()
                if not wtext:
                    continue
                words.append(
                    Word.from_seconds(
                        float(w.get("start", 0)),
                        float(w.get("end", 0)),
                        wtext,
                        speaker=spk,
                    )
                )
        if not words and segs:
            words = [Word(s.start_ms, s.end_ms, s.text, speaker=spk) for s in segs]
        return TranscriptResult(segments=segs, words=words)


class FasterWhisperAsrAdapter:
    adapter_id = "faster-whisper"

    def transcribe(
        self,
        wav: Path,
        *,
        speaker: str | None = None,
        model: str = "large-v3",
        language: str = "ru",
        compute_type: str = "int8",
        device: str = "auto",
        initial_prompt: str | None = None,
    ) -> TranscriptResult:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise AppError(
                "faster-whisper is not installed. Run: uv sync --extra asr",
                code="asr_dep_missing",
                next_step="uv sync --extra asr",
                cause=e,
            ) from e

        # Strip mlx repo prefixes if user switched adapters
        if model.startswith("mlx-community/"):
            model = model.split("/", 1)[1].removeprefix("whisper-")

        spk = speaker or "SPEAKER_00"
        m = WhisperModel(model, compute_type=compute_type)
        kwargs: dict = {
            "language": language,
            "vad_filter": True,
            "vad_parameters": dict(min_silence_duration_ms=500),
            "beam_size": 5,
            "word_timestamps": True,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        segments, _info = m.transcribe(str(wav), **kwargs)
        out: list[Segment] = []
        words: list[Word] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if text:
                out.append(Segment.from_seconds(float(seg.start), float(seg.end), text, spk))
            for w in getattr(seg, "words", None) or []:
                wtext = (getattr(w, "word", None) or "").strip()
                if not wtext:
                    continue
                words.append(
                    Word.from_seconds(float(w.start), float(w.end), wtext, speaker=spk)
                )
        if not words and out:
            words = [Word(s.start_ms, s.end_ms, s.text, speaker=spk) for s in out]
        return TranscriptResult(segments=out, words=words)


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")


def resolve_asr_adapter(name: str = "auto"):
    """Resolve ASR adapter by name or auto-detect."""
    key = (name or "auto").lower()
    if key in ("mock", "mock-asr"):
        return MockAsrAdapter()
    if key == "mlx-whisper":
        return MlxWhisperAsrAdapter()
    if key == "faster-whisper":
        return FasterWhisperAsrAdapter()
    if key == "auto":
        if is_apple_silicon():
            try:
                import mlx_whisper  # noqa: F401

                return MlxWhisperAsrAdapter()
            except ImportError:
                pass
        try:
            import faster_whisper  # noqa: F401

            return FasterWhisperAsrAdapter()
        except ImportError as e:
            raise AppError(
                "No ASR adapter available. Install: uv sync --extra mlx (Apple) "
                "or uv sync --extra asr",
                code="asr_adapter_missing",
                next_step="uv sync --extra mlx",
                cause=e,
            ) from e
    raise AppError(f"Unknown ASR adapter: {name}", code="unknown_asr_adapter")
