#!/usr/bin/env bash
# Fail if sensitive / media paths look tracked or about to be added.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

# records must be ignored even as a symlink
if git check-ignore -q records 2>/dev/null; then
  :
elif [[ -e records ]]; then
  echo "ERROR: records exists but is not ignored by git" >&2
  fail=1
fi

# No tracked media / secrets
while IFS= read -r path; do
  case "$path" in
    *.wav|*.mkv|*.mp4|*.mov|*.flac|*.aac)
      echo "ERROR: tracked media file: $path" >&2
      fail=1
      ;;
    *HF_TOKEN*|*credentials.json*|*.env)
      echo "ERROR: tracked secret-like path: $path" >&2
      fail=1
      ;;
  esac
done < <(git ls-files)

# Staged additions
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    case "$path" in
      *.wav|*.mkv|*.mp4|*.mov)
        echo "ERROR: staged media file: $path" >&2
        fail=1
        ;;
      records|records/*)
        echo "ERROR: staged records path: $path" >&2
        fail=1
        ;;
    esac
  done < <(git diff --cached --name-only --diff-filter=A 2>/dev/null || true)
fi

exit "$fail"
