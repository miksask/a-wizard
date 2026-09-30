"""Experimental speakrs CoreML diarization adapter (RTTM)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from a_wizard.domain.errors import AppError
from a_wizard.domain.models import SpeakerTurn


def speakrs_bin() -> str | None:
    env = os.environ.get("A_WIZARD_SPEAKRS_BIN")
    if env and Path(env).is_file():
        return env
    return shutil.which("speakrs")


class SpeakrsDiarAdapter:
    adapter_id = "speakrs-coreml"

    def diarize(
        self,
        wav: Path,
        *,
        num_speakers: int | None = None,
        threshold: float | None = None,
        hf_token: str | None = None,
    ) -> list[SpeakerTurn]:
        binary = speakrs_bin()
        if not binary:
            raise AppError(
                "speakrs binary not found. Set A_WIZARD_SPEAKRS_BIN or install on PATH.",
                code="speakrs_missing",
                next_step="install speakrs coreml CLI for experimental bench",
            )

        wav = wav.resolve()
        with tempfile.TemporaryDirectory(prefix="a-wizard-speakrs-") as tmp:
            out_rttm = Path(tmp) / "out.rttm"
            cmd = [binary, "diarize", str(wav), "--output", str(out_rttm), "--backend", "coreml"]
            if num_speakers is not None:
                cmd.extend(["--num-speakers", str(num_speakers)])
            try:
                proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            except FileNotFoundError as e:
                raise AppError("speakrs not executable", code="speakrs_missing", cause=e) from e
            if proc.returncode != 0:
                # Try alternate CLI shape
                cmd2 = [binary, "process", str(wav), "--rttm", str(out_rttm)]
                proc = subprocess.run(cmd2, check=False, capture_output=True, text=True)
                if proc.returncode != 0:
                    raise AppError(
                        f"speakrs failed: {(proc.stderr or proc.stdout or '')[:500]}",
                        code="speakrs_failed",
                    )
            if not out_rttm.is_file():
                # stdout may contain RTTM
                text = proc.stdout or ""
                if "SPEAKER" in text:
                    return parse_rttm(text)
                raise AppError("speakrs produced no RTTM", code="speakrs_no_output")
            return parse_rttm(out_rttm.read_text(encoding="utf-8"))


def parse_rttm(text: str) -> list[SpeakerTurn]:
    turns: list[SpeakerTurn] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 8 or parts[0].upper() != "SPEAKER":
            continue
        start = float(parts[3])
        dur = float(parts[4])
        speaker = parts[7]
        if not speaker.startswith("SPEAKER_"):
            if speaker.isdigit():
                speaker = f"SPEAKER_{int(speaker):02d}"
            else:
                speaker = f"SPEAKER_{speaker}"
        turns.append(SpeakerTurn.from_seconds(start, start + dur, speaker))
    return turns
