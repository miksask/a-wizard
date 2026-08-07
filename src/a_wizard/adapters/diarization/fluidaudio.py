"""FluidAudio CLI offline diarization adapter (CoreML/ANE)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from a_wizard.domain.errors import AppError
from a_wizard.domain.models import SpeakerTurn


def fluidaudio_bin() -> str | None:
    env = os.environ.get("A_WIZARD_FLUIDAUDIO_BIN")
    if env and Path(env).is_file():
        return env
    return shutil.which("fluidaudio")


class FluidAudioDiarAdapter:
    adapter_id = "fluidaudio"

    def diarize(
        self,
        wav: Path,
        *,
        num_speakers: int | None = None,
        threshold: float | None = None,
        hf_token: str | None = None,
    ) -> list[SpeakerTurn]:
        binary = fluidaudio_bin()
        if not binary:
            raise AppError(
                "fluidaudio binary not found. Set A_WIZARD_FLUIDAUDIO_BIN or install on PATH.",
                code="fluidaudio_missing",
                next_step="build/install FluidAudio CLI and export A_WIZARD_FLUIDAUDIO_BIN",
            )

        wav = wav.resolve()
        with tempfile.TemporaryDirectory(prefix="a-wizard-fluid-") as tmp:
            out_json = Path(tmp) / "diar.json"
            cmd = [
                binary,
                "process",
                str(wav),
                "--mode",
                "offline",
                "--output",
                str(out_json),
            ]
            if threshold is not None:
                cmd.extend(["--threshold", str(threshold)])
            if num_speakers is not None:
                cmd.extend(["--num-speakers", str(num_speakers)])
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except FileNotFoundError as e:
                raise AppError(
                    "fluidaudio binary not executable",
                    code="fluidaudio_missing",
                    cause=e,
                ) from e
            except subprocess.CalledProcessError as e:
                raise AppError(
                    f"fluidaudio failed: {(e.stderr or e.stdout or '')[:500]}",
                    code="fluidaudio_failed",
                    cause=e,
                ) from e

            if not out_json.is_file():
                # Some CLI versions print JSON to stdout file next to input
                candidates = list(Path(tmp).glob("*.json"))
                if not candidates:
                    raise AppError(
                        "fluidaudio produced no JSON output",
                        code="fluidaudio_no_output",
                    )
                out_json = candidates[0]
            data = json.loads(out_json.read_text(encoding="utf-8"))

        return _parse_fluidaudio_json(data)


def _parse_fluidaudio_json(data: dict | list) -> list[SpeakerTurn]:
    segments = data
    if isinstance(data, dict):
        segments = data.get("segments") or data.get("turns") or data.get("speakers") or []
    turns: list[SpeakerTurn] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        speaker = (
            seg.get("speakerId")
            or seg.get("speaker")
            or seg.get("label")
            or "SPEAKER_00"
        )
        speaker = str(speaker)
        if not speaker.startswith("SPEAKER_"):
            # normalize numeric ids
            if speaker.isdigit():
                speaker = f"SPEAKER_{int(speaker):02d}"
            else:
                speaker = f"SPEAKER_{speaker}"
        start = seg.get("startTimeSeconds", seg.get("start", seg.get("start_ms")))
        end = seg.get("endTimeSeconds", seg.get("end", seg.get("end_ms")))
        if start is None or end is None:
            continue
        if "startTimeSeconds" in seg or (
            isinstance(start, float) or (isinstance(start, (int, float)) and float(start) < 10_000)
        ):
            # Heuristic: values < 10000 treated as seconds unless *_ms keys
            if "start_ms" in seg or "end_ms" in seg:
                turns.append(SpeakerTurn(int(start), int(end), speaker))
            else:
                turns.append(SpeakerTurn.from_seconds(float(start), float(end), speaker))
        else:
            turns.append(SpeakerTurn(int(start), int(end), speaker))
    return turns
