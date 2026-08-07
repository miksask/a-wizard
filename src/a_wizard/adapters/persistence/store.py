"""Atomic filesystem persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from a_wizard.domain.errors import StateError, UsageError
from a_wizard.domain.freshness import sha256_file
from a_wizard.domain.models import SCHEMA_VERSION, Project, utc_now_iso

MANIFEST_NAME = "manifest.yaml"


def project_dir_for_video(video: Path) -> Path:
    video = video.resolve()
    return video.parent / f"{video.stem}.project"


def ensure_under(project_dir: Path, rel: str) -> Path:
    project_dir = project_dir.resolve()
    target = (project_dir / rel).resolve()
    if not str(target).startswith(str(project_dir) + os.sep) and target != project_dir:
        raise UsageError(f"path escapes project dir: {rel}", code="path_escape")
    return target


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # best-effort directory fsync
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


class YamlProjectRepository:
    def exists(self, project_dir: Path) -> bool:
        return (project_dir / MANIFEST_NAME).is_file()

    def load(self, project_dir: Path) -> Project:
        path = project_dir / MANIFEST_NAME
        if not path.is_file():
            raise StateError(f"manifest not found: {path}", code="manifest_missing")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return Project.from_dict(data)
        except ValueError as e:
            raise StateError(str(e), code="manifest_schema", cause=e) from e
        except Exception as e:
            raise StateError(f"failed to load manifest: {e}", code="manifest_load", cause=e) from e

    def save(self, project_dir: Path, project: Project) -> None:
        project.updated_at = utc_now_iso()
        if project.schema_version != SCHEMA_VERSION:
            raise StateError(
                f"refusing to save schema_version={project.schema_version}",
                code="manifest_schema",
            )
        data = project.to_dict()
        text = yaml.dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        atomic_write_text(project_dir / MANIFEST_NAME, text)
        self._write_manifest_md(project_dir, project)

    def _write_manifest_md(self, project_dir: Path, project: Project) -> None:
        lines = [
            "# a-wizard project",
            "",
            f"- **schema**: {project.schema_version}",
            f"- **video**: `{project.source.get('path', '?')}`",
            f"- **updated**: {project.updated_at}",
            "",
            "## Tracks",
            "",
            "| # | Mode | Status | Lang | Speaker/map |",
            "|---|------|--------|------|-------------|",
        ]
        for t in project.tracks:
            if t.mode.value == "plain":
                spk = t.plain_speaker or "—"
            elif t.mode.value == "diarized":
                spk = ", ".join(f"{k}→{v}" for k, v in t.speaker_map.items()) or "(pending)"
            elif t.mode.value == "skipped":
                spk = f"skipped: {t.skip_reason or ''}".strip()
            else:
                spk = "—"
            lines.append(
                f"| {t.index} | {t.mode.value} | {t.status.value} | {t.language} | {spk} |"
            )
        lines.extend(["", "## Stages", ""])
        for key, rec in sorted(project.stages.items()):
            lines.append(f"- `{key}`: {rec.status.value}")
        atomic_write_text(project_dir / "manifest.md", "\n".join(lines) + "\n")


class FsArtifactStore:
    def write_text(self, project_dir: Path, rel: str, text: str) -> str:
        path = ensure_under(project_dir, rel)
        atomic_write_text(path, text)
        return sha256_file(path)

    def write_json(self, project_dir: Path, rel: str, data: Any) -> str:
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        return self.write_text(project_dir, rel, text)

    def write_bytes(self, project_dir: Path, rel: str, data: bytes) -> str:
        path = ensure_under(project_dir, rel)
        atomic_write_bytes(path, data)
        return sha256_file(path)

    def read_text(self, project_dir: Path, rel: str) -> str:
        return ensure_under(project_dir, rel).read_text(encoding="utf-8")

    def digest(self, project_dir: Path, rel: str) -> str:
        return sha256_file(ensure_under(project_dir, rel))


class FileProjectLock:
    def __init__(self) -> None:
        self._fds: dict[str, int] = {}

    def acquire(self, project_dir: Path) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        lock_path = project_dir / ".a-wizard.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            raise StateError(
                f"project locked by another process: {project_dir}",
                code="project_locked",
                next_step="wait or stop the other a-wizard process",
                cause=e,
            ) from e
        self._fds[str(project_dir.resolve())] = fd

    def release(self, project_dir: Path) -> None:
        key = str(project_dir.resolve())
        fd = self._fds.pop(key, None)
        if fd is None:
            return
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
