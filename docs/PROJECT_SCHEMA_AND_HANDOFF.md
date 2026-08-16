# Athena Voice Studio — project schema and Claude Code handoff

Last updated: 2026-08-15. This is the authoritative continuation guide for the standalone
Athena Voice Studio repository.

## Non-negotiable scope

- Project root: `C:\Users\brandon\Downloads\Athena-Voice-Studio\athena-voice-studio`
- Remote: `https://github.com/blackulaphoto/voice_studio.git`
- **Do not modify Athena, Athena source, or any Athena virtual environment.**
- Use only this project's `.venv`; never install packages globally.
- Preserve the Golden Voice QUALITY path. Do not trade speaker identity for speed or features.
- Never claim an emotion/preset works until the user listens to same-text output.
- Private audio, transcripts, generations, model weights, and benchmark JSON stay local.

## Current checkpoint

- Branch: `main`
- Local HEAD when this document was written: `d37695b`
- Local branch is three commits ahead of `origin/main`:
  - `59824d9 add real performance reference conditioning`
  - `601233f remove performance upload requirement`
  - `d37695b generate phase two performance suite`
- Phase 0 Golden Baseline: complete and user-approved.
- Phase 1 speed investigation: complete. The alternate Qwen path is not generally faster on CPU.
- Phase 2 performance presets: ten candidates generated; Warm approved; remaining listening/tuning
  is in progress.

## Runtime

| Component | Current value |
|---|---|
| OS | Windows |
| Python | 3.12.7 |
| Virtual environment | `<project>\.venv` |
| Backend | FastAPI 0.141.1 + Uvicorn |
| Frontend | React + Vite |
| PyTorch | 2.13.0+cpu |
| Qwen package | qwen-tts 0.1.1 |
| Model | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` |
| Device | CPU, FP32; no usable CUDA device detected |
| FFmpeg | 7.1.1 essentials build; ffmpeg and ffprobe available |
| SoX | Project-local under `tools/sox/sox-14.4.2` |
| UI | `http://127.0.0.1:5173` |
| API | `http://127.0.0.1:8000` |

Start normally with `start.bat`. Backend development command from `backend/` is
`..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
Frontend development command from `frontend/` is `npm.cmd run dev`.

## Repository layout

```text
athena-voice-studio/
  backend/
    app/
      main.py                 FastAPI routes and synthesis orchestration
      config.py               Paths, model ID, CORS, upload limit
      db.py                   SQLite schema, migrations, repositories
      schemas.py              Pydantic API contracts
      audio/processing.py     ffprobe analysis, reference prep, atempo, MP3 export
      text/normalization.py   spoken-text normalization and overrides
      text/segmentation.py    early long-form segmentation support
      tts/base.py             engine interface and capability schema
      tts/qwen_engine.py      Qwen loading, hardware, prompt cache, inference timing
    tests/                    unit tests plus opt-in real-Qwen integration test
    requirements.txt
    requirements-dev.txt
  frontend/
    src/App.jsx               entire current React application and API client
    src/styles.css            entire visual system and responsive rules
    src/main.jsx
  scripts/
    capture_golden_baseline.py
    benchmark_phase1.py
    benchmark_phase2.py
    benchmark_engine.py
    verify_inference.py
  docs/
    baseline.md
    phase-1-speed.md
    phase-2-performances.md
    PROJECT_SCHEMA_AND_HANDOFF.md
  quality_samples/            private/local; audio and benchmark metadata ignored
  storage/                    private/local SQLite, voices, generations, model cache
  setup_windows.ps1
  setup.bat
  start.bat
```

## Configuration and storage

`backend/app/config.py` defines `Settings`:

- `storage_root`: defaults to `<project>/storage`
- `qwen_model_id`: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`
- `force_device`: optional; otherwise CUDA only when PyTorch reports it usable
- `cors_origins`: localhost/127.0.0.1 Vite origins
- `max_upload_mb`: 250 per source

Storage layout:

