"""Download only pinned small public tokenizer metadata. Never fetch weights or send clinical text."""

import argparse, hashlib, json
from pathlib import Path
import httpx
from vet_pipeline.util import atomic_write, write_json

FILES = {
    "qwen3": (
        "Qwen/Qwen3-30B-A3B",
        "ad44e777bcd18fa416d9da3bd8f70d33ebb85d39",
        "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    ),
    "qwen35": (
        "Qwen/Qwen3.5-9B",
        "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
    ),
}
p = argparse.ArgumentParser()
p.add_argument(
    "--directory",
    type=Path,
    default=Path.home() / ".local/share/vet-fieldnotes-ai/tokenizers",
)
a = p.parse_args()
with httpx.Client(timeout=120, follow_redirects=True, trust_env=False) as client:
    for name, (repo, revision, expected) in FILES.items():
        folder = a.directory / name
        target = folder / "tokenizer.json"
        if (
            target.exists()
            and hashlib.sha256(target.read_bytes()).hexdigest() == expected
        ):
            print(name, "already verified")
            continue
        response = client.get(
            f"https://huggingface.co/{repo}/resolve/{revision}/tokenizer.json"
        )
        response.raise_for_status()
        data = response.content
        if len(data) > 30_000_000 or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Tokenizer size/checksum validation failed")
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write(target, data)
        write_json(
            folder / "source.json",
            {
                "repository": repo,
                "revision": revision,
                "sha256": expected,
                "bytes": len(data),
            },
        )
        print(name, "tokenizer metadata verified")
