# Engine and model licensing review

Licenses must be rechecked at the exact pinned revision before distribution. A repository's code license does not automatically license its model weights, training data, voices, or third-party dependencies.

| Candidate | Code | Weights / use constraints | Product status |
|---|---|---|---|
| Qwen3-TTS | Apache-2.0 repository | Official repository currently presents the Qwen3-TTS release under Apache-2.0; verify the selected Hugging Face model card and NOTICE files at pin time. | Retained current adapter; empirical comparison pending on this checkout. |
| Chatterbox family | MIT repository | Resemble presents Standard, Turbo, Nano, and Multilingual weights as MIT-licensed and includes PerTh watermarking. Verify each chosen model card and bundled third-party assets. | High-priority bake-off candidate. |
| F5-TTS | MIT code | The official repository warns that pretrained models may have separate restrictions; the commonly used F5-TTS Base weights have historically used CC-BY-NC terms. Verify the exact v1 model card. | Evaluation-only unless intended use is license-compatible. |
| Fish Speech / S2 | AGPL-3.0 repository at time of review | Model-weight and commercial terms may differ from the Python API client's Apache license. Do not infer local-model rights from the API client license. | Evaluation-only pending exact weight terms and operational fit. |

Sources: official project repositories and their linked model cards: [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), [Chatterbox](https://github.com/resemble-ai/chatterbox), [F5-TTS](https://github.com/SWivid/F5-TTS), and [Fish Speech](https://github.com/fishaudio/fish-speech).
