"""Built-in reference clip for Chatterbox, which ships without a default voice."""

from __future__ import annotations

from pathlib import Path

_REF_TEXT = (
    "Hello. This is a clear speaking voice. "
    "It is used only as a reference for synthesis."
)


def default_chatterbox_ref_path() -> Path:
    return Path.home() / ".cache" / "a-wizard" / "tts" / "chatterbox-default-ref.wav"


def ensure_default_chatterbox_ref(path: Path | None = None) -> Path:
    """Return a local reference wav, creating it with Kokoro on first use."""
    path = path or default_chatterbox_ref_path()
    if path.is_file() and path.stat().st_size > 1000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    from a_wizard.adapters.tts.mlx_audio import MlxAudioTtsAdapter
    from a_wizard.adapters.tts.registry import DEFAULT_MODELS
    from a_wizard.application.speak import write_wav_mono

    engine = MlxAudioTtsAdapter(model_id=DEFAULT_MODELS["en"])
    audio = engine.synthesize(_REF_TEXT, lang="en", voice="af_heart")
    write_wav_mono(path, audio, engine.sample_rate)
    return path