```text
storage/
  athena_voice.db
  model-cache/hub/models--Qwen--Qwen3-TTS-12Hz-0.6B-Base/snapshots/<revision>/
  samples/<voice_id>/sample-N.<ext>
  voices/<voice_id>/reference.wav
  voices/<voice_id>/performances/<preset>/source.<ext>       optional advanced path
  voices/<voice_id>/performances/<preset>/reference.wav     optional advanced path
  generations/<generation_id>/speech.wav
  generations/<generation_id>/speech.mp3
```

`.gitignore` excludes `.venv`, `storage`, frontend dependencies/build, model/download artifacts,
audio formats, Golden Baseline, and Phase 1/2 private benchmark metadata.

## SQLite schema

Database initialization and additive column migration are in `backend/app/db.py`.

### `voices`

| Column | Meaning |
|---|---|
| `id` | slug derived from voice name; primary key |
| `name` | display name |
| `reference_audio_path` | processed 24 kHz mono WAV |
| `original_sample_paths` | JSON list of authorized uploads |
| `reference_text` | exact transcript when supplied |
| `duration_seconds` | processed reference duration |
| `created_at`, `updated_at` | UTC ISO timestamps |
| `engine_id` | normally `qwen3` |
| `model_id` | exact Qwen model |
| `language` | default English |
| `settings_json` | extensible voice settings |

### `generations`

| Column | Meaning |
|---|---|
| `id` | UUID hex primary key |
| `voice_id` | foreign key; cascades with voice |
| `text`, `normalized_text` | original and actual spoken text |
| `language`, `speed` | request controls |
| `style_instruction` | legacy nullable field; unused |
| `model_id`, `engine_id`, `device` | provenance |
| `mode` | `quality` or historical `fast` alternate path |
| `performance` | selected Phase 2 preset |
| `seed` | nullable; Qwen adapter does not advertise seed support |
| `settings_json` | JSON including exact engine values and phase timings |
| `reference_set_json` | JSON source paths used for conditioning |
| `duration_seconds`, `generation_seconds` | output/latency measurements |
| `wav_path`, `mp3_path` | local audio paths |
| `benchmark_label` | visible benchmark/test label |
| `created_at` | UTC ISO timestamp |

`settings_json` currently persists `normalize_text`, requested `speed`,
`performance_parameters`, `effective_speed`, Qwen sampling values, and `phase_timings`.

### `performance_references`

Optional advanced infrastructure retained but hidden from normal UI. Columns: `id`, `voice_id`,
`preset`, processed/original paths, exact `reference_text`, duration, and timestamp. Unique on
`(voice_id, preset)` and cascades with voice. Normal built-in presets do **not** require this.

## HTTP API

All routes are under `/api`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | actual device/model loaded state |
| GET | `/engines`, `/models` | engine and honest capabilities |
| GET | `/voices` | voice list plus device |
| GET/PATCH/DELETE | `/voices/{voice_id}` | voice detail/update/delete |
| POST | `/voices` | authorized multipart voice creation |
| GET | `/voices/{voice_id}/preview` | processed reference WAV |
| GET/POST | `/voices/{voice_id}/performances` | optional advanced references |
| GET | `/voices/{voice_id}/performances/{preset}/preview` | optional reference preview |
| DELETE | `/voices/{voice_id}/performances/{preset}` | optional reference delete |
| POST | `/tts` | synchronous local synthesis and persistence |
| GET | `/generations` | latest 100 generation records |
| GET/PATCH/DELETE | `/generations/{id}` | detail, label update, delete |
| GET | `/generations/{id}/audio` | inline WAV playback |
| GET | `/generations/{id}/download/{wav|mp3}` | downloads |

`GenerationRequest` accepts voice, text, language, speed, mode, engine, performance, optional
seed, normalization flag, pronunciation overrides, engine settings, and benchmark label.

## Synthesis flow

```text
POST /api/tts
  -> validate voice, engine, performance
  -> normalize text
  -> choose base reference or optional performance-specific reference
  -> merge built-in performance settings
  -> Qwen engine lazy-loads one model process
  -> build/reuse cached clone prompt keyed by voice/reference performance
  -> generate_voice_clone(... supported Qwen kwargs ...)
  -> write canonical WAV
  -> FFmpeg atempo for requested speed × preset pace
  -> export MP3
  -> ffprobe duration
  -> persist generation, exact settings, references, and phase timings
  -> return playable/downloadable API record
```

