# Requirements Checklist: Multitrack ASR Wizard

**Feature**: 001-multitrack-asr-wizard  
**Created**: 2026-08-06

## Completeness

- [x] P1 user stories cover end-to-end, resume, track modes
- [x] Non-interactive policy explicit (preset + allow-raw)
- [x] Edge cases listed (no audio, token, lock, collision)
- [x] Out of scope stated (legacy import, GUI, LLM summary)

## Clarity

- [x] Freshness vs status flags distinguished
- [x] Exit codes defined
- [x] Artifact names stable and documented
- [x] Prompt inheritance rules explicit

## Consistency

- [x] Spec ↔ data-model ↔ CLI contract aligned
- [x] Constitution privacy/testing rules reflected
- [x] Adapter swap acceptance criterion present

## Notes

Legacy asr-wizard remains reference for behavior only; bugs (stale done, SPEAKER collision, --yes guessing) intentionally fixed.
