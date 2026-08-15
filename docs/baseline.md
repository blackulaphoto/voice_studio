# Golden baseline — Qwen3 voice `hillsry`

Captured 2026-08-15 before performance optimization. This is the immutable QUALITY comparison point. The private, complete machine-readable record is stored locally at `quality_samples/golden_baseline/baseline.json`; that directory is gitignored because it contains the exact reference transcript, reference hashes, and voice audio.

## Frozen configuration

| Field | Baseline |
|---|---|
| Engine | `qwen3` |
| Model | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` |
| Qwen package | `qwen-tts 0.1.1` |
| Voice profile | `hillsry` |
| Reference | One authorized 55.59-second MP3; processed reference 54.47 seconds |
| Processed reference hash | `2a9087b7fa8d821e957e2c524616badeaa558c9a49b8532d4779afdfe496fc1d` |
| Transcript | Exact text retained only in the private local baseline JSON and voice database |
| Language | English |
| Mode | Quality |
| Speed | `1.0` |
| Performance | None; Qwen adapter does not claim a style/emotion control |
| Seed | Unsupported / none |
| Engine settings | None |
| Device | CPU — AMD Ryzen 7 5825U |
| Dtype | FP32 |
| Runtime | Python 3.12.7, PyTorch 2.13.0+cpu, torchaudio 2.11.0+cpu |
| System RAM | 13.84 GB |
| Reference processing | 24 kHz mono PCM s16le; outer-edge silence trimming at -60 dB; internal pauses preserved; loudnorm `I=-18:TP=-2:LRA=7` |
| Post-processing | No speed transform at 1.0; canonical WAV; MP3 via libmp3lame quality 2 |

The original known-good cloned sentence was listened to by the user and judged correct. The new golden-set clips require listening approval before Phase 1 may replace or alter any QUALITY behavior.

## Model load baseline

| Scenario | Seconds | Memory note |
|---|---:|---|
| First install + download + load | 188.65 | Includes downloading the 2.34 GB local model cache |
| Cached offline load, uncontended | 22.40 | Separate process, network explicitly disabled |
| Cached offline load while live backend already held model | 140.96 | 3,172 MB process RSS increase; paging/memory pressure makes a second simultaneous model undesirable |

The application must keep one model resident and must not preload a second worker on this hardware.

## Warm real-inference baseline

All cases used the same resident model, voice, transcript conditioning, language, speed, and settings. RTF is generation seconds divided by audio seconds; lower is faster.

| Sample | Words | Generation (s) | Audio (s) | RTF | Backend RSS after (MB) |
|---|---:|---:|---:|---:|---:|
| Neutral | 28 | 134.080 | 9.20 | 14.57 | 3,070 |
| Warm | 25 | 93.531 | 6.80 | 13.75 | 3,018 |
| Playful | 22 | 105.847 | 7.92 | 13.36 | 3,083 |
| Serious | 23 | 135.414 | 11.52 | 11.75 | 3,186 |
| Intimate content | 21 | 107.549 | 7.76 | 13.86 | 3,128 |
| Sexy content | 21 | 99.456 | 6.88 | 14.46 | 2,680 |
| Short conversational | 10 | 68.714 | 3.36 | 20.45 | 3,044 |
| Long paragraph | 101 | 337.140 | 34.40 | 9.80 | 3,236 |
| Numbers and dates | 30 | 140.652 | 11.76 | 11.96 | 3,230 |

## Golden artifacts

Local-only WAV and MP3 pairs are stored under `quality_samples/golden_baseline/` for neutral, warm, playful, serious, intimate, sexy, short conversational, long paragraph, and numbers/dates cases. The capture harness is `scripts/capture_golden_baseline.py` and safely resumes completed cases.

## Regression gate

- QUALITY must retain the frozen engine/model/reference/transcript/settings unless a separately reviewed change improves or preserves voice identity.
- Every optimization must generate matching comparison text and be listened to against these files.
- Timing improvements alone cannot replace QUALITY.
- Changes that reduce identity or perceptual quality must be fixed, restricted to FAST, or reverted.

## Phase 0 status

- Static checks: passed.
- Unit tests: 15 passed; one opt-in real-inference test skipped by default.
- Frontend build: passed with Vite 8.2.1.
- Backend/API smoke: passed; health reported the CPU Qwen model resident and UI returned HTTP 200.
- Real synthesis: passed for all nine categories.
- Manual listening: original known-good output passed; nine new baseline clips await user approval.
