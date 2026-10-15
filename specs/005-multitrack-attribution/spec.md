# Feature Specification: Multitrack Attribution

**Feature Branch**: `005-multitrack-attribution`

**Created**: 2026-10-12

**Status**: Implemented

**Input**: User description: "The second (plain) track is transcribed and merged into the first (diarized) track's transcript very strangely: single words of other speakers end up on the plain speaker. Fix every cause that hurts recognition in such cases, keeping in mind that two tracks may both be diarized and that recordings may have 3–4 tracks (rooms recorded separately, then combined into one video, all on one call)."

## Background

Mixdown mode runs one ASR pass on the mix and attributes every word to the source track with the highest raw RMS in the word window. Real OBS recordings combine a digital desktop-capture track (near digital silence between phrases, RMS ≈ 8–10) with an analog microphone (constant noise floor, RMS ≈ 100–900). Whenever a word window falls into a pause on the desktop track, the microphone's noise wins by a wide margin, so remote speakers' words are cut out of their sentences and attributed to the plain speaker. On two real recordings this produced 311 and 85 plain-speaker lines of which only a handful were real speech. Whisper hallucinations in silence ("Thank you.", "....") were attributed the same way. Separately, FluidAudio speaker ids (`S1`, `S2`, …) were not track-scoped, so two diarized tracks would merge speakers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Noise-robust channel attribution (Priority: P1)

The operator records a call with OBS: track 0 is desktop audio (remote participants, diarized), track 1 is their own microphone (plain). Attribution only considers a track for a word when that track actually carries speech above its own noise floor, so the microphone's noise no longer steals words from remote speakers, and remote phrases stay whole.

**Why this priority**: This is the reported defect; it corrupts every recording made with a noisy microphone.

**Independent Test**: Synthetic two-track fixture: track 0 has speech-like bursts separated by digital silence, track 1 has a constant noise floor plus one short speech burst. Words placed inside and at the edges of track-0 bursts are attributed to track 0; words inside the track-1 burst are attributed to the plain speaker; no single-word plain-speaker islands appear inside track-0 phrases.

**Acceptance Scenarios**:

1. **Given** a plain microphone track with a noise floor 20–30 dB above the desktop track's silence, **When** attribution runs, **Then** words whose window falls into a desktop pause are not attributed to the microphone unless the microphone carries speech above its own floor.
2. **Given** a word that no track carries speech for, **When** attribution runs, **Then** the word joins the nearest confidently attributed neighbor in time instead of opening a new turn.
3. **Given** a 1–2 word island of another channel inside a phrase without strong evidence for that channel, **When** attribution runs, **Then** the island is reassigned to the surrounding channel.
4. **Given** a completed project created before this feature, **When** the operator runs `a-wizard run PROJECT`, **Then** only attribute, merge, and minimize are redone (ASR and mixdown stay fresh).

---

### User Story 2 - Several diarized tracks (Priority: P1)

Two or more tracks are diarized (for example desktop audio with several remote people plus a room microphone with several local people). Every diarizer's speaker ids are normalized and scoped by track, so speakers from different tracks never collide, and words are assigned to the diarization turn they overlap most.

**Why this priority**: Without track scoping, two diarized tracks silently merge different people into one label.

**Independent Test**: Two diarized synthetic tracks whose mock diarizers both return `S1`/`S2`; the dialog contains four distinct labels `SPEAKER_T0D1`, `SPEAKER_T0D2`, `SPEAKER_T1D1`, `SPEAKER_T1D2`.

**Acceptance Scenarios**:

1. **Given** FluidAudio ids `S1`, `S2`, **When** turns are parsed, **Then** they become `SPEAKER_01`, `SPEAKER_02`, and in the dialog `SPEAKER_T{track}D1`, `SPEAKER_T{track}D2`.
2. **Given** legacy cached labels such as `SPEAKER_S3`, **When** they are track-scoped, **Then** they become `SPEAKER_T{track}D3`.
3. **Given** a word that straddles the boundary between two diarization turns, **When** speakers are assigned, **Then** the word follows the speaker of its nearest neighbor on the same track if that speaker is one of the overlapped turns.

---

### User Story 3 - Three or four room tracks with crosstalk (Priority: P2)

Rooms recorded separately are combined into one video; each track carries its own room's speakers, possibly with different gains, and rooms may hear each other through loudspeakers (a delayed, attenuated copy of another room's speech in their microphone). Attribution compares tracks by loudness relative to each track's own typical speech level and automatically detects and compensates such crosstalk.

**Why this priority**: Requested scenario; raw loudness comparison fails when microphone gains differ or when a loud room microphone picks up another room's speech.

