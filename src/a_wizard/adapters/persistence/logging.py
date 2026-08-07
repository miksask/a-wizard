"""JSONL run observer (no secrets / transcript text)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from a_wizard.adapters.persistence.store import atomic_write_text


class JsonlRunObserver:
    def __init__(self, project_dir: Path | None = None, run_id: str | None = None) -> None:
        self.run_id = run_id or str(uuid4())
        self.project_dir = project_dir
        self.path: Path | None = None
        if project_dir is not None:
            logs = project_dir / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            self.path = logs / f"run-{stamp}-{self.run_id[:8]}.jsonl"
            self.path.touch(exist_ok=True)

    def event(self, name: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "run_id": self.run_id,
            "event": name,
            **{k: v for k, v in fields.items() if k not in {"text", "token", "prompt", "hf_token"}},
        }
        line = json.dumps(payload, ensure_ascii=False)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        # also keep a tiny latest pointer best-effort
        if self.project_dir is not None and self.path is not None:
            try:
                atomic_write_text(
                    self.project_dir / "logs" / "latest_run.txt",
                    str(self.path.name) + "\n",
                )
            except OSError:
                pass
