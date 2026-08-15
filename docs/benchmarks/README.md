# Benchmark records

JSON files in this directory are produced only by real local inference through `scripts/benchmark_engine.py`. No benchmark result is checked in until a model actually runs. Generated listening clips are written to `quality_samples/<engine>/<model>/<run-id>/`.

Example after installing weights and providing an authorized sample:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_engine.py --engine qwen3 --reference C:\path\authorized.wav --reference-text "Exact words spoken in the sample."
```

The current Qwen adapter is non-streaming; its recorded first-audio time is therefore the completed-file latency and is labeled accordingly.