The Qwen model remains resident after first use. Voice prompts remain cached in memory. Complete
local snapshots are loaded with `local_files_only=True`, preventing unnecessary Hugging Face
network probes. Do not run a second model worker on this 14 GB machine; prior testing showed
severe paging/memory pressure.

## Audio pipeline

Voice uploads accept WAV, MP3, M4A, FLAC, OGG, AAC, and WebM. `preprocess_reference`:

1. analyzes each input locally with ffprobe/FFmpeg;
2. combines multiple inputs without fragile concat manifests;
3. converts to 24 kHz, mono, PCM s16le WAV;
4. trims only leading/trailing silence at -60 dB while preserving internal pauses;
5. normalizes conservatively with `loudnorm=I=-18:TP=-2:LRA=7`.

Generated WAV is canonical. MP3 uses libmp3lame quality 2. Speed uses FFmpeg `atempo`, preserving
pitch. The preview for a voice is the processed reference, not evidence that cloning occurred.

## Qwen engine and capabilities

`QwenVoiceCloneEngine` truthfully advertises cloning, multilingual output, and speed. It does not
advertise model-native emotion, style instructions, seed, true streaming, or paralinguistic tags.
Supported sampling kwargs are explicitly allowlisted: temperature, top-k/top-p, repetition
penalty, and corresponding sub-talker controls. Unknown UI settings are not forwarded.

QUALITY passes the Golden Qwen defaults unchanged unless a performance preset is selected.
The historical `fast` mode sets Qwen `non_streaming_mode=True`; full benchmarks showed it is
not generally faster on this CPU, so the UI calls it **Alternate — Not faster on CPU**.

## Built-in performance profiles

Defined in `backend/app/main.py` as `PERFORMANCE_PRESETS`. All use the existing voice—no second
upload. Current exact mappings:

| Preset | Parameters |
|---|---|
| Neutral | Golden sampling defaults; pace 1.00 |
| Warm | temperature .85, top_p .90, subtalker_temperature .85, pace .96 |
| Playful | temperature 1.05, top_k 60, subtalker_temperature 1.05, pace 1.03 |
| Serious | temperature .72, top_p .85, subtalker_temperature .72, pace .94 |
| Soft | temperature .78, top_p .88, subtalker_temperature .76, pace .88 |
| Excited | temperature 1.10, top_k 65, subtalker_temperature 1.10, pace 1.08 |
| Concerned | Golden sampling defaults; pace .92 |
| Firm | temperature .68, top_p .82, repetition_penalty 1.08, subtalker_temperature .68, pace .96 |
| Intimate | temperature .76, top_p .86, repetition_penalty 1.10, subtalker_temperature .74, pace .88 |
| Tired | temperature .82, top_p .90, repetition_penalty 1.10, subtalker_temperature .78, pace .82 |

These are candidates, not scientifically validated emotions. Warm passed user listening. Two
earlier Concerned sampling variants ran away for more than eight minutes on a twelve-word line;
both were terminated and replaced with Golden sampling plus pace only.

## Current Phase 2 listening feedback and required next work

The complete suite is labeled in Generations as
`Phase 2 · <PRESET> · built-in no-upload preset` and uses:

> Brandon, come here for a second. I need to tell you something.

User verdict so far:

- Most presets are acceptable for now.
- Warm works great.
- Serious has an unacceptable approximately four-second gap between “come here for a second”
  and “I need to tell you something.”
- Soft sounds more Intimate than Soft.
- Intimate sounds more Soft than Intimate.
- Soft and Intimate still do not authentically capture how this speaker would sound in those
  moments.

Next engineer should make only narrow changes first:

1. Inspect Serious WAV waveform/silence and confirm whether the gap comes from generated audio
   or post `atempo`. Do not globally strip internal pauses; that would damage intentional timing.
