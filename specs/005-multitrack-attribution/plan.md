# Implementation Plan: Multitrack Attribution

**Branch**: `005-multitrack-attribution` | **Date**: 2026-10-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-multitrack-attribution/spec.md`

## Summary

Replace raw-loudness channel attribution with a per-track activity model: two-pass local noise floors, a 9.5 dB speech gate, gain-normalized dominance between active tracks, context resolution, island smoothing, automatic crosstalk compensation, and removal of isolated hallucinations. Normalize and track-scope diarizer labels, assign diarized words by turn overlap, cache diarization, version the attribute signature, reuse the activity model to filter per-track transcripts, and add opt-in ASR cleanup (gated/normalized audio, Whisper `hallucination_silence_threshold`) behind a new `options` command.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: numpy (base), existing Typer/YAML stack; no new dependencies

**Storage**: Project directory; new artifacts `meta/diar/track_{n}.meta.json`, `transcripts/track_{n}.words.json`, `meta/track_filter.json`, optional `tracks/track_{n}.clean.wav`

**Testing**: pytest with synthetic numpy signals, short ffmpeg fixtures, mock ASR/diar adapters, JSON schema contract tests

**Target Platform**: macOS and Linux

**Project Type**: local CLI

**Performance Goals**: activity model + crosstalk ≤ 5 s per 1.5 h of 4 tracks; per-word evaluation linear in words × tracks

**Constraints**: Local-first; synthetic tests only; schema_version stays 2; no ASR re-run for existing projects unless an opt-in option is enabled

**Scale/Scope**: 1–4 (up to N) tracks, recordings up to several hours

## Constitution Check

- **I. Local-First Privacy**: All processing local; reports contain counts and levels, never transcript text. Pass.
- **II. Resume-Safe Atomic State**: Diarization cache, word files, clean WAVs written atomically; options saved under lock. Pass.
- **III. Verifiable Freshness**: Attribution version + params in attribute and per-track merge signatures; options enter signatures only when enabled. Pass.
- **IV. Ports and Adapters**: Activity model and attribution are pure numpy in the application layer; label normalization is domain; the gain mixer is a media adapter; ASR adapters accept the new optional parameter. Pass.
- **V. Synthetic Tests First**: Every scenario (noisy mic, two diarized tracks, four rooms with crosstalk, hallucinations, per-track duplicates) is synthetic. Pass.

## Project Structure

### Documentation (this feature)

```text
specs/005-multitrack-attribution/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── attribution-report.schema.json
│   └── mix.segments.schema.json
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
src/a_wizard/
  domain/activity.py               # ActivityParams, CleanupParams (pure data)
  domain/models.py                 # normalize_diar_label, track_scoped_speaker, Word flags
  domain/freshness.py              # attribution/cleanup versions in signatures
  application/activity.py          # noise floors, speech levels, word evidence
  application/crosstalk.py         # crosstalk detection + compensation
  application/attribution.py       # mixdown attribution, per-track filter, diar assignment
  application/diar_cache.py        # cached diarization turns
  application/cleanup.py           # opt-in frame gains
  application/service.py           # wiring, options, per-track words, clean audio
  adapters/media/gain_mix.py       # streamed gain mixer for clean audio
  adapters/asr/engines.py          # hallucination_silence_threshold pass-through
  adapters/diarization/*.py        # normalized labels, mock not cacheable
  cli/app.py                       # `options` command

tests/
  unit/test_activity.py
  unit/test_crosstalk.py
  unit/test_attribution.py         # extended scenarios
  unit/test_track_filter.py
  unit/test_diar_cache.py
  unit/test_cleanup.py
  unit/test_domain.py              # label normalization
  unit/test_contracts.py           # report + segments schemas
  application/test_options.py
  integration/test_pipeline.py     # noisy-mic and per-track crosstalk end-to-end
```

**Structure Decision**: Keep the single package; split the activity model and crosstalk into their own modules so attribution stays readable and both modes reuse them.

## Complexity Tracking

None.
