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
| Warm 30 words | Quality | 0.000 | 0.000 | 124.837 | 125.204 | 10.32 | 12.13 |
| Warm 30 words | Fast | 0.000 | 0.000 | 125.294 | 125.598 | 10.48 | 11.98 |
| Warm 101 words | Quality | 0.000 | 0.000 | 298.810 | 299.184 | 31.84 | 9.40 |
| Warm 101 words | Fast | 0.000 | 0.000 | 328.598 | 328.979 | 33.60 | 9.79 |

Audio conversion and probing were under 0.4 seconds. Warm inference and codec decoding are
more than 99% of request time, so frontend, database, WAV writing, MP3 export, and reference
disk reads are not meaningful speed bottlenecks after warm-up.

## Decision

The initial short pair reduced warm wall time by 5.221 seconds (6.3%), but generated shorter
audio and had a worse RTF. The user subsequently approved both short clips for identity and
naturalness, allowing the required larger timing suite to proceed without promoting the mode.

The completed larger benchmark rejects this switch as a general speed optimization. At 30
words it was 0.394 seconds slower (effectively tied), and at 101 words it was 29.795 seconds
slower (10.0%). The UI therefore calls it an Alternate path and explicitly states that it is
not faster on this CPU. Internally its historical mode value remains `fast` so existing records
can still be restored exactly. A future mode must demonstrate a real improvement before it is
presented as FAST.

The paired takes are persisted in the Studio as:

- `Phase 1 - warm 10 words - QUALITY`
- `Phase 1 - warm 10 words - FAST`

Use the Compare workspace for the listening gate. If FAST audibly degrades the Golden Voice,
remove or replace this experiment rather than rationalizing the regression.

## Human listening result

The user listened directly to the matched QUALITY and FAST takes and judged both to be great,
with no pacing or voice-quality problem in either comparison clip. An earlier pacing concern
was traced to a separate user-created synthesis and does not apply to this paired benchmark.
The alternate path therefore passes this short-sentence human identity and naturalness gate.
QUALITY remains the default, and the completed timing suite shows the alternate path is not a
general performance improvement on this CPU. The 30-word and 101-word pairs still require the
same human listening check before Phase 1's audio-quality gate is closed.