**Independent Test**: Four synthetic tracks with different gains; room B's microphone carries a 240 ms delayed copy of room A at a raw level higher than A's direct level. Words spoken in room A are attributed to track A; the report lists the detected A→B crosstalk with its lag.

**Acceptance Scenarios**:

1. **Given** tracks with different microphone gains, **When** two tracks carry speech in the same word window, **Then** the winner is the track whose level is highest relative to its own typical speech level.
2. **Given** a consistent delayed copy of track A inside track B, **When** attribution runs, **Then** the crosstalk is detected (lag within ±40 ms of truth), compensated before the activity decision, and reported.
3. **Given** independent tracks (normal turn-taking, no crosstalk), **When** attribution runs, **Then** no crosstalk is reported and results equal the uncompensated decision.

---

### User Story 4 - Drop hallucinations in silence (Priority: P2)

Whisper sometimes emits text where nobody speaks ("Thank you.", "Продолжение следует...", "...."). Words that no track carries speech for and that are isolated from real speech are removed from the dialog; they stay in the raw ASR output.

**Why this priority**: These words otherwise appear as a separate (usually plain-speaker) line.

**Independent Test**: A silent run of words more than 2 s away from any speech evidence is excluded from segments and flagged `dropped` in `mix.segments.json`; a silent word adjacent to speech is kept and attached to its neighbor; when no track has any activity at all, nothing is dropped.

**Acceptance Scenarios**:

1. **Given** words whose best track is below 6 dB over its noise floor and that are ≥ 2 s from any word with speech evidence, **When** attribution runs, **Then** they are excluded from the dialog and counted in the report.
2. **Given** completely silent synthetic audio, **When** attribution runs, **Then** no word is dropped and the legacy loudest-channel rule is used.

---

### User Story 5 - Per-track mode uses the same activity model (Priority: P2)

In `per_track` mode every track is transcribed separately, so a noisy track hallucinates in silence and a track with crosstalk transcribes another room's speech a second time. At merge time, words of each track are kept only when that track carries speech: hallucinations isolated in silence, crosstalk-explained words, and words clearly dominated by another track that has its own overlapping words are removed.

**Why this priority**: Requested; per-track mode otherwise duplicates text in multi-room recordings.

**Independent Test**: Two-track per-track fixture where track 1 contains a delayed copy of track 0 and both ASR passes return the same phrase; the merged dialog contains the phrase once, from track 0.

**Acceptance Scenarios**:

1. **Given** per-track words on a track with no speech in their window and no nearby speech, **When** merge runs, **Then** they are dropped.
2. **Given** projects transcribed before this feature (no per-track word files), **When** merge runs, **Then** segments are filtered as coarse units and the merge still succeeds.

---

### User Story 6 - Opt-in ASR cleanup (Priority: P3)

The operator can opt in to cleaner ASR input: inactive tracks are attenuated and track levels are normalized before mixing (mixdown) or before per-track ASR (per_track), and Whisper's `hallucination_silence_threshold` can be set. Both are off by default and changing them re-runs only the dependent stages.

**Why this priority**: Requires a new ASR pass (minutes per recording) and carries a small risk of attenuating very quiet speech, so it must not be the default.

**Independent Test**: `a-wizard options PROJECT --audio-cleanup` on a completed mixdown project marks mixdown and downstream stale; the next run writes a gated `tracks/mix.wav`; with defaults, stage signatures of existing projects are unchanged.

**Acceptance Scenarios**:

1. **Given** default options, **When** an existing project is reconciled, **Then** mixdown and transcription signatures are identical to the previous release.
2. **Given** `--hallucination-silence 2`, **When** the project is transcribed, **Then** the ASR adapter receives `hallucination_silence_threshold=2.0` and transcription stages are stale until redone.
3. **Given** `a-wizard options PROJECT` without flags, **When** it runs, **Then** current values are printed and nothing changes.

### Edge Cases

