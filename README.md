# Athena Voice Studio

Athena Voice Studio is a **local, permission-based voice-cloning application** for creating reusable voice profiles and generating new speech through open-source inference. It has a dark React audio interface, a FastAPI backend, local SQLite metadata, and local file storage. The implementation does **not** depend on ElevenLabs, PlayHT, OpenAI TTS, or another hosted paid TTS provider.

> **Authorization is required.** Create profiles only for a voice you own or for which you have the voice owner’s explicit permission to reproduce. The application asks for this acknowledgment when saving every profile.

## What is implemented

| Area | Included behavior |
|---|---|
| Voice creation | Names a profile; uploads multiple WAV, MP3, M4A, FLAC, OGG, AAC, or WebM samples; records from a browser microphone; preserves originals; trims leading/trailing silence; normalizes loudness; produces a mono 24 kHz WAV reference; previews the prepared reference; and stores local metadata. |
| Local cloning | Uses Qwen3-TTS Base’s actual `generate_voice_clone` model path with reference audio and transcript. Reusable clone-prompt features are cached in process after first use. |
| Synthesis | Selects a voice, enters new text, chooses model-supported language, sets concrete pitch-preserving output speed, generates a WAV, exports MP3 when FFmpeg supports `libmp3lame`, and plays the result in the interface. |
| Voice library | Displays profile name, cleaned-reference duration, source-sample count, creation date, waveform, preview, and deletion. |
| Generations | Shows saved lines, generation time, output duration, playback, re-open/regenerate workflow, and WAV/MP3 downloads. |
| Device behavior | Detects CUDA availability at startup, displays GPU/VRAM or CPU fallback in the interface, loads the model lazily, and retains it for later generations. |
| Local API | Exposes stable loopback REST endpoints for authorized local clients; integration with any other application is outside this project. |

## Project layout

```text
athena-voice-studio/
├── backend/
│   ├── app/
│   │   ├── audio/processing.py        # FFmpeg preprocessing, speed, MP3 export
│   │   ├── tts/qwen_engine.py         # lazy real local Qwen3-TTS adapter
│   │   ├── config.py                  # environment-backed local settings
│   │   ├── db.py                      # SQLite profiles and generation history
│   │   └── main.py                    # FastAPI routes
│   └── requirements.txt
├── frontend/
│   └── src/                           # React/Vite audio interface
├── storage/
│   ├── samples/                       # untouched source recordings
│   ├── voices/                        # cleaned reference WAVs
│   └── generations/                   # generated WAV/MP3 files
├── docs/model-evaluation.md
├── setup.bat
├── setup_windows.ps1
└── start.bat
```

## Windows installation

Install the following prerequisites before starting:

| Requirement | Recommended version | Purpose |
|---|---:|---|
| Windows | Windows 10 or 11 | Local application host. |
| Python | 3.12 | Qwen3-TTS’s documented setup uses a fresh Python 3.12 environment.[1] |
| Node.js | 20+ | Runs the Vite React interface. |
| FFmpeg | Current | Required for preprocessing, duration detection, MP3 export, and speaking-speed adjustment. The setup script installs it with `winget` when available. |
| NVIDIA GPU | CUDA-capable, recommended | Recommended for usable latency. The application still starts in CPU fallback mode, but real synthesis may be much slower. |

