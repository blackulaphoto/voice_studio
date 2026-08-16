# Phase 2 performance references

Qwen3-TTS Base does not expose instruction-driven emotion for voice cloning. Athena Voice
Studio therefore provides experimental built-in delivery profiles using controls the installed
engine genuinely supports: sampling temperature, top-k/top-p, repetition penalty, sub-talker
sampling, and pitch-preserving pace. They require no additional voice upload. Their emotional
names remain experimental until same-text listening proves a meaningful difference.

## First acceptance gate: Warm

Use the existing Golden Voice and generate this exact line twice, first with Original and then
with Warm:

> Brandon, come here for a second. I need to tell you something.

In the Studio:

1. Open **Synthesize** and select the Golden Voice.
2. Select **Original delivery** and generate the acceptance sentence in Quality mode.
3. Select **Warm · experimental** and generate the same sentence again.
4. Compare the two takes using the Compare workspace.
   delivery using the Compare workspace.

## Planned preset set

Neutral, Warm, Playful, Serious, Soft, Excited, Concerned, Firm, Intimate, and Tired are the
allowed names. None requires another upload. The first Warm result must preserve speaker identity
and create a meaningful delivery difference before the remaining profiles are accepted.

Generation history persists the selected profile, its exact supported parameters, effective
pace, and reference source. Optional performance-specific recordings remain an advanced backend
capability, not a normal-use requirement.

## Generated listening suite

All presets use the same twelve-word acceptance sentence and the existing Golden Voice in
Quality mode. Timing proves that the profiles affected generation and/or pacing, but does not by
itself prove that the emotional name is perceptually correct.

| Preset | Generation (s) | Audio (s) | RTF | Status before listening |
|---|---:|---:|---:|---|
| Neutral | 75.198 | 3.92 | 19.18 | Generated |
| Warm | 235.710 | 10.49 | 22.47 | User approved |
| Playful | 70.874 | 2.91 | 24.36 | Generated; inspect for rushing |
| Serious | 115.542 | 8.93 | 12.94 | Generated |
| Soft | 79.059 | 4.34 | 18.22 | Generated |
| Excited | 66.531 | 2.58 | 25.79 | Generated; inspect for rushing |
| Concerned | 106.422 | 3.55 | 29.98 | Generated with safe fallback |
| Firm | 81.949 | 3.82 | 21.45 | Generated |
| Intimate | 97.921 | 3.63 | 26.98 | Generated |
| Tired | 182.263 | 11.29 | 16.14 | Generated; inspect long delivery |

Two earlier Concerned sampling profiles exceeded practical latency limits on the short sentence
and were terminated. The accepted candidate uses Golden sampling defaults plus a 0.92 pace
adjustment. This preserves a bounded, real change without claiming unstable sampling as emotion.

The local, resumable harness is `scripts/benchmark_phase2.py`. Its private generation IDs and
exact local results are stored under the gitignored `quality_samples/phase_2/` directory.
