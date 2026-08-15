# Athena Voice Studio — Build and Verification Report

## Delivered application

Athena Voice Studio is a Windows-ready, local React and FastAPI application for **authorized voice-profile creation** and **open-source voice-cloned speech synthesis**. The selected engine is Qwen3-TTS Base, using the practical `0.6B` model by default. It performs actual in-process local voice cloning; it does not call ElevenLabs, PlayHT, OpenAI TTS, or another hosted paid TTS provider.

The project includes a polished dark audio-studio interface, local FastAPI REST endpoints, Qwen model caching, FFmpeg preparation/export, SQLite metadata, local profile and generation storage, Windows setup and launch scripts, and setup/troubleshooting documentation.

| Capability | Result |
|---|---|
| Create an authorized voice profile | Implemented with required authorization acknowledgment, multi-file upload, browser microphone capture, source preservation, silence trimming, loudness normalization, resampling, preview, and local persistence. |
| Generate cloned speech | Implemented through `Qwen3TTSModel.generate_voice_clone`, using a cached reusable clone prompt after first use. |
| Voice library | Implemented with profile cards, prepared-reference waveform, preview, duration, creation date, source count, and deletion. |
| Synthesis workspace | Implemented with voice selection, text entry, model-native language selection, pitch-preserving output speed, local generation status, waveform, player, metadata, WAV download, MP3 download, and regenerate action. |
| Athena-facing API | Implemented with `GET /api/voices`, `POST /api/voices`, `DELETE /api/voices/{voice_id}`, `POST /api/tts`, and supporting health, preview, history, playback, and download routes. |
| Device awareness | Implemented. CUDA is detected automatically; the interface identifies CUDA hardware and VRAM when available, otherwise shows CPU fallback. |
| Windows handoff | Implemented with `setup.bat`, `setup_windows.ps1`, `start.bat`, `.env.example`, `requirements.txt`, and README instructions. |

## Verification performed

The React application compiled successfully with Vite after implementation. Python source compilation also completed without errors. The backend, frontend, and real Qwen inference pipeline were run locally in the sandbox.

| Verification activity | Observed result |
|---|---|
| Local Qwen adapter | The selected Qwen3-TTS `0.6B` Base model was downloaded and loaded on CPU in bfloat16 mode. |
| Real inference script | The saved verification script generated a local 24 kHz WAV through the implemented adapter. It wrote `actual-local-clone.wav` at 238,124 bytes. |
| Authorized profile API | A profile was created through `POST /api/voices` with an authorized test reference, prepared successfully to a 2.67-second reference WAV, and persisted locally. |
| Local Athena API | `POST /api/tts` produced a new local cloned WAV, returned metadata and API URLs, and persisted the generation. |
| UI synthesis | The browser UI created a second local generation, then rendered the waveform, native audio player, generation time, model label, output duration, WAV button, and MP3 button. |
| Download endpoints | Downloaded WAV was confirmed as 24 kHz mono PCM audio. Downloaded MP3 was confirmed as MPEG Layer III audio. Both endpoints returned the correct media type and attachment disposition. |

> The sandbox had no NVIDIA GPU and 3.8 GB of RAM. CPU fallback still completed real synthesis successfully, with roughly 65 seconds required for the displayed eleven-second output. A compatible NVIDIA GPU is strongly recommended for practical assistant latency.

## Model rationale

Qwen3-TTS Base was selected because its official API supports reference-audio-plus-transcript rapid voice cloning and a reusable clone-prompt object. Its `0.6B` and `1.7B` Base variants provide an explicit local-performance trade-off, while the project’s Apache-2.0 license supports a cleaner future deployment path than some alternatives.[1]

F5-TTS, Coqui XTTS-v2, Fish Speech, and OpenVoice were evaluated before selection. The complete comparison, licensing considerations, and adapter rationale are recorded in [`docs/model-evaluation.md`](docs/model-evaluation.md).[1] [2] [3] [4] [5]

## Handoff

On Windows, run **`setup.bat`** once, then **`start.bat`**. Open `http://127.0.0.1:5173` when both local services launch. The first generation downloads and loads the chosen model; later requests reuse it while the application stays running.

Use clear, single-speaker samples recorded in a quiet environment. The interface recommends 10–30 seconds even though the validated rapid-cloning path permits shorter clean references. Supply the exact reference transcript whenever possible, as this enables the engine’s full clone-prompt path. Only profiles for voices you own or have explicit permission to reproduce should be created.

## References

[1]: https://github.com/QwenLM/Qwen3-TTS "Qwen3-TTS official repository"
[2]: https://github.com/SWivid/F5-TTS "F5-TTS official repository"
[3]: https://huggingface.co/coqui/XTTS-v2 "Coqui XTTS-v2 model card"
[4]: https://github.com/fishaudio/fish-speech "Fish Speech official repository"
[5]: https://github.com/myshell-ai/OpenVoice "OpenVoice official repository"
