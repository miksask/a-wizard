"""Persistence atomic write and lock tests."""

from __future__ import annotations

from pathlib import Path

from a_wizard.adapters.persistence.store import (
    FileProjectLock,
    FsArtifactStore,
    YamlProjectRepository,
)
from a_wizard.domain.models import Project


def test_atomic_roundtrip(tmp_path: Path):
    repo = YamlProjectRepository()
    store = FsArtifactStore()
    project_dir = tmp_path / "p.project"
    project_dir.mkdir()
    project = Project.new(source_path="/x.mkv", basename="x.mkv", audio_stream_count=1)
    repo.save(project_dir, project)
    loaded = repo.load(project_dir)
    assert loaded.project_id == project.project_id
    digest = store.write_text(project_dir, "dialog/hello.txt", "hi\n")
    assert len(digest) == 64
    assert store.read_text(project_dir, "dialog/hello.txt") == "hi\n"


def test_lock_exclusive(tmp_path: Path):
    project_dir = tmp_path / "p.project"
    project_dir.mkdir()
    a = FileProjectLock()
    b = FileProjectLock()
    a.acquire(project_dir)
    try:
        raised = False
        try:
            b.acquire(project_dir)
        except Exception:
            raised = True
        assert raised
    finally:
        a.release(project_dir)
    b.acquire(project_dir)
    b.release(project_dir)
