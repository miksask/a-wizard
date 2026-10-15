#!/usr/bin/env bash
# Copy top-level records/*.project/dialog/transcript.txt → records/for-gpt/<stem>.transcript.txt
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEST="records/for-gpt"
mkdir -p "$DEST"

copied=0
skipped=0

shopt -s nullglob
for proj in records/*.project; do
  [[ -d "$proj" ]] || continue
  src="$proj/dialog/transcript.txt"
  stem="$(basename "$proj" .project)"
  dst="$DEST/${stem}.transcript.txt"
  if [[ -f "$src" ]]; then
    cp "$src" "$dst"
    echo "copied: $src -> $dst"
    copied=$((copied + 1))
  else
    echo "skip (missing): $src" >&2
    skipped=$((skipped + 1))
  fi
done

echo "done: copied=$copied skipped=$skipped"
