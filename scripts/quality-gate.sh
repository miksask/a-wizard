#!/usr/bin/env bash
# Full local quality gate for a-wizard (no cloud CI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== hygiene =="
bash "$ROOT/scripts/check-repo-hygiene.sh"

echo "== lock =="
uv lock --check

echo "== ruff =="
uv run --extra dev ruff check src tests

echo "== ffmpeg =="
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "ERROR: ffmpeg/ffprobe required for the full gate (integration tests must not skip)" >&2
  exit 1
fi

echo "== pytest =="
uv run --extra dev pytest -q --cov=a_wizard --cov-report=term-missing --cov-fail-under=70

echo "== build =="
uv build

echo "OK quality gate passed"
