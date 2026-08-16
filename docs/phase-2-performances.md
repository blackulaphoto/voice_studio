# Phase 2 performance references

Qwen3-TTS Base does not expose instruction-driven emotion for voice cloning. Athena Voice
Studio therefore separates voice identity from performance using real, authorized reference
recordings by the same speaker. A preset is selectable only after its audio and exact transcript
have been saved; the UI does not show decorative emotion options.

## First acceptance gate: Warm

Start with one Warm reference before recording the full set. Record the same speaker who owns
the Golden Voice saying this exact line:

> Brandon, come here for a second. I need to tell you something.

Delivery guidance: speak warmly and naturally, as if reassuring someone nearby. Do not whisper,
act theatrically, change accent, or imitate another person. A clean 5–15 second recording is
recommended. Keep only the speaker's voice, with no music or other people.

In the Studio:

1. Open **Synthesize** and select the Golden Voice.
2. Choose **+ Performance**.
3. Select **Warm**.
4. Paste the exact transcript above.
5. Upload the Warm recording and confirm authorization.
6. Save it, then select **Warm · recorded reference** under Performance.
7. Generate the common acceptance sentence in Quality mode and compare it with Original
   delivery using the Compare workspace.

## Planned preset set

Neutral, Warm, Playful, Serious, Soft, Excited, Concerned, Firm, Intimate, and Tired are the
allowed names. Each requires its own real recording and transcript. The first Warm result must
preserve speaker identity and create a meaningful delivery difference before the remaining nine
are recorded or Phase 2 is considered working.

Performance source audio and processed references remain under local ignored `storage/` paths.
Generation history persists the selected performance name and the exact reference source used.
