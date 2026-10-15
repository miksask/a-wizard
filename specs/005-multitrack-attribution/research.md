# Research: Multitrack Attribution

All measurements below were taken offline on 15 local OBS recordings (≈ 9 h, every one `0:diarized desktop` + `1:plain microphone`) using their cached energy profiles, `mix.raw.json`, and diarization turns. No recording or transcript is committed.

## 1. Root cause of plain-speaker fragments

**Finding**: Desktop capture is near digital silence between phrases (RMS p10 ≈ 8–10), the microphone never is (p10 ≈ 100–280, locally up to ~900). Words attributed to the microphone had a median duration of 520–540 ms (typical words 140–240 ms): Whisper stretches phrase-edge words into pauses, so the desktop window average collapses while the microphone stays at its noise level. Ratios were far above `ambiguity_ratio=1.15`, so the guard never fired. A simulation of the old rule reproduced the exact plain-speaker line counts of the reference recordings (311 and 85).

**Decision**: Gate tracks by level over their own noise floor before comparing them.

## 2. Noise-floor estimator

Compared on all recordings (clear-mic words = microphone ≥ 8× its p10 and desktop < 60; clear-desktop words = desktop ≥ 300 and microphone < 2× its p10):

| Estimator | Clear-mic words active | Clear-desktop words lost | Plain lines, Routines-Sync |
|---|---|---|---|
| 30 s blocks, p20 | 99.5 % | 0.51 % | 19 |
| rolling ±15 s, p10 | 99.6 % | 0.01 % | 70 |
| two-pass rolling ±15 s (p10 envelope → median of frames within +6 dB) | 99.5 % | 0.00 % | 22 |

**Decision**: Two-pass rolling estimate, ±15 s window, 0.5 s step, absolute minimum 30 RMS (≈ −61 dBFS). A low percentile alone sits on the lower tail of non-stationary microphone noise, which lets noise exceed the gate; the median of frames near that envelope is the typical noise level and still ignores speech. Cost ≈ 1 s per 1.5 h track.

## 3. Gate and word statistic

**Decision**: 9.5 dB (≈ ×3 amplitude) over floor; word level = 75th percentile of frames in a window widened to ≥ 100 ms. The percentile keeps stretched words from being diluted by the silence they spill into; the minimum window gives zero-length words more than one 20 ms frame.

## 4. Choosing between several active tracks

**Finding**: 2–10 % of words had both tracks active (overlaps, backchannels). Comparing SNR over floor disagreed with raw loudness in up to 30 % of those words because a digital track's tiny floor inflates its SNR (e.g., desktop 47.5 dB vs microphone 33.9 dB while the microphone was 1.5× louder). Activity of the two tracks was negatively correlated at every lag (−0.2 … −0.3), so there is no echo of the local voice in desktop audio.

**Decision**: Compare `(level − floor) / (speech_level − median floor)` per track. This equals raw comparison when gains match, is immune to floor inflation, and stays correct when room microphones have different gains (raw loudness would pick a hot microphone's crosstalk over a quiet microphone's direct speech). Near-ties (< 1.25×) go to context.

**Alternatives considered**: raw RMS (fails on gain differences in multi-room), SNR (fails on digital floors).

**Refinement (tiered candidates)**: A microphone that barely clears the gate (9–12 dB, loudspeaker bleed or room noise) under strong desktop speech got an inflated relative level, because a track with little speech has its speech level estimated from sparse bursts. Across 1540 both-active words: weak-mic-under-strong-desktop words attributed to the microphone — relative level 93/479, relative level with a 25 dB minimum speech level 9/479, tiered rule 0/479; loud microphone speech louder than desktop kept on the microphone — 493/493, 489/493, 493/493. **Decision**: when any candidate is ≥ 18 dB over its floor, candidates below 18 dB are dropped before comparing relative levels.

## 5. Crosstalk

**Decision**: For each ordered pair (A, B) correlate the dB-above-floor envelopes of A(t) and B(t+lag) for lags 0–1000 ms. Declare A→B when the peak is ≥ 0.3 and ≥ 0.1 above the median over lags. Gain = median of `sqrt(max(P_B − F_B², 0)) / E_A` over frames where A is ≥ 20 dB over its floor. Compensate `P_B ← max(P_B − 2·gain²·ref_A², F_B²)` with `ref_A` = A delayed by the lag and max-filtered over ±40 ms. Real recordings peaked at ≤ +0.07, so no false links were detected.

**Alternatives considered**: audio-domain echo cancellation (heavy, needs sample-accurate alignment), text-based duplicate detection (only possible per-track).

## 6. Hallucinations in silence

**Decision**: Drop runs of words whose best track is below 6 dB over floor and that are ≥ 2 s from any word with ≥ 6 dB evidence. On the corpus this removed 0–4 words per recording ("Продолжение следует...", a long "ersterster…" run, "Thank you.", "Um...", single "yeah"/"Так." at 2.8–4.8 dB, i.e. at noise level). Words between 6 and 9.5 dB are never dropped. Hallucinations adjacent to real speech are attached to the neighbor instead of forming their own line.

## 7. Labels

**Finding**: FluidAudio returns `S1…S10`; the adapter produced `SPEAKER_S1`, which `track_scoped_speaker` did not recognize, so labels were neither track-scoped nor shortened (`[SPEAKER_S3]` vs `[ST0D3]`). speakrs RTTM labels had the same issue.

**Decision**: One `normalize_diar_label` used by all adapters; `track_scoped_speaker` accepts any `SPEAKER_<letters><digits>` legacy form.

## 8. Freshness

**Decision**: `ATTRIBUTION_ALGORITHM_VERSION` plus the parameter set are part of the attribute signature (and of the per-track merge signature). New options enter signatures only when enabled, so existing projects never redo ASR because of this feature. Diarization gets a cache with a sidecar like the energy cache; without it every re-attribution would re-run the diarizer (≈ 20 s per 1.5 h track).

## 9. Opt-in cleanup

**Decision**: Gains per 20 ms frame from the (compensated) activity model with a lower 6 dB gate, 120 ms pre-roll, 400 ms hangover, −18 dB when closed, and per-track level normalization toward −20 dBFS clamped to ±12 dB; mixing streams 30 s chunks with numpy. Off by default because quiet speech in a very noisy microphone can sit near the gate and the change requires a new ASR pass. `hallucination_silence_threshold` is supported by mlx-whisper ≥ 0.4 and faster-whisper ≥ 1.0 when word timestamps are on.
