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
- Local HEAD before this session: `df09a6f retune serious soft and intimate presets` (pushed,
  matched `origin/main`, clean working tree).
- This session (uncommitted): Soft trailing-silence fix (two iterations — see below), then Phase 3
  expressive-delivery work (wider preset ranges, three new post-processing dials, freeform UI
  sliders, `/performance-presets` endpoint). 6 files changed:
  `backend/app/audio/processing.py`, `backend/app/main.py`, `backend/tests/test_audio_processing.py`,
  `docs/PROJECT_SCHEMA_AND_HANDOFF.md`, `frontend/src/App.jsx`, `frontend/src/styles.css`.
- Phase 0 Golden Baseline: complete and user-approved.
- Phase 1 speed investigation: complete. The alternate Qwen path is not generally faster on CPU.
- Phase 2 performance presets: superseded by Phase 3 (see "Expressive delivery range and freeform
  controls"). Serious v2 and Intimate v2 (Phase 2, short sentence) still await user judgment;
  Phase 3's Neutral/Concerned/Intimate (new longer sentence, wider ranges) also await judgment.

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
| GET | `/performance-presets` | preset defaults + delivery-dial bounds, for the frontend sliders |
| GET | `/generations` | latest 100 generation records |
| GET/PATCH/DELETE | `/generations/{id}` | detail, label update, delete |
| GET | `/generations/{id}/audio` | inline WAV playback |
| GET | `/generations/{id}/download/{wav|mp3}` | downloads |

`GenerationRequest` accepts voice, text, language, speed, mode, engine, performance, optional
seed, normalization flag, pronunciation overrides, engine settings, and benchmark label.
`engine_settings` is a free-form dict merged over the selected preset (`{**preset, **engine_settings}`)
— it carries both native Qwen sampling overrides (temperature/top_k/top_p/repetition_penalty/
subtalker_*) and the four post-processing delivery dials (pace/pause_scale/energy/breath); see
"Expressive delivery range and freeform controls" below.

## Synthesis flow

```text
POST /api/tts
  -> validate voice, engine, performance
  -> normalize text
  -> choose base reference or optional performance-specific reference
  -> merge preset settings with request-level engine_settings overrides
  -> Qwen engine lazy-loads one model process
  -> build/reuse cached clone prompt keyed by voice/reference performance
  -> generate_voice_clone(... supported Qwen kwargs, including a max_new_tokens safety cap ...)
  -> trim_outer_silence (edges only)
  -> rescale_internal_pauses (pause_scale dial; edges must be trimmed first)
  -> FFmpeg atempo for requested speed × preset/dial pace
  -> blend_breath (breath dial; must run after both silence-detection passes above)
  -> shape_energy (energy dial; final loudnorm pass, absorbs breath's level nudge)
  -> export MP3
  -> ffprobe duration
  -> persist generation, exact settings, references, and phase timings
  -> return playable/downloadable API record
```

(Phrase-segmented synthesis — split text at punctuation, one model call per phrase, reassemble
with constructed pauses — was tried and reverted; see "Phase 4" below for why. The single-call flow
above is current.)

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
pitch. Every generation passes through `trim_outer_silence` first (same `silenceremove` +
`areverse` double-pass technique as `preprocess_reference`, threshold -60 dB, `start_silence`
matched to `start_duration` on each pass — see the dedicated fix section below for why that
matching is load-bearing), which removes only leading/trailing silence and never touches internal
pauses (`stop_periods=0` on both passes). Seconds removed are persisted in
`settings.outer_trim_seconds_removed` and `settings.phase_timings.outer_trim_seconds` as honest
evidence, not a silent edit. The preview for a voice is the processed reference, not evidence that
cloning occurred. See "Expressive delivery range and freeform controls" below for the three
post-processing dials (pause length, energy, breath) added after edge-trimming in the pipeline.

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
upload. **Superseded by the Phase 3 retune below** (much wider sampling ranges plus the new
pace/pause_scale/energy/breath dials) — see "Expressive delivery range and freeform controls" for
current exact mappings and the rationale. Warm's sampling values are carried forward unchanged
(user-approved); only its new-axis dials (pause_scale, energy) were added. Two early Concerned
sampling variants (pre-Phase-3) ran away for more than eight minutes on a twelve-word line and
were terminated; Phase 3's Concerned reintroduces a widened temperature but keeps a repetition
penalty (1.08) specifically as a runaway safety net — watch generation time on this preset after
any further change.

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

### Targeted v2 work completed after the initial handoff inventory

The active mappings were changed narrowly:

- Serious v2 now uses temperature .68, top_p .82, repetition penalty 1.08,
  sub-talker temperature .68, pace .95.
- Soft v2 uses the parameter family the user perceived as softer: temperature .76, top_p .86,
  repetition penalty 1.08, sub-talker temperature .74, pace .94.
- Intimate v2 uses the parameter family the user perceived as more intimate: temperature .78,
  top_p .88, repetition penalty 1.08, sub-talker temperature .76, pace .84.

Persisted labels and evidence:

| Label | Generation ID | Total audio | Silence analysis at -45 dB |
|---|---|---:|---|
| Phase 2 v2 · SERIOUS · targeted retune | `a0fe7c64ab5a4aa094a6640be10a39a6` | 4.02s | 1.09s sentence pause; original 5.90s defect gone |
| Phase 2 v2 · SOFT · targeted retune | `9bb2fcc9083145cf86d20b44ceb127d5` | 8.57s | 5.58s trailing silence after speech; cleanup still required |
| Phase 2 v2 · INTIMATE · targeted retune | `5a1c37b8bee843e9bf7f407d3614ea92` | 4.28s | 1.11s sentence pause |

The user should judge Serious v2, the spoken portion of Soft v2, and Intimate v2. Preserve the old
and v2 takes for A/B.

Because Qwen Base has no semantic emotion instruction, exact personal authenticity may not be
achievable from sampling knobs alone. If targeted retuning plateaus, state that honestly. Optional
same-speaker performance references can improve authenticity but must remain optional—not a gate
for normal synthesis.

### Soft trailing-silence fix (outer-edge trim) — two iterations, second one correct

Soft v2's trailing silence was a generation-pipeline gap, not a sampling-parameter problem: no
step ever trimmed silence from generated audio (only voice references got that treatment). Fixed
with `trim_outer_silence` in `backend/app/audio/processing.py` — the same
`silenceremove`+`areverse` double-pass technique already used for voice references, with
`stop_periods=0` on both passes so it can only ever remove leading/trailing silence, never an
internal pause. Wired into `POST /api/tts` in `backend/app/main.py` right after speed-stretch and
before MP3 export/duration probe. Removed seconds are persisted honestly in
`settings.outer_trim_seconds_removed` and `settings.phase_timings.outer_trim_seconds` rather than
silently edited away. This trim runs on every generation, not just Soft — it is safe by
construction for all presets, including Serious's retuned internal pause, since internal silence
is never touched.

**First attempt (`Phase 2 v3 · SOFT · outer-edge trim fix`, generation
`6eaec72d4ee444eab8dc1ee80c1ef642`) was itself defective.** It used a -45 dB threshold with
`start_silence=0.12` while `start_duration` was `0.20`/`0.35`. The user listened and reported it
clipped the "B" of "Brandon" and the trailing "g" of "something" — the trim was too tight. Root
cause, confirmed empirically with plain `ffmpeg` against synthetic fixtures (see
`test_trim_outer_silence_costs_nothing_on_fully_non_silent_audio` and
`test_trim_outer_silence_preserves_quiet_onset` in `backend/tests/test_audio_processing.py`):
FFmpeg's `silenceremove` needs to observe `start_duration` worth of continuous non-silence before
it trusts audio has resumed, and it unconditionally discards `start_duration - start_silence` even
when there is *no silence at all* in the input. With `start_silence < start_duration`, every
generation paid that forced "warm-up cost" off both ends regardless of the dB threshold — a plain
2-second non-silent test tone lost ~230ms to this alone. That is almost certainly what ate the "B"
and the "g", independent of how the threshold was tuned.

**Fix:** `start_silence` is now set equal to `start_duration` on each pass (0.20 leading, 0.35
trailing), and the threshold moved to -60 dB to match the already-proven `preprocess_reference`
value. Verified directly with `ffmpeg`: a fully non-silent 2.0s test tone now loses ~2ms (rounding
only, was ~230ms); a synthetic "quiet onset" at -50 dBFS (simulating a plosive/nasal onset or
decay) survives essentially intact. `backend/tests/test_audio_processing.py` has three trim
regression tests. Full suite: 24 passed, 1 skipped (opt-in real-Qwen test); `pip check` clean;
Vite build passed.

Second verification take, labeled `Phase 2 v4 · SOFT · corrected outer-edge trim`, generation
`5acc6ee42da1492c974af31add0dcaf1`: total audio 3.92s, `outer_trim_seconds_removed` only 0.24s
(vs. 0.66s for the flawed v3 take). `silencedetect` at -45 dB shows exactly one internal gap
(0.97s, the natural pause between the two sentences) and nothing flagged at either edge. Peak-level
envelope in the first 0.5s starts strong immediately (-4.5 dB in the first 50ms window, no dead
air); the last 0.6s shows a smooth taper (-14 dB down to roughly -25 dB) consistent with a natural
consonant decay rather than an abrupt cutoff. This is diagnostic evidence the fix behaves as
intended, not proof the ear will agree — per project rule, nothing here is claimed as fixed until
the user listens. `Phase 2 v3` (the flawed take) is left in place, clearly labeled, for A/B against
v4; do not delete it. The user should listen to and judge Serious v2, Intimate v2, and this v4
Soft take specifically for whether "Brandon" and "something" sound intact at both ends.

## Phase 3: expressive delivery range and freeform controls

User feedback on the Phase 2 suite: presets were "perceptible but too conservative... lacks
sufficient range and intensity" — specifically, Intimate read as "basically the same as the rest
just a little softer" instead of sultry. Requested axes: pitch contour, pacing, energy, emphasis,
pauses, breathiness, volume dynamics, sentence rhythm, all while preserving identity. Also
requested: freeform sliders (not just the ten fixed presets), and a longer evaluation sentence.

**Investigated first, before writing any code:** the installed Qwen3-TTS Base model has no native
pitch/emotion/energy/style control of any kind. Its full `generate_voice_clone` parameter surface
(confirmed by reading `qwen_tts/inference/qwen3_tts_model.py` directly) is exactly:
`top_k, top_p, temperature, repetition_penalty, subtalker_dosample, subtalker_top_k,
subtalker_top_p, subtalker_temperature, max_new_tokens`. Nothing else exists to control — no
pitch, no energy, no style token. This confirms the capability doc's existing honesty claim and
sets the real design constraint: any "pitch contour" or "energy" axis has to come from either (a)
much wider native sampling ranges (still the model's own generation, zero identity risk) or (b)
post-processing DSP (some identity risk depending on what's altered).

**User was asked and chose, explicitly, before implementation:** sampling-only for pitch/prosody
range — no pitch-shift DSP. Reasoning offered: pitch-shifting alters fundamental frequency after
the fact, which is the one lever that actually trades against "do not trade speaker identity for
speed or features." Wider sampling stays inside the model's own generation. This project should
**not** add pitch-shift DSP without asking again first if a future engineer is tempted to.

### What changed

1. **Much wider native sampling ranges per preset** — the identity-safe lever for pitch/rhythm
   variation. Previously all ten presets clustered temperature 0.68-1.10; Phase 3 spans roughly
   0.55 (Serious) to 1.30 (Excited), with proportionally wider top_p/top_k/repetition_penalty/
   subtalker_temperature spread. See `PERFORMANCE_PRESETS` in `backend/app/main.py` for exact
   values — the table in "Built-in performance profiles" above is now stale by design; that
   section points here instead of duplicating the dict.

2. **Three new post-processing dials**, implemented in `backend/app/audio/processing.py`, each
   independently unit-tested (`backend/tests/test_audio_processing.py`):
   - **`pause_scale`** (`rescale_internal_pauses`): stretches or compresses *only* the internal
     silence gaps between clauses — completely independent of `pace`, which uniformly stretches
     everything. Detects gaps via `ffmpeg silencedetect`, rebuilds the file as alternating
     speech/silence segments via `atrim` + `concat`, replacing each gap with
     `pause_scale × original_duration` of true digital silence (bounded to
     `[0.02s, min(4× original, 4.0s)]` so a slider cannot produce pathological silence). Must run
     after `trim_outer_silence` so every detected gap is genuinely internal.
   - **`energy`** (`shape_energy`): reshapes the overall loudness contour via a *second*
     `loudnorm` pass with `energy` mapped linearly to both the LRA (loudness range) target and the
     integrated-loudness target — `energy<1` narrows the range for a flatter/calmer contour,
     `energy>1` widens it and lifts the level for a livelier one. Deliberately reuses `loudnorm`
     (already proven safe in `preprocess_reference`) rather than a hand-tuned `compand` curve,
     since `loudnorm` is EBU R128-based and not prone to audible pumping artifacts. Runs *last* in
     the pipeline so its normalization pass sets the final envelope including whatever breath
     added.
   - **`breath`** (`blend_breath`) — **explicitly experimental.** Blends a very low-level,
     band-limited (roughly 750 Hz-5.25 kHz) pink-noise bed under the speech via `amix`, scaled
     from -34 dB (amount=0, inaudible) to -22 dB (amount=1). This is an approximation of
     aspiration/air texture, not a literal breath model — it is the one new axis most likely to
     sound synthetic rather than natural at higher settings. Must run after both silence-detection
     passes (`trim_outer_silence`, `rescale_internal_pauses`) — the added noise floor would
     otherwise defeat their detection. **The user must judge this by ear**, same rule as
     everything else; the UI's breath slider carries its own "(experimental)" label and a
     set-back-to-0 hint for exactly this reason.

   All three, plus `pace`, are clamped server-side in `synthesize()` regardless of source (preset
   or slider) via `DELIVERY_BOUNDS` / `_clamped_delivery_dial` in `backend/app/main.py`:
   `pace` 0.5-1.6, `pause_scale` 0.3-3.0, `energy` 0.5-1.8, `breath` 0.0-1.0.

3. **Pipeline order** (see the updated diagram under "Synthesis flow"): `trim_outer_silence` →
   `rescale_internal_pauses` → `time_stretch` (pace) → `blend_breath` → `shape_energy` → export.
   Each ordering constraint is load-bearing (documented inline in `synthesize()`); do not reorder
   without re-reading why.

4. **`GET /api/performance-presets`** returns `{presets: PERFORMANCE_PRESETS, bounds:
   DELIVERY_BOUNDS}` so the frontend never hand-duplicates the preset dict (drift risk).

5. **Freeform sliders in the UI** (`DeliveryControls` in `frontend/src/App.jsx`): five native
   sampling sliders (temperature, top_p, top_k, repetition_penalty, subtalker_temperature) and
   four post-processing sliders (pace, pause length, energy, breath). Picking a named preset loads
   its exact values into `draft.engine_settings` as a starting point; any slider can then be
   nudged past the preset, since the backend already merges `engine_settings` over the preset
   (`{**performance_settings, **payload.engine_settings}` — this plumbing pre-existed and needed
   no change). A "Reset to `<preset>`" button reloads the preset's exact values. Generation
   records persist `pace`/`pause_scale`/`energy`/`breath` **flat** (not nested) in `settings`
   specifically so Restore/Regenerate on a saved take reproduces the exact dial values used,
   rather than silently falling back to preset defaults for the new axes.

6. **New evaluation sentence**, used for the Phase 3 re-listen (longer, with a dash-pause, a
   comma-pause, a question, and an emphatic repetition — deliberately more room than the old
   twelve-word acceptance line to expose pacing/energy/rhythm differences):

   > Brandon, come here for a second — I need to tell you something, and I need you to really
   > listen this time. Can you do that for me? Because this... this actually matters.

### Evidence

Verification batch generated with the new sentence above, Golden Voice, Quality mode:

| Label | Generation ID | Gen time | Audio | Notes |
|---|---|---:|---:|---|
| Phase 3 · NEUTRAL | `d5a33aa24489485f9a178ddf1ba70f41` | 236.0s | 8.65s | Baseline, unchanged behavior. Two internal gaps detected (0.97s at the dash-pause, 0.16s near the question mark). mean -19.9 dB / max -2.3 dB. |
| Phase 3 · CONCERNED | `2e2ba0e08feb408cb0b41b019d74060d` | 192.7s | 11.34s | No runaway. `outer_trim_seconds_removed` was unusually large (5.37s) — the raw engine output apparently had a long silent lead-in/out this take (raw duration ~14.95s before trim); `trim_outer_silence` handled it correctly, final duration is normal. Given no seed support, treat this as one stochastic sample, not a systematic issue — worth re-checking if it recurs. |
| Phase 3 · INTIMATE | `2939fbaa72d34211b46e533b1b85d6f8` | 243.3s | 10.96s | **First attempt at this preset ran away past 8 minutes** — same failure signature as the historical Concerned incident (low temperature + weak repetition_penalty → degenerate repeat loop). Root cause: Intimate's `repetition_penalty` was 1.05 (golden default, the weakest of any preset in the set) paired with temperature 0.70. Fixed by raising it to 1.09, matching the safety-margin pattern already used by every other sub-0.85-temperature preset (Serious 1.10, Firm 1.08, Soft 1.06, Tired 1.10, Concerned 1.08). Retry completed normally. **Notable side effect to listen for:** at -45 dB, `silencedetect` found *zero* silence periods in the final output, even though `pause_seconds_added` confirms an internal gap was found and stretched (+0.47s) before breath was blended in. Breath's noise floor at `breath=0.4` sits around -29 dB — louder than the -45 dB silence threshold — so Intimate's pauses are now filled with soft breath texture rather than true silence. This may read as intentional "breathing during pauses" (arguably more sultry) or as the pause not registering as a clean pause; needs an actual ear, not just this measurement. |

None of the three runaway/timing risks recurred after the fix; all three complete in the same
~190-245s range. **Nothing above is a substitute for listening.** The user should judge all three,
paying specific attention to whether Intimate's breath texture sounds like natural, sultry
breathing or like synthetic hiss — set `breath` back toward 0 via the slider if it's the latter.
`Playful`, `Serious`, `Soft`, `Excited`, `Firm`, `Tired`, and `Warm` were not regenerated with the
new sentence this session (to control CPU-minutes spent before getting a reaction); regenerate
them once the direction on Neutral/Concerned/Intimate is confirmed.

### Accepted constraint: the Golden Voice reference itself is the ceiling, not the dials

User discovery, same session: a new voice cloned from an Audrey Hepburn reference sample expressed
the *same* presets/dials with far more dynamic fluctuation, pacing, pauses, and emotional range
than the Golden Voice (`hillsry`) ever has. The user confirmed directly — no A/B test needed —
that `hillsry`'s reference recording is flat the whole way through. **This is now an accepted
constraint, not an open hypothesis.** Qwen3-TTS's voice-clone conditioning likely inherits some
prosodic character from the reference recording itself, so a flat reference caps how expressive
the clone can sound regardless of sampling parameters or post-processing dials.

**Implication for future work:** do not chase more expressive range out of `hillsry` via further
preset/dial tuning — that ceiling is accepted, not a bug to keep fixing. If more range is wanted
later, the real lever is a richer/more dynamic Golden Voice reference recording, which is a
materially bigger and more sensitive decision than a preset tweak (see "Preserve the Golden Voice
QUALITY path" in Non-negotiable scope) and should only happen if the user explicitly raises it.

## Frontend architecture

The UI is intentionally a single React file plus CSS. `App.jsx` owns voices, generations,
engines, device, selected voice, draft generation settings, current output, notices, preset
library, and modal state. It fetches `/voices`, `/generations`, `/health`, `/engines`, and
`/performance-presets` on refresh.

Six views:

- Voices: authorized profiles, reference preview, delete.
- Synthesize: voice/engine/mode/language/performance, text, speed, **delivery controls (freeform
  sliders — see "Expressive delivery range and freeform controls" above)**, output deck.
- Generations: searchable persisted library, labels, playback, restore/regenerate/delete.
- Compare: real two-take playback; no invented ratings.
- Quality Lab: honest setup/measurement state.
- Settings: hardware, model, capabilities, storage truth.

Performance dropdown always includes Original plus ten experimental built-ins. No performance
upload is required. An old `PerformanceDialog` component and optional CSS/backend endpoints may
still exist as hidden advanced infrastructure; remove them later if desired, but do not expose a
required upload again.

**Default speed is 0.90, not 1.0** (`App.jsx`, initial `draft` state). User feedback 2026-08-16:
even Original/no-preset delivery at speed 1.0 — the exact value captured and approved in the
frozen Golden Baseline (`docs/baseline.md`, left untouched as a historical record; do not edit
it) — now sounds rushed ("running when it should be walking") once heard against longer, more
natural sentences. Speed is a pure post-processing `atempo` tempo change (pitch-preserving, no
identity risk), so lowering only the UI's *default starting value* is safe under the regression
gate; the slider still reaches 1.0 and above if 0.90 undershoots. **0.90 is an unverified first
cut** — it has not been confirmed by listening yet. If the user reports it's still too fast (or
now too slow), adjust this single default rather than touching `pace` in any preset or the
baseline record.

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

Latest completed checks before this document: 38 tests passed, one opt-in real-Qwen test skipped;
`pip check` clean; Vite build passed; API healthy after backend restart; model loaded after the
Phase 4 phrase-segmentation verification generation (see evidence above).

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

## Phase 4: phrase-segmented synthesis for natural cadence — REVERTED, DO NOT RE-ENABLE WITHOUT ASKING

**Status as of 2026-08-17: reverted at the user's explicit request.** `synthesize()` in
`backend/app/main.py` is back to plain single-call synthesis (matching Phase 3 exactly, plus the
independently-useful `max_new_tokens` cap — see the follow-up section below). The
`segment_phrases`/`concatenate_with_pauses`/`_cap_segment_count` machinery described below still
exists in `backend/app/text/segmentation.py` and `backend/app/audio/processing.py`, is still unit
tested, but is **not called from any live endpoint**. Do not wire it back in without the user
asking — read this whole section first so you don't repeat the same three bugs.

**Why it was reverted, in the user's own words after listening to two different fixed-up
attempts:** "the first one has a 5 second pause between each phrase, the second one treats every
phrase as a new sentence so it doesn't sound like a natural conversation... just switch it back to
how it was when it was running over itself. we will figure this out later." Every individual bug
found along the way (see below) got fixed correctly, and the *mechanism still didn't produce
natural-sounding speech* — phrase-by-phrase independent synthesis, even bug-free, apparently reads
as disconnected/sentence-like rather than conversational, and pause durations tuned to sound right
in isolation read as dead air in context. This is a fundamentally different problem from the bugs;
fixing the bugs did not fix it. The original "words run together" complaint is back, by choice,
until a better approach is found — do not treat that as unfinished/needing another patch pass
without the user raising it again.

**Original context below, preserved as-is for whoever revisits this:**

User feedback 2026-08-16/17, on a plain Original-delivery test synth (no preset involved): "the
model runs words together, clips pauses between phrases, and begins the next thought before the
previous one has naturally landed... someone excitedly talking over themselves." Explicitly not a
tempo complaint — lowering the default speed to 0.90 (**reverted back to 1.0, see the follow-up
section below — this was itself a bug, not a kept change**)
did not address it, and the user was clear: don't reduce tempo further, fix phrasing/cadence
directly, keeping the same energy/pitch/personality.

**Root cause:** a single `generate_voice_clone` call has no guarantee of leaving an audible gap at
any given comma or period — Phase 3's `pause_scale`/`rescale_internal_pauses` can only rescale a
gap that already exists in the raw output; it cannot create one where the model left none. That's
exactly what was happening on plain Original delivery.

**Fix — phrase-segmented synthesis**, implemented across three files:

- `segment_phrases()` in `backend/app/text/segmentation.py`: splits text at every sentence ending
  (`.!?`) and clause boundary (`,;:—...`), pairing each phrase with a punctuation-weighted pause
  (sentence 0.38s, clause 0.28s, comma 0.18s, ellipsis 0.32s — pre-pace "at rest" values). Fragments
  shorter than 3 words are folded into the next segment (a lone "Brandon," synthesized alone tends
  to come out with clipped, unnatural intonation, and is one more full model call for no benefit).
  Distinct from the pre-existing `segment_text()` (long-form ~420-char chunking for a different,
  not-yet-wired future feature) — do not conflate the two.
- `concatenate_with_pauses()` in `backend/app/audio/processing.py`: joins WAV segments with an
  exact true-silence gap after each one (last segment's pause is always dropped — the true end is
  `trim_outer_silence`'s job).
- `synthesize()` in `backend/app/main.py`: when `segment_phrases` returns more than one phrase, each
  is synthesized **separately** through `engine.synthesize` — same cached voice-clone prompt, same
  sampling settings every call, so energy/pitch/personality stay consistent across phrases — tightly
  edge-trimmed individually (`trim_outer_silence(..., start_duration=0.10, end_duration=0.10)`, same
  `start_silence=start_duration` fix as everywhere else), then reassembled with
  `concatenate_with_pauses`, with each pause additionally scaled by the `pause_scale` delivery dial.
  Plain single-phrase text (no punctuation at all) falls back to the original one-call path plus
  `rescale_internal_pauses`, unchanged. Per-segment `engine.last_timings` are summed for honest
  evidence; `phrase_segment_count` and `pause_seconds_added` are persisted on every generation.

This also makes `pause_scale` meaningfully reliable for the first time — previously it rescaled
whatever raw gap Qwen happened to leave (sometimes nothing); now it scales a real, guaranteed gap
at every major phrase boundary.

**Verification** (technical only — not a listening judgment, which is the user's call, not mine):
generation `fe64b683004840ada823e2a62a2c3005`, Original delivery, `hillsry`, the standard Phase 3
evaluation sentence, speed 0.90, 5 phrase segments from 4 boundaries (em-dash, comma, period,
question mark; the ellipsis before the final clause landed inside a merged segment, see below).
292.1s total (5 separate model calls) vs. ~236s for the single-call Phase 3 Neutral baseline on the
same sentence — a real but modest cost increase, not a multiplication. `silencedetect` at -45dB
found exactly the 4 constructed gaps at their expected positions and durations (post-0.90-speed-
stretch): ~0.30s (em-dash, expected 0.31), ~0.18s (comma, expected 0.20), ~0.47s (period, expected
0.42), ~0.46s (question mark, expected 0.42) — plus a 5th, smaller (0.17s) *natural* gap inside the
final merged segment ("Because this... this actually matters." — the short "Because this..."
fragment got folded into the next clause by the min-3-word merge rule, so that internal ellipsis
pause is whatever the model did on its own, not one we constructed). Peak-level envelope at all 4
constructed boundaries shows a smooth quiet-to-full ramp over ~60-100ms — consistent with intact
word onsets, not a clipped consonant landing straight into a loud vowel. `pause_seconds_added`
(1.22s pre-stretch) matched the sum of the four punctuation weights exactly (0.28+0.18+0.38+0.38).

**Not yet regenerated with this fix:** any Phase 2/3 preset takes. The user should test a fresh
Original-delivery synth first and confirm the cadence actually reads as natural before presets get
re-evaluated on top of it — the phrase-segmentation mechanism is new and this is its first real
output.

### Phase 4 follow-up: unbounded runaway hit for real, within the hour

While the user was testing the fix above, a plain Original-delivery generation stalled for 11+
minutes — confirmed via the generation directory (`storage/generations/<id>/segment-N.wav` files
stopped appearing after segment 3, while the backend process was still actively burning CPU, not
hung/frozen). Same degenerate-repeat-loop failure mode as the earlier Intimate/Concerned incidents,
except this was never actually bounded: Qwen's own `max_new_tokens` default is 2048, and on CPU
that can take many minutes to exhaust even when the extra tokens are pure repetition. **This
vulnerability was not new to Phase 4** — every single-call generation since Phase 0 carried it —
Phase 4 just multiplied the number of independent per-request engine calls (5, for that test
sentence), proportionally multiplying the chance that at least one of them hits it.

**Fix:** `max_new_tokens` is now forwarded to Qwen (added to the allowlist in
`_generation_kwargs`, `backend/app/tts/qwen_engine.py`) and every `engine.synthesize` call —
phrase-segmented or single-call fallback — now passes an explicit per-call budget via
`_estimate_max_tokens(text)` in `backend/app/main.py`: `max(250, min(1800, word_count * 80))`.
**This heuristic is an unverified guess** — nothing in the pipeline currently logs Qwen's actual
token counts, so 80 tokens/word is deliberately generous (favoring "never truncates real speech"
over "tightest possible cap"); a false-truncation bug would be worse than only partially shortening
a rare runaway. If a future take sounds abruptly cut off rather than clipped-but-complete, this
cap is the first thing to check — loosen the multiplier/floor/ceiling rather than assume it's
unrelated. Revisit with real measured token counts once something logs them. The stuck generation's
partial files were deleted and the backend restarted; this fix was not yet re-verified with a real
end-to-end generation before being handed back to the user (they were actively blocked and waiting).

### Phase 4 follow-up 2: long text still isn't safe (segment count cap)

Separately, a *different* Original-delivery generation with longer input text produced 14+ phrase
segments and ran 10+ minutes — confirmed genuinely progressing (not stuck) via steadily-appearing
`segment-N.wav` files, roughly one per minute. Each phrase segment costs one full sequential CPU
inference call, so long text turned into a very long wait even with nothing broken. Fixed with
`_cap_segment_count` in `backend/app/text/segmentation.py`: merges adjacent segments (preferring to
merge away the *smallest* pause boundary first) until the count is at or below `max_segments=8`.
Tested (`test_segment_phrases_caps_segment_count_on_long_text`,
`test_segment_phrases_respects_custom_max_segments`). This is a stopgap, not a real long-form
solution — moot now that phrase-segmentation is reverted, but the cap logic is sound if revisited.

### Phase 4 follow-up 3: underwater sound, then internal-silence bloat — then the actual verdict

Two further bugs were found and fixed via direct measurement (ffprobe/volumedetect/silencedetect,
not by ear) before the user could get a clean listen at all:

1. **"Underwater," sleepy-sounding audio.** Root cause: the 0.90 default speed from the earlier
   pacing complaint (see the "reduced to 0.90" note above) was never reverted after the user
   explicitly rejected tempo reduction as an approach — phrase-segmented takes were still going
   through `atempo` at 0.9. Measured directly: high-frequency content ~11dB more attenuated
   relative to overall level than an unmodified baseline (a known WSOLA time-stretch artifact,
   consistent with "underwater"). Fixed: default speed reverted to 1.0 in `frontend/src/App.jsx`
   (see Frontend architecture).
2. **Internal silence bloat within a single phrase segment.** Even after the tempo bug was fixed,
   one verification take came out at 18.8s for a sentence that should run ~10s, with
   `silencedetect` showing a 3.8-second dead patch and a dozen+ small extra gaps that weren't part
   of the constructed boundary pauses — a bad stochastic draw inside one segment's own short
   phrase, bounded in wall-clock time by the new `max_new_tokens` cap but not prevented from being
   *qualitatively* bloated with dead air within that budget. Mitigated by aggressively compressing
   any internal gap found *inside* an individual phrase segment before concatenation
   (`rescale_internal_pauses(segment_path, pause_scale=0.25, ...)`) — a short phrase has no
   legitimate reason to contain its own dramatic pause, unlike a full sentence.

With both of those fixed, a third verification take came out clean by every measurement available
(spectral profile matched the healthy baseline, only 6 reasonable-duration gaps, sane 11.3s total
duration) — generation `81814703e3684761b86f85e4be745acb`. **This is the one the user actually
listened to**, and the verdict was the mechanism itself, not a remaining bug (see the REVERTED
banner at the top of this Phase 4 section). Fixing every measurable defect did not make
phrase-segmented synthesis sound natural — that's the actual finding to carry forward, not "try
harder to fix the same approach."

### Phase 4 follow-up 4: the 80-tokens/word cap was itself the bug — garbage tail, not a hang

After reverting to single-call synthesis (see the REVERTED banner), the user ran a real paragraph
and reported: ~29s of real speech followed by ~2 full minutes of "noises and fuzz... squeaks and
garbage" — silently baked into the delivered WAV as if it were valid audio. The `max_new_tokens`
cap from follow-up 1 (80 tokens/word, floor 250, ceiling 1800) did its one job — bounded wall-clock
time, so this wasn't an infinite hang — but did nothing to stop a degenerate run from filling its
entire token budget with noise after the real content naturally ended, and nothing downstream
(`trim_outer_silence`, `rescale_internal_pauses`) can catch this: both only act on genuine
*silence*, and noise/squeaks are not silent.

**The cap itself was drastically miscalibrated, and this run proved it precisely.** 1800 tokens
produced ~149s of audio ⇒ ≈12.08 tokens/second — matching "Qwen3-TTS-**12Hz**" almost exactly.
`max_new_tokens` counts acoustic frames at the model's native 12Hz rate, not some larger
multi-codebook count. At a conservative 1.6 words/sec speaking floor that's ~7.5 tokens/word
needed; the old 80-tokens/word guess was ~10x that, leaving enormous headroom for a degenerate run
to fill with garbage. Two fixes, both in `backend/app/main.py`:

1. **Recalibrated `_estimate_max_tokens`**: ~15 tokens/word (2x the conservative-floor estimate,
   still generous for slow/dramatic delivery and pauses), floored at 200, capped at 1400 (≈117s of
   audio-equivalent — a legitimately very long paragraph can still hit this; if so, the fix is
   shorter input text, not a higher cap).
2. **New: a post-generation sanity check**, right after `engine.synthesize()` returns and before
   any post-processing runs. Computes `plausible_ceiling = max(4.0, (word_count / 1.6) * 2.0)`
   seconds and compares against the raw output's actual duration; if the raw output exceeds that,
   raises `EngineUnavailableError` (surfaced as a 503 with an honest, specific message) instead of
   proceeding to trim/pause-rescale/export a corrupted result. **This is the fix that actually
   matters** — the tighter token cap reduces how much garbage a worst-case run *can* produce, but
   only the sanity check refuses to *ship* it. Neither has been verified against a real repeat of
   this failure yet (would need another degenerate run to occur, which is inherently
   non-reproducible without a seed).

Frontend note, unrelated bug found in the same debugging pass: a separate FastAPI validation error
(reference transcript over 2000 characters, a plain pre-existing limit) was displaying as literal
text "[object Object]" in the CreateVoice/PerformanceDialog/Synthesize error banners, because
FastAPI's own validation errors return `detail` as an array of `{loc, msg, type}` objects while
this app's own `HTTPException` calls always send a plain string, and the frontend only handled the
string case. Fixed with a shared `errorMessage(payload)` helper in `frontend/src/App.jsx` that
handles both shapes; also added a defensive `.slice(0, 2000)` on both transcript textareas as a
backstop, since the exact mechanism that let a change bypass the existing HTML `maxLength="2000"`
was not conclusively identified.

### Phase 4 follow-up 5: root-cause research, and a real wall-clock timeout with process kill

Following the garbage-tail incident (follow-up 4), the user asked for the root cause to actually
be investigated — is it the voices, the delivery-control sliders, or Qwen itself — and for a real
fix rather than continued cap-tuning.

**Local data correlation.** Every persisted generation's settings and word count were pulled and
compared. The two conclusively-degenerate runs both used the **exact same 57-word, filler-heavy
text** ("Okay, so, like, I don't know if I'm explaining this right... they're probably not
fucking fine.") — first on voice `hillary3`, then again on a brand-new `hillary` voice built from
full sentences specifically to rule out a choppy-reference cause. Meanwhile that same `hillary3`
voice succeeded cleanly on four other, different 118-word texts. This is real evidence the
dominant trigger is **text content** (heavy filler words, a deliberately repeated word — "fine...
fine"), not primarily voice choice or the delivery sliders; sliders varied across both good and
bad runs with no clear pattern, and voice varied while the bad text stayed constant.

**Upstream research** (WebSearch, github.com/QwenLM/Qwen3-TTS) confirmed this is a **known,
documented Qwen3-TTS bug**, not specific to this project:
- PR #178: *"Without repetition penalty, the model can fall into a degenerate state where it
  keeps sampling the same codec tokens over and over"* — their fix tracks and penalizes repeated
  first-codebook tokens.
- Discussion #211 / Issue #318: the model can fail to emit an end-of-sequence token and loop
  indefinitely on certain inputs, with no warning.
- Directly relevant to this project's exact model: reported testing showed **the 0.6B Base model
  (what this project uses) produced 106 pauses longer than 1.5s on long-form generation, vs. just
  2 for the larger 1.7B model** — the smaller model is documented to be meaningfully worse at this.

**Fix 1 — `repetition_penalty` floor.** Original/Neutral delivery previously applied zero
override (the bare model default, ~1.05 — the single weakest setting anywhere in this app),
exactly what PR #178 identifies as the vulnerable configuration. `MIN_REPETITION_PENALTY = 1.08`
in `backend/app/main.py` is now applied to every generation (an explicit preset/user value still
wins). This is a small, defensive floor, not a character change — every built-in preset already
sat at or above it except Intimate's original 1.05, separately fixed earlier for the same reason.
**Flagged deliberately, not silent:** this means Original delivery's effective settings are no
longer literally "None" as recorded in `docs/baseline.md`'s frozen Golden Baseline — a
perceptible-risk trade-off, made on purpose. Watch Warm specifically (previously user-approved)
for any perceived character shift.

**Fix 2 — the fix that actually matters: real wall-clock timeout via subprocess kill.** The
existing `max_new_tokens` cap only bounds *token count*; on this hardware, hitting even the
tightened cap can still take a very long time — measured directly: **1800 tokens took 1412s
(23.5 min) of pure inference on a real runaway ⇒ ~0.785s/token.** No token cap can make a bad
run's wait *short* on hardware this slow; only forcibly killing it can. Python cannot safely
cancel a blocking call running in a thread, so `backend/app/tts/qwen_engine.py` was rewritten:
all real model inference (load, prompt cache, `generate_voice_clone`) now runs in a **persistent
child process**, communicated with via `multiprocessing` queues. `synthesize()` waits up to a
**token-budget-proportional** timeout (`max(90s, max_new_tokens * 1.3s)` — proportional, not
flat, so a short phrase fails fast while a legitimately long paragraph isn't killed prematurely);
if no response arrives in time, the worker is forcibly `.kill()`ed and a fresh one is spawned for
the next request (reloading the model once, ~15-20s — paid only when a runaway actually happens).
The prompt cache moved into the worker process along with the model (it's meaningless without
one); `clear_prompt`/`unload` now relay through the same queue-based protocol.

Verified for real, not just by inspection: 6 new tests in `backend/tests/test_qwen_engine.py`
using a fake worker function spawn a genuine subprocess (not mocked) and confirm round-trip
success, that a hung request is actually killed and raises a clear error, that the *next* request
against a freshly-respawned worker succeeds normally, and that the timeout scales correctly with
`max_new_tokens` (including the 90s floor for short text). 46/46 tests pass. Also smoke-tested
against the real model after restart: a real generation correctly hit the duration sanity check on
a too-short phrase (proving the whole pipeline — spawn, load, generate, IPC, sanity check — works
end to end), and a second real generation succeeded cleanly with `repetition_penalty: 1.08` and
`model_load_seconds: 0.0` confirming the worker persisted across requests rather than reloading.

**What this does not do:** guarantee degenerate runs stop happening — that's an upstream Qwen3-TTS
limitation, not something fixable from this codebase. It guarantees any single bad run is bounded
and costs at most one model reload, instead of an unbounded and possibly indefinite wait. If a
future request still stalls for the full timeout duration, that is expected — check for the
`EngineUnavailableError` "timed out" message in the response rather than assuming a new bug.

### Phase 4 follow-up 6: the duration ceiling had a real gap — detect-and-salvage instead

Follow-up 5's `plausible_ceiling` check missed a real case: a 74-word text degenerated to 88.4s
(vs. a clean 19.29s take of the *identical* text, confirming it was garbage) but stayed just
under that request's generous ceiling (92.5s) — a text-length-based ceiling has to stay loose to
avoid false-flagging legitimately long paragraphs, which leaves room for a proportionally-smaller
garbage tail to slip through on longer text undetected. The user asked directly: is testing with
the same text repeatedly the cause? **No** — see below.

**Diagnosis, from the real slipped-through file** (`storage/generations/3b7f8d66df634317a559ffb41b536188`,
preserved for this analysis): windowed volume analysis showed clean speech-level energy
(~-17 to -19dB) for the first ~20s, then a sharp, *sustained* drop to a quiet-but-not-silent floor
(~-32 to -41dB) for the remaining ~68s. Plain `silencedetect` found nothing — the garbage is
"noise/squeaks" (transient, spiky), never accumulating the continuous quiet run silencedetect
requires. This meant duration-ratio was fundamentally the wrong tool: it can only ever be a
backstop, not the primary defense.

**Fix — `find_degenerate_tail_start` + `truncate_at`** in `backend/app/audio/processing.py`:
tracks each 2-second window's RMS against the loudest window seen so far (a proxy for the real
speech level) and looks for 3 consecutive windows that fall ≥12dB below that peak — a signature
specific to a sustained *quiet* tail following real content, not a natural pause (near-silent,
brief) and not silence (continuous). When found, the audio is **truncated right there and the
good part is kept** — a meaningful upgrade from outright rejection, since the user is trying to
A/B-compare delivery settings and losing an otherwise-good take to a full retry is real cost, not
just inconvenience. The old `plausible_ceiling` check still runs afterward, now on the
post-truncation duration, as a backstop for shapes this doesn't catch (e.g. loud repetition with
no energy drop at all). Wired into `synthesize()` right after the raw engine call, before any
other post-processing. Evidence persisted as `settings.degenerate_tail_trimmed_at_seconds` (null
when nothing was trimmed).

Validated twice against real data, not just synthetic fixtures: 4 new unit tests
(`backend/tests/test_audio_processing.py`) using synthetic loud-then-spiky-quiet audio, **and**
run directly against the real slipped-through file — correctly detected the transition at exactly
20.0s and truncated to 20.0s, matching the clean 19.29s take of the identical text almost exactly.
49/49 tests pass.

**Answering the user's actual question — is same-text testing the cause?** No. Every piece of
evidence points at text *content* characteristics (filler words, repeated phrasing) and the
model's own documented instability, not at how many times a given text has been tried, and not
primarily at voice choice (see follow-up 5's `hillary3` vs. `hillary` finding). Re-running the
exact same text is not what causes this — each call is an independent stochastic draw with no
memory of prior attempts. **Practical testing guidance, given this is a real, unfixable-from-here
upstream risk on every single call:** prefer short (10-20 word), grammatically clean, non-repetitive
test phrases for delivery-setting A/B comparisons — shorter text bounds both the risk window and
the cost of a bad draw; avoid filler-heavy/repetitive phrasing specifically for test text if
possible; and now, if a run does degenerate, the tail-salvage means most of the time the good
content still comes through automatically rather than losing the whole take.

## Remaining roadmap after Phase 2

Follow the production brief in order: long-form stability and intelligent segmentation;
pronunciation dictionary; batch generation; exact history/regeneration/duplicate; model lifecycle;
progressive chunked playback only if honest; benchmark/rating system; restart/offline reliability;
one-click Windows launch hardening. Do not add Chatterbox/F5 or unrelated engines until the current
Qwen path and active phase are gated and checkpointed.

### TODO (not started, user-deferred)

- **STT for reference transcription**, so uploaded voice/performance reference audio can be
  auto-transcribed into the exact `reference_text` field instead of the user typing it or
  transcribing externally with a separate outside tool. Requested 2026-08-16; explicitly deferred —
  do not start without the user asking. Two paths, undecided which:
  - **OpenAI's cloud transcription API** (Whisper / `gpt-4o-transcribe`) — simplest to integrate,
    but would be the project's first outbound network call / cloud dependency (needs an API key),
    which cuts against the non-negotiable "Private audio, transcripts, generations... stay local"
    rule above (reference audio would leave the machine). Raise that trade-off explicitly before
    implementing this path.
  - **Local Whisper** (open-source, not the API) — `faster-whisper` (CTranslate2, INT8-quantized,
    good CPU performance) is the likely pick, matching the existing pattern of one resident local
    model already used for Qwen3-TTS; `whisper.cpp` as a lighter fallback. No network call, no
    identity/privacy trade-off, but another model download into `storage/model-cache` and another
    CPU inference cost alongside Qwen. User leaning toward a local solution as of 2026-08-16.