1. Extract or clone this project to a local folder.
2. Double-click **`setup.bat`**. It creates `.venv`, installs a CUDA PyTorch build when `nvidia-smi` is available (otherwise CPU PyTorch), installs Python packages, and installs frontend packages.
3. Optionally copy `.env.example` to `.env` and adjust `QWEN_MODEL_ID`. The default `Qwen/Qwen3-TTS-12Hz-0.6B-Base` is the lightest selected clone model. Use the `1.7B-Base` model for a more capable GPU.
4. Double-click **`start.bat`**.
5. Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API listens only on [http://127.0.0.1:8000](http://127.0.0.1:8000).

The first synthesis loads and downloads the selected model through the local Qwen package. Model loading may take several minutes the first time; later requests reuse the resident model and the saved profile’s cached prompt representation.

## Creating a profile

Record one clear speaker in a quiet, non-reverberant room. **10–30 seconds** of conversational speech is a good starting range; the app accepts multiple samples and keeps their originals. Enter the text that was spoken in the supplied reference whenever possible. Qwen’s documented clone API accepts both `ref_audio` and `ref_text`; supplying the transcript enables its full prompt representation, while embedding-only fallback may lower fidelity.[1]

The profile creator saves originals in the canonical project-local `storage/samples/<voice-id>/`, prepares the inference reference at `storage/voices/<voice-id>/reference.wav`, and stores metadata in `storage/athena_voice.db`. A configured relative `STORAGE_ROOT` is always resolved from the project root, never the process working directory.

## API contract

All API paths are local and prefixed with `/api`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Reports active inference device, GPU details when available, selected model, and model-load status. |
| `GET` | `/api/voices` | Lists saved profiles and device state. |
| `POST` | `/api/voices` | Creates an authorized profile from multipart form data. Requires `name`, `files`, and `authorization_acknowledged=true`; `reference_text` is optional but recommended. |
| `GET` | `/api/voices/{voice_id}/preview` | Streams the processed local reference audio. |
| `DELETE` | `/api/voices/{voice_id}` | Removes the profile’s database row, source samples, prepared reference, and cached prompt. |
| `POST` | `/api/tts` | Runs actual local Qwen3-TTS inference and returns generated-audio metadata and URLs. |
| `GET` | `/api/generations` | Lists prior locally saved outputs. |
| `GET` | `/api/generations/{generation_id}/audio` | Streams the generated WAV. |
| `GET` | `/api/generations/{generation_id}/download/wav` | Downloads WAV. |
| `GET` | `/api/generations/{generation_id}/download/mp3` | Downloads MP3 when available. |

### Local API example

```bash
curl -X POST http://127.0.0.1:8000/api/tts ^
  -H "Content-Type: application/json" ^
  -d "{\"voice_id\":\"athena\",\"text\":\"Brandon, your interview is at ten thirty tomorrow.\",\"speed\":1.0,\"language\":\"English\"}"
```

A successful request returns a JSON object containing `audio_url`, `wav_download_url`, optional `mp3_download_url`, `duration_seconds`, `generation_seconds`, `model_id`, and `device`.

## Controls and model fidelity

The interface exposes only controls that have concrete behavior:

| Control | Implementation |
|---|---|
| Language | Sent to Qwen3-TTS’s documented `generate_voice_clone` call. |
| Speaking speed | Applied after model generation through FFmpeg’s pitch-preserving `atempo` filter. |
| Reference transcript | Used when creating Qwen’s clone prompt. Strongly recommended for quality. |

Temperature, pitch, seed, and unsupported emotion controls are intentionally absent; the selected clone API does not document them as stable public controls. Read the detailed comparison and selection rationale in [`docs/model-evaluation.md`](docs/model-evaluation.md).

## Troubleshooting

| Symptom | Resolution |
|---|---|
| “FFmpeg was not found” | Close all terminals after setup, confirm `ffmpeg -version` and `ffprobe -version` work in a new Command Prompt, then restart. |
| First generation takes a long time | This is expected while the local model is downloaded and loaded. Keep the app running after first use to preserve the model in memory. |
| CPU mode is displayed | Install a supported NVIDIA driver/CUDA-compatible PyTorch wheel, then rerun `setup.bat`. CPU inference remains a functional but slow fallback. |
| Profile creation says the reference is too short | Add clear speech so the post-trim prepared reference exceeds three seconds; 10–30 seconds is recommended. |
| Clone does not sound sufficiently similar | Use cleaner speech, supply the exact reference transcript, avoid background music/other speakers, and use a longer but focused sample. |
| MP3 button does not appear | FFmpeg’s `libmp3lame` encoder was unavailable. WAV output remains canonical and downloadable. |
| Model load fails after a package upgrade | Delete and recreate `.venv` with `setup.bat`; if the issue persists, switch the model ID in `.env` to the default 0.6B Base variant. |

## Privacy and safety

All application data is local by design: the app stores recordings, profile metadata, and generated output under `storage/`. The model package may download model weights on initial setup, but synthesis does not send profile recordings or text to a paid hosted TTS provider. Do not bind this local service to a public network interface without separately adding authentication, access control, encrypted storage, and a review of the relevant model license.

## References

[1]: https://github.com/QwenLM/Qwen3-TTS "Qwen3-TTS official repository"
