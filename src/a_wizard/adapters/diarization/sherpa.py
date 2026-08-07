"""sherpa-onnx offline speaker diarization adapter."""

from __future__ import annotations

import os
from pathlib import Path

from a_wizard.domain.errors import AppError
from a_wizard.domain.models import SpeakerTurn


def _model_dir() -> Path:
    env = os.environ.get("A_WIZARD_SHERPA_MODEL_DIR")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "a-wizard" / "sherpa-onnx-diar"


class SherpaOnnxDiarAdapter:
    adapter_id = "sherpa-onnx"

    def diarize(
        self,
        wav: Path,
        *,
        num_speakers: int | None = None,
        threshold: float | None = None,
        hf_token: str | None = None,
    ) -> list[SpeakerTurn]:
        try:
            import sherpa_onnx
        except ImportError as e:
            raise AppError(
                "sherpa-onnx is not installed. Run: uv sync --extra diar-onnx",
                code="diar_dep_missing",
                next_step="uv sync --extra diar-onnx",
                cause=e,
            ) from e

        model_dir = _model_dir()
        seg = model_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
        emb = (
            model_dir
            / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
        )
        # Prefer NeMo TitaNet Small if present
        titanet = model_dir / "nemo_en_titanet_small.onnx"
        if titanet.is_file():
            emb = titanet

        if not seg.is_file() or not emb.is_file():
            raise AppError(
                f"sherpa-onnx diarization models not found under {model_dir}. "
                "Download pyannote segmentation 3.0 ONNX and NeMo TitaNet Small.",
                code="sherpa_models_missing",
                next_step=f"place models in {model_dir} or set A_WIZARD_SHERPA_MODEL_DIR",
            )

        clustering = sherpa_onnx.FastClusteringConfig(
            num_clusters=-1 if num_speakers is None else int(num_speakers),
            threshold=0.90 if threshold is None else float(threshold),
        )
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(seg)
                ),
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb)),
            clustering=clustering,
        )
        if not config.validate():
            raise AppError("Invalid sherpa-onnx diarization config", code="sherpa_config")

        diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
        # Load audio as float32 mono 16k
        samples, sample_rate = _load_wav_mono16k(wav)
        if sample_rate != diarizer.sample_rate:
            raise AppError(
                f"sample rate {sample_rate} != diarizer {diarizer.sample_rate}",
                code="sherpa_sample_rate",
            )
        result = diarizer.process(samples).sort_by_start_time()
        turns: list[SpeakerTurn] = []
        for r in result:
            speaker = f"SPEAKER_{int(r.speaker):02d}"
            turns.append(SpeakerTurn.from_seconds(float(r.start), float(r.end), speaker))
        return turns


def _load_wav_mono16k(path: Path) -> tuple[list[float] | object, int]:
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    if sw != 2:
        raise AppError(f"expected 16-bit PCM wav, got sampwidth={sw}", code="wav_format")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        audio = audio.reshape(-1, nch).mean(axis=1)
    return audio, rate
