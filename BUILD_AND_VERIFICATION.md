# Build and verification ledger

Updated 2026-08-15. This ledger reports only evidence produced from the current checkout.

## Baseline audit

- The delivered folder had no Git metadata. Baseline commit `4eb3fe8` was created locally; the publishable branch is `main`.
- The project had no `.venv`, no installed frontend packages, no automated tests, no checked-in benchmark data, and no quality samples.
- Initial frontend build failed because Vite was not installed.
- FFmpeg 7.1.1 and ffprobe were available. System Python was 3.11.9 and Node was 22.14.0.
- Host inspection confirmed Windows 11, AMD Ryzen 7 5825U, 13.84 GB RAM, AMD integrated graphics, and no usable CUDA runtime. The verified runtime therefore uses official CPU PyTorch.

## Defects reproduced or confirmed by inspection

- Default storage resolved to the parent of the project despite documentation showing project-local `storage/`.
- SQLite foreign keys were enabled only in the schema script, not on each connection.
- Voice deletion cascaded rows but left generation files/directories behind.
- Multi-file references used a concat manifest with fragile quoting/escaping.
- Generation history did not retain enough state for complete regeneration.
- Qwen selected BF16 for all CPUs and all CUDA devices without capability checks.
- The API had no engine/model capability endpoint, voice detail/update route, or generation delete route.

## Current verification

| Category | Result | Scope |
|---|---|---|
| STATIC CHECK | Passed | `python -m compileall -q backend scripts` after current backend changes. |
| UNIT TEST | Passed | 15 tests plus one separately marked real-inference test skipped by default. Coverage includes mixed audio, internal-pause preservation, database lifecycle, dtype selection, offline model-cache resolution, normalization, pronunciation, and segmentation. |
| FRONTEND DEPENDENCIES | Passed | `npm install` completed with zero reported vulnerabilities. |
| FRONTEND BUILD | Passed | Vite 8.2.1 transformed 16 modules and produced the production bundle. |
| BACKEND API SMOKE | Passed | TestClient startup plus health, engines, models, voices, and generations all returned HTTP 200. |
| UI DESIGN EVALUATION | Passed with fixes applied | Desktop/tablet/mobile review passed; mobile overflow/navigation and offline error-state priorities were subsequently corrected. Cross-provider evaluation was unavailable, so a separate OpenAI evaluator agent was used. |
| INTEGRATION TEST | Passed manually | An authorized 55.59-second MP3 created the persisted `hillsry` profile and synthesized a new sentence through `POST /api/tts`. The opt-in pytest integration test remains skipped by default. |
| REAL MODEL INFERENCE | Passed | Qwen3-TTS 0.6B loaded from the project-local cache with Hugging Face and Transformers explicitly offline, then produced WAV and MP3 output. |
| MANUAL LISTENING TEST | Passed by user | The user listened to the newly synthesized clone and confirmed it sounded correct. |
| PERFORMANCE BENCHMARK | Partial | Cold CPU model load: 188.65 s. Cached offline load: 22.4 s. A 3.28-second short sentence generated in 159.495 s (RTF 48.63). Full golden-suite benchmark remains pending. |
| WINDOWS SETUP | Passed on target host | Dedicated Python 3.12.7 `.venv`, CPU PyTorch 2.13.0, Qwen3-TTS 0.1.1, FFmpeg 7.1.1, portable SoX 14.4.2, npm frontend, backend and frontend localhost services verified. |

## Implemented in the current branch

- Canonical project-local data root independent of current working directory.
- Per-connection SQLite foreign keys and migration-safe metadata columns.
- Explicit cascade-delete policy with associated generation-file cleanup.
- Mixed-format FFmpeg filter-graph processing without concat manifests.
- Local reference analysis metadata and actionable quality rating.
- Engine interface and truthful Qwen capability reporting.
- Hardware-safe FP32/FP16/BF16 selection and explicit unload/cache cleanup.
- Complete generation request persistence for regeneration.
- English text normalization, local pronunciation overrides, and long-text segmentation primitives.
- Versioned golden voice test corpus and real-inference benchmark harness.
- Separate engine/model licensing review.

## Not yet verified or complete

No model has won the bake-off. Chatterbox, F5-TTS, and Fish Speech are research candidates only. True streaming, cancellation during model inference, multi-reference selection by performance, ASR WER, speaker similarity scoring, batch synthesis, persisted A/B ratings, model downloads, and real listening quality remain incomplete until implemented and measured. Do not represent this branch as ElevenLabs-class or production-complete yet.
