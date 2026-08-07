"""ffmpeg/ffprobe media adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from a_wizard.domain.errors import AppError, UsageError


class FfmpegMediaAdapter:
    adapter_id = "ffmpeg"

    def probe(self, video: Path) -> dict[str, Any]:
        video = video.resolve()
        if not video.is_file():
            raise UsageError(f"video not found: {video}", code="video_missing")
        try:
            streams_p = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a",
                    "-show_entries",
                    "stream=index,codec_name,channels,sample_rate,duration",
                    "-of",
                    "json",
                    str(video),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            streams = (json.loads(streams_p.stdout or "{}").get("streams")) or []
            dur_p = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            duration_s = float((dur_p.stdout or "").strip() or "nan")
            duration_ms = None if duration_s != duration_s else int(round(duration_s * 1000))
        except FileNotFoundError as e:
            raise AppError(
                "ffprobe not found; install ffmpeg",
                code="ffprobe_missing",
                next_step="install ffmpeg/ffprobe",
                cause=e,
            ) from e
        except subprocess.CalledProcessError as e:
            raise AppError(
                f"ffprobe failed for {video}",
                code="ffprobe_failed",
                cause=e,
            ) from e
        except ValueError:
            duration_ms = None
        return {
            "path": str(video),
            "basename": video.name,
            "duration_ms": duration_ms,
            "audio_stream_count": len(streams),
            "audio_streams": streams,
            "content_fingerprint": f"{video.stat().st_size}:{int(video.stat().st_mtime)}",
        }

    def extract_all(self, video: Path, project_dir: Path, *, force: bool = False) -> list[Path]:
        meta = self.probe(video)
        n = int(meta["audio_stream_count"])
        if n == 0:
            raise UsageError(f"no audio streams in {video}", code="no_audio")
        tracks_dir = project_dir / "tracks"
        tracks_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i in range(n):
            out = tracks_dir / f"track_{i}.wav"
            if not force and out.is_file() and self._duration_matches(video, out):
                paths.append(out)
                continue
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(video),
                        "-map",
                        f"0:a:{i}",
                        "-c:a",
                        "pcm_s16le",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        str(out),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as e:
                raise AppError(
                    "ffmpeg not found; install ffmpeg",
                    code="ffmpeg_missing",
                    next_step="install ffmpeg",
                    cause=e,
                ) from e
            except subprocess.CalledProcessError as e:
                raise AppError(
                    f"ffmpeg extract failed for track {i}",
                    code="ffmpeg_extract_failed",
                    cause=e,
                ) from e
            paths.append(out)
        return paths

    def mixdown(
        self,
        wavs: list[Path],
        out: Path,
        *,
        force: bool = False,
    ) -> Path:
        """Mix multiple mono WAVs into one via ffmpeg amix."""
        if not wavs:
            raise UsageError("no wavs to mix", code="mixdown_empty")
        out = out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.is_file() and not force:
            return out
        if len(wavs) == 1:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(wavs[0]),
                "-c:a",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(out),
            ]
        else:
            n = len(wavs)
            cmd = ["ffmpeg", "-y"]
            for w in wavs:
                cmd.extend(["-i", str(w)])
            labels = "".join(f"[{i}:a]" for i in range(n))
            filt = (
                f"{labels}amix=inputs={n}:duration=longest"
                f":dropout_transition=0:normalize=0[aout]"
            )
            cmd.extend(
                [
                    "-filter_complex",
                    filt,
                    "-map",
                    "[aout]",
                    "-c:a",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(out),
                ]
            )
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise AppError(
                "ffmpeg not found; install ffmpeg",
                code="ffmpeg_missing",
                next_step="install ffmpeg",
                cause=e,
            ) from e
        except subprocess.CalledProcessError as e:
            raise AppError(
                f"ffmpeg mixdown failed: {(e.stderr or '')[:400]}",
                code="ffmpeg_mixdown_failed",
                cause=e,
            ) from e
        return out

    def _duration_matches(self, src: Path, wav: Path, eps: float = 0.05) -> bool:
        try:
            def dur(p: Path) -> float | None:
                r = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(p),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return float((r.stdout or "").strip())
            a, b = dur(src), dur(wav)
            if a is None or b is None:
                return False
            return abs(a - b) <= eps
        except Exception:
            return False