2. Prefer retuning Serious sampling to avoid the long pause. If a post-process is necessary,
   make it preset-specific and cap only pathological internal silence, with a regression test.
3. Swap/rework Soft and Intimate parameters based on the user's perceptual report; names must
   follow what is heard, not the original parameter theory.
4. Regenerate the exact same acceptance sentence for Serious, Soft, and Intimate only.
5. Keep old takes for A/B comparison, label replacements `Phase 2 v2`, and ask the user to judge.
6. Do not regenerate all ten until those three pass.

Because Qwen Base has no semantic emotion instruction, exact personal authenticity may not be
achievable from sampling knobs alone. If targeted retuning plateaus, state that honestly. Optional
same-speaker performance references can improve authenticity but must remain optional—not a gate
for normal synthesis.

## Frontend architecture

The UI is intentionally a single React file plus CSS. `App.jsx` owns voices, generations,
engines, device, selected voice, draft generation settings, current output, notices, and modal
state. It fetches `/voices`, `/generations`, `/health`, and `/engines` on refresh.

Six views:

- Voices: authorized profiles, reference preview, delete.
- Synthesize: voice/engine/mode/language/performance, text, speed, output deck.
- Generations: searchable persisted library, labels, playback, restore/regenerate/delete.
- Compare: real two-take playback; no invented ratings.
- Quality Lab: honest setup/measurement state.
- Settings: hardware, model, capabilities, storage truth.

Performance dropdown always includes Original plus ten experimental built-ins. No performance
upload is required. An old `PerformanceDialog` component and optional CSS/backend endpoints may
still exist as hidden advanced infrastructure; remove them later if desired, but do not expose a
required upload again.

`VITE_API_BASE_URL` remains configurable; default is `http://127.0.0.1:8000/api`. Assets returned
as `/api/...` are resolved against the API origin, not the Vite origin.

## Baselines and measured evidence

Read these before optimizing:

- `docs/baseline.md`: immutable Golden QUALITY config and timings.
- `docs/phase-1-speed.md`: instrumentation and rejected general FAST claim.
- `docs/phase-2-performances.md`: current preset parameters, timings, failures, and suite.
- `quality_samples/golden_baseline/`: private approved audio/metadata.
- `quality_samples/phase_1/`, `quality_samples/phase_2/`: private resumable results.

Phase timings are stored per generation under `settings.phase_timings`: model load, voice prompt,
inference+decode, WAV write, post-speed, MP3 export, duration probe, and request total. Warm runs
show inference/codec decoding consumes more than 99% of warm request time; frontend/database and
audio file work are not meaningful speed bottlenecks.

## Verification commands

From project root:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
Push-Location frontend
npm.cmd run build
Pop-Location
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing
```

Latest completed checks before this document: 21 tests passed, one opt-in real-Qwen test skipped;
Vite build passed; API/UI healthy; model loaded after Phase 2 suite.

The real integration test is intentionally opt-in because CPU synthesis takes minutes. Use the
existing voice and persisted benchmark harnesses rather than launching duplicate model workers.

## Git and safety rules

- Do not use `git add .`; stage exact files and inspect `git diff --cached --name-only`.
- Preserve private ignored directories.
- Do not delete the Golden Baseline or existing generations used for A/B.
- Do not force dependency resolution or downgrade unrelated packages.
- Current normal Git push may require a command-scoped safe-directory override because Windows
  reports sandbox ownership:
  `git -c safe.directory=C:/Users/brandon/Downloads/Athena-Voice-Studio/athena-voice-studio push origin main`
- GitHub CLI API auth was stale, but normal Git credential push worked.

## Remaining roadmap after Phase 2

Follow the production brief in order: long-form stability and intelligent segmentation;
pronunciation dictionary; batch generation; exact history/regeneration/duplicate; model lifecycle;
progressive chunked playback only if honest; benchmark/rating system; restart/offline reliability;
one-click Windows launch hardening. Do not add Chatterbox/F5 or unrelated engines until the current
Qwen path and active phase are gated and checkpointed.
