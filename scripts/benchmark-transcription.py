"""Benchmark existing local transcription backends; no downloads or global configuration changes."""

import argparse
import json
from pathlib import Path
from vet_pipeline.audio_benchmark import benchmark_audio

p = argparse.ArgumentParser()
p.add_argument("--manifest", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
p.add_argument("--backend", choices=["faster-whisper", "whisper-cpp"], required=True)
p.add_argument("--model", required=True)
p.add_argument("--executable", type=Path)
p.add_argument("--threads", type=int, default=4)
p.add_argument(
    "--origin", choices=["synthetic", "authorized-record"], default="synthetic"
)
p.add_argument("--authorization-ref", default="")
a = p.parse_args()
if not 1 <= a.threads <= 16:
    raise SystemExit("Use 1–16 threads")
r = benchmark_audio(
    a.manifest,
    a.output,
    a.backend,
    a.model,
    a.executable,
    a.threads,
    a.origin,
    a.authorization_ref,
)
print(
    json.dumps(
        {
            "report": str(a.output),
            "results": [
                {
                    k: x.get(k)
                    for k in [
                        "id",
                        "valid",
                        "seconds",
                        "wordErrorRate",
                        "realTimeFactor",
                        "gpuAccelerationConfirmed",
                        "error",
                    ]
                }
                for x in r["results"]
            ],
        },
        indent=2,
    )
)
