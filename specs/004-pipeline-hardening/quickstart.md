# Quickstart: Pipeline Hardening

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
./scripts/quality-gate.sh

# optional local hooks (one-time per clone)
git config core.hooksPath hooks
```

Verify metadata-only status (no ML extras required for this command):

```bash
uv run a-wizard status /path/to/recording.project
```

After deleting a mix ASR artifact, `a-wizard plan … --json` should show `transcribe_mix` (or equivalent) as next, not `done`.
