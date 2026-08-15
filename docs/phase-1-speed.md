# Phase 1 speed investigation

Measured locally on 2026-08-15 with the Golden Voice, Qwen3-TTS Base 0.6B,
PyTorch CPU FP32, and the same ten-word sentence used by the Golden Baseline.

## Instrumented pipeline

Every new generation now records phase timings in its persisted `settings.phase_timings`:

- model loading;
- cached voice-prompt lookup or construction;
- Qwen inference plus codec decoding;
- WAV writing;
- speed post-processing;
- MP3 export;
- duration probing;
- total request time.

The model and voice prompt remain resident and are reused. QUALITY retains the exact Qwen
generation defaults used by the Golden Baseline. The experimental FAST path changes only
Qwen's documented `non_streaming_mode` argument to `true`, avoiding its simulated streaming
text-input path.

## Results

| Run | Mode | Load (s) | Prompt (s) | Inference + decode (s) | Total (s) | Audio (s) | RTF |
|---|---|---:|---:|---:|---:|---:|---:|
| Cold | Quality | 13.602 | 8.033 | 112.940 | 134.992 | 8.32 | 16.23 |
| Warm | Quality | 0.000 | 0.000 | 82.207 | 82.502 | 4.56 | 18.09 |
| Warm | Fast | 0.000 | 0.000 | 77.000 | 77.281 | 3.68 | 21.00 |

Audio conversion and probing were under 0.4 seconds. Warm inference and codec decoding are
more than 99% of request time, so frontend, database, WAV writing, MP3 export, and reference
disk reads are not meaningful speed bottlenecks after warm-up.

## Decision

FAST reduced warm wall time by 5.221 seconds (6.3%) in this pair, but generated shorter audio
and had a worse RTF. This is not a material or quality-approved improvement. FAST remains
visibly marked Experimental, QUALITY remains the default, and no larger benchmark or default
promotion is justified until the paired clips pass human identity and naturalness listening.

The paired takes are persisted in the Studio as:

- `Phase 1 - warm 10 words - QUALITY`
- `Phase 1 - warm 10 words - FAST`

Use the Compare workspace for the listening gate. If FAST audibly degrades the Golden Voice,
remove or replace this experiment rather than rationalizing the regression.

## Human listening result

The user judged the FAST take generally good and still recognizable, but reported that its
pacing sometimes runs over itself and does not follow normal conversational cadence as well as
QUALITY. Because the paired takes used identical text and punctuation, punctuation alone does
not explain the difference. FAST is therefore accepted only as a usable experimental option,
not as a replacement for QUALITY and not as the default.
