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