- One active track only: attribution still drops isolated hallucinations; no crosstalk analysis.
- Tracks of slightly different length: shorter profiles are padded with silence.
- A track with no detected speech at all: reported with a warning suggesting `skipped`.
- Zero-length or very short ASR words: evaluated on a window of at least 100 ms.
- Sudden noise steps on a microphone: the local floor adapts within about 15 s; words in the transition may still be attributed by energy.
- Completely silent or synthetic inputs: legacy loudest-channel fallback, no drops.
- Diarized words with no overlapping turn: nearest turn by time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Attribution MUST estimate a time-varying noise floor per track from its RMS profile (two-pass rolling estimate with an absolute minimum for digital silence) and a typical speech level per track.
- **FR-002**: A track MUST be a candidate for a word only if its word-window level is at least 9.5 dB above its local noise floor.
- **FR-003**: With one candidate the word MUST go to that track; with several, candidates below 18 dB over their floor are dropped when another candidate reaches 18 dB, then the track with the highest level relative to its own speech level wins unless the top two are within a 1.25× ratio, in which case the word is resolved by context.
- **FR-004**: Words without a candidate or with a tie MUST take the channel of the nearest confidently attributed word in time (restricted to tied candidates when applicable). If no word in the recording is confidently attributed, the legacy loudest-channel rule MUST be used.
- **FR-005**: Channel islands of at most 2 words and 700 ms between words of one other channel MUST be reassigned to that channel unless every island word is confident and at least 3× louder (relative) than the surrounding channel.
- **FR-006**: The system MUST detect crosstalk between every ordered pair of active tracks (positive envelope correlation ≥ 0.3 at a lag of 0–1000 ms) and compensate it in the power domain before the activity decision; detected links MUST be reported.
- **FR-007**: Runs of words whose best track is below 6 dB over its floor and that are at least 2 s away from any word with speech evidence MUST be excluded from the dialog, flagged `dropped` in `mix.segments.json`, and counted; nothing is dropped in fallback mode.
- **FR-008**: Diarizer speaker ids MUST be normalized to `SPEAKER_NN` in all adapters and track-scoped to `SPEAKER_T{track}D{n}`, including legacy `SPEAKER_S{n}` labels.
- **FR-009**: Diarized words MUST be assigned to the turn with maximum overlap; words overlapping several turns without a ≥ 60 % majority MUST follow the nearest same-track neighbor's speaker when it is among the overlapped turns.
- **FR-010**: The attribute stage signature MUST include an attribution algorithm version and its parameters, so existing projects redo attribute, merge, and minimize without redoing ASR.
- **FR-011**: Diarization turns MUST be cached per track keyed by WAV SHA-256, adapter id, and cache version, written atomically; mock adapters MUST bypass the cache.
- **FR-012**: `meta/attribution.json` MUST include per-track noise floor, speech level, active ratio, word and segment counts, crosstalk links, counts of context-resolved, smoothed, and dropped words, and human-readable warnings; it MUST NOT contain transcript text.
- **FR-013**: In `per_track` mode, transcription MUST also store per-track words, and merge MUST filter each track's words with the same activity model (hallucination, crosstalk, domination rules), falling back to segment-level filtering for older projects.
- **FR-014**: Project options `audio_cleanup` (bool) and `hallucination_silence_threshold` (seconds or null) MUST default to off and MUST NOT change any stage signature while off.
- **FR-015**: With `audio_cleanup` on, mixdown MUST attenuate inactive frames of each track (−18 dB, with pre-roll and hangover) and normalize track speech levels (±12 dB) before summing; in `per_track` mode the same processing MUST produce a clean per-track WAV used for ASR only.
- **FR-016**: `a-wizard options TARGET` MUST print current options, and with `--audio-cleanup/--no-audio-cleanup` or `--hallucination-silence SECONDS/--no-hallucination-silence` MUST update them under the project lock and invalidate only dependent stages.
- **FR-017**: Automated tests MUST use only synthetic signals and mock adapters.

### Key Entities

- **Track activity**: per-track RMS profile (optionally crosstalk-compensated), local noise floor, speech level.
- **Crosstalk link**: source track, destination track, lag, gain, correlation.
- **Word evidence**: per track SNR over floor, relative level; decision state (confident, ambiguous, silent), resolution (energy, context, smoothed, fallback), dropped flag.
- **Attribution report**: aggregated counts, per-track diagnostics, links, warnings.
- **Project options**: `audio_cleanup`, `hallucination_silence_threshold` in transcription defaults.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the two reference recordings, plain-speaker lines drop from 311 and 85 to fewer than 30 and 12 while every word with clear microphone speech stays on the plain speaker.
- **SC-002**: Across all available two-track recordings, no word with clear desktop speech and a silent microphone is attributed to the microphone, and at least 99 % of clear microphone words are attributed to the microphone.
- **SC-003**: Synthetic four-room fixture with crosstalk and gain differences attributes at least 95 % of words to the correct room.
- **SC-004**: Re-attributing an existing 1.5 h recording takes under 30 s after diarization is cached (no ASR).
- **SC-005**: Full local quality gate passes with coverage ≥ 70 %.

## Assumptions

- Tracks inside one video are time-aligned (same container); automatic alignment of independently recorded files is out of scope.
- 20 ms RMS profiles (existing energy cache) are sufficient; no spectral features are added.
- Crosstalk is approximately a delayed, attenuated copy of the source envelope with a stable lag over the recording.
- Opt-in cleanup changes ASR input only; attribution always uses the original tracks.
- Schema version stays 2; new manifest keys are optional.
