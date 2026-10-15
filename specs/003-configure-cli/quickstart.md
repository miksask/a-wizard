# Quickstart: Configure CLI

Prerequisites: `uv sync --extra dev`, ffmpeg for integration fixtures.

## Validation (mocks)

```bash
# after a completed mock run on a two-track fixture:
uv run a-wizard configure ./interview.project \
  --language en --no-prompt \
  --track 0:diarized --track 1:skipped

uv run a-wizard status ./interview.project
# next step should be mix transcription (or mixdown if skipped set changed), not extract

uv run a-wizard run ./interview.project --mock
```

No-op (same flags as already stored) must leave stages succeeded and `run` report Done.

Interactive:

```bash
uv run a-wizard configure ./interview.project
# answer prompt, language, track modes
uv run a-wizard run ./interview.project
```

Other languages:

```bash
# interactive: choose [4] other, then type e.g. German (stored as de)
uv run a-wizard configure ./interview.project

# non-interactive: code, name, or auto
uv run a-wizard configure ./interview.project --language German --no-prompt \
  --track 0:diarized --track 1:skipped
uv run a-wizard configure ./interview.project --language auto --no-prompt \
  --track 0:diarized --track 1:skipped

# unsupported language → usage error (exit 2) with suggestions, nothing saved
uv run a-wizard configure ./interview.project --language klingon --no-prompt \
  --track 0:diarized --track 1:skipped
```

Repeating a no-op with a different spelling (`--language de` after `German`) must stale nothing.

## Automated check

```bash
uv run pytest tests/unit/test_domain.py tests/unit/test_languages.py \
  tests/application/test_configure.py tests/integration/test_pipeline.py
```

Expect configure tests to pass without network, GPU, or `HF_TOKEN`.
