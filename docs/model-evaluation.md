# Local voice-cloning engine evaluation

Updated 2026-08-15. This document deliberately separates source review from local measurement.

## Current decision status

No final quality or fast engine has been selected empirically on this checkout. Qwen3-TTS remains the only implemented adapter because it was inherited from the baseline and is needed to stabilize behavior before comparison. The prior document's selection language was stronger than its surviving evidence: the checkout contains no model environment, benchmark JSON, quality samples, authorized reference, or reproducible listening scores. Those claims are not treated as current proof.

The next valid decision requires real runs from `scripts/benchmark_engine.py`, the checked-in `quality_tests/golden_voice_suite.json`, saved audio under `quality_samples/`, and human listening ratings. Producing a WAV is not a quality decision.

## Candidate shortlist from current primary-source review

| Candidate | Documented reason to measure | Principal question | Local result |
|---|---|---|---|
| Qwen3-TTS Base 0.6B / 1.7B | Official reference-audio plus transcript cloning, reusable clone prompt, multilingual models, Apache-2.0 repository. | Does identity and long-form stability justify its load/latency on the target hardware? | Not run in this checkout. |
| Chatterbox Standard | English zero-shot cloning with CFG/exaggeration-style controls. | Does it outperform Qwen on identity and expressive delivery without instability? | Not run. |
| Chatterbox Turbo 350M | Official project positions it for low-latency English, with `[laugh]` and related documented paralinguistic tags. | Is short-response quality and identity strong enough for FAST mode? | Not run. |
| Chatterbox Nano 110M | Official project describes CPU-oriented operation. | Is the quality/identity trade-off acceptable on a Windows CPU-only system? | Not run. |
| Chatterbox Multilingual V3 500M | Official project reports 23+ languages, improved similarity, fewer hallucinations, and natural conversational speech. | Are cross-language identity and memory costs better than Qwen? | Not run. |
| F5-TTS v1 Base | Mature reference-audio workflow and published deployment/RTF information. | Does measured quality offset weight-license constraints and integration complexity? | Not run. |
| Fish Speech S2 | Official technical report describes expressive multilingual streaming with published RTF and sub-100ms first audio. | Do local weights, license, Windows install, VRAM, and actual cloning quality fit this product? | Not run. |

Source claims are not benchmark results. See [licensing.md](licensing.md) and official sources: [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), [Chatterbox](https://github.com/resemble-ai/chatterbox), [F5-TTS](https://github.com/SWivid/F5-TTS), [Fish Speech](https://github.com/fishaudio/fish-speech), and the [Fish Audio S2 technical report](https://arxiv.org/abs/2603.08823).

## Required evaluation protocol

1. Pin engine package, repository commit, model revision, torch build, device, driver, FFmpeg version, and OS.
2. Use the same authorized reference set and exact transcripts. Preserve originals.
3. Run every golden case at least three seeded repetitions where seed control exists.
4. Run cold load, warm generation, 10-word, 30-word, 100-word, and 500-word cases.
5. Record model load, completed-file first-audio latency (or true streamed latency), total generation time, audio duration, RTF, RAM delta, peak VRAM, failure, artifact, and hallucination counts.
6. Run local ASR WER and speaker-embedding similarity only as supporting metrics.
7. Conduct blind listening ratings for speaker similarity, naturalness, emotion, pronunciation, and overall quality.
8. Retain one quality engine and one fast engine only if each has a measured advantage. Remove adapters that do not.

## Control mapping for the current adapter

Qwen's current adapter truthfully reports language and post-generation pitch-preserving speed. It reports no temperature, seed, emotion, style, paralinguistic tags, or true streaming. The UI must render from this capability response. Future adapters must document parameter-to-control mappings rather than borrowing product names from another service.

## Hardware recorded for this audit

- Windows host; OS/CPU/RAM CIM queries were denied by the sandbox account.
- `nvidia-smi` was unavailable, so no NVIDIA GPU or VRAM result is confirmed.
- Project virtual environment and model weights were absent.
- FFmpeg 7.1.1 and system Python 3.11.9 were available.

Accordingly, no real inference, listening, or performance conclusion is reported in this audit yet.
