# Local Voice-Cloning Engine Evaluation

## Decision

Athena Voice Studio uses **Qwen3-TTS Base** as its concrete local inference engine. The default is `Qwen/Qwen3-TTS-12Hz-0.6B-Base` for the most practical first installation, with an environment-only upgrade path to `Qwen/Qwen3-TTS-12Hz-1.7B-Base` for a capable NVIDIA GPU. Both Base models support rapid voice cloning from a reference recording and transcript; the official API also supports building a reusable clone prompt, which this app caches per saved voice profile to avoid recomputing reference features on each Athena response.[1]

> The selected engine runs **in-process** through its open-source Python package. It does not call a paid hosted TTS API, and the profile samples and generated output live in the configured local storage directory.

## Comparison

| Engine | Strengths for this application | Trade-off | Decision |
|---|---|---|---|
| **Qwen3-TTS Base** | Current Apache-2.0 project; rapid voice cloning from reference audio plus transcript; reusable clone-prompt API; 0.6B and 1.7B variants; English and nine other major languages.[1] | Newer stack and CPU fallback is substantially slower than CUDA. | **Selected.** Strong fit for a persistent assistant because the same prompt representation can be reused across many outputs. |
| F5-TTS v1 Base | Maintained project with chunk inference, a direct CLI reference-audio workflow, CUDA installation guidance, and strong reported GPU throughput.[2] | The public pretrained model license is CC-BY-NC even though the code is MIT, making it a poor default where future commercial use is possible.[2] | Not the default. Keep it as a future adapter option if licensing is appropriate for the deployment. |
| Coqui XTTS-v2 | Mature, simple local API; short reference clip workflow; multilingual voice cloning and style transfer through cloning.[3] | The model is under the Coqui Public Model License rather than a permissive open-source model license.[3] | Not the default. A viable technical fallback only after a separate license review. |
| Fish Speech S2 | Actively self-hostable with short-reference voice cloning and expressive speech capabilities.[4] | Larger practical hardware footprint and a more demanding deployment path for a first Windows-local implementation. | Not selected for the initial build. |
| OpenVoice V2 | Lightweight and MIT-licensed; useful for tone-color conversion.[5] | Not the strongest single-engine fit for natural, long-form direct text-to-voice cloning in the requested assistant workflow. | Useful future secondary engine, not the primary engine. |

## Implemented Architecture

| Layer | Implementation | Reason |
|---|---|---|
| User interface | React + Vite | A desktop-oriented local browser experience with voice library, synthesis focus, generations, recording, playback, waveform visualization, and downloads. |
| API | FastAPI | Provides stable Athena-ready endpoints and isolates the frontend from model implementation details. |
| Inference | `Qwen3TTSModel.generate_voice_clone` | Uses actual local model inference from the Qwen package rather than placeholder audio or a cloud service.[1] |
| Prompt reuse | `create_voice_clone_prompt` cache | Preserves a processed reference representation in RAM after first generation for consistent successive responses.[1] |
| Audio processing | FFmpeg | Preserves originals, creates a mono 24 kHz normalized/trimmed reference WAV, measures duration, exports MP3, and applies pitch-preserving speed changes. |
| Storage | Local files + SQLite | Stores original samples, prepared prompts, WAV/MP3 output, and profile/generation metadata on the local machine. |

## Control Surface

The selected clone API documents `text`, `language`, reference audio, reference transcript, and clone prompt inputs.[1] Accordingly, Athena Voice Studio exposes only the controls it implements: **language** passes through to Qwen3-TTS, and **speaking speed** is applied locally with FFmpeg’s pitch-preserving `atempo` filter. Temperature, pitch, seed, and unsupported emotion sliders are deliberately not shown.

The reference transcript is recommended. Qwen’s documented clone workflow accepts a reference transcript for the reference audio; the app allows embedding-only fallback when no transcript is supplied, while warning users that it may reduce cloning fidelity.[1]

## Operational Notes

The selected 0.6B Base model is a reasonable Windows-first local baseline. It automatically downloads when loaded by the Qwen package, according to the official project documentation.[1] CUDA is auto-detected at application startup. The interface shows the active device and keeps the loaded model resident after first use. CPU operation is supported as a fallback but is expected to be markedly slower; a CUDA-capable NVIDIA GPU is the recommended production configuration.

## References

[1]: https://github.com/QwenLM/Qwen3-TTS "Qwen3-TTS official repository"
[2]: https://github.com/SWivid/F5-TTS "F5-TTS official repository"
[3]: https://huggingface.co/coqui/XTTS-v2 "Coqui XTTS-v2 model card"
[4]: https://github.com/fishaudio/fish-speech "Fish Speech official repository"
[5]: https://github.com/myshell-ai/OpenVoice "OpenVoice official repository"
