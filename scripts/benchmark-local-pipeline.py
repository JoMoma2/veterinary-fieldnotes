"""Synthetic-only, resumable local WAV -> real LLM -> approved test export benchmark.

Never accepts clinical input or exports to production. No service configuration,
retention, remote inference or remote publication is performed.
"""

import argparse
import json
import time
import wave
from pathlib import Path
from urllib.parse import urlparse
from vet_pipeline.config import config
from vet_pipeline.hardware import ResourceSampler, inventory
from vet_pipeline.ingest import ingest
from vet_pipeline.library import current
from vet_pipeline.publication import approve_synthetic, export
from vet_pipeline.runner import run
from vet_pipeline.store import Store
from vet_pipeline.util import REPO, digest_file, load_json, write_json

p = argparse.ArgumentParser()
p.add_argument("--manifest", type=Path, required=True)
p.add_argument("--config", type=Path, required=True)
p.add_argument("--workspace", type=Path, required=True)
p.add_argument("--export-test", action="store_true")
a = p.parse_args()
cfg = config(a.config)
if cfg["provider"]["kind"] != "ollama" or urlparse(
    cfg["provider"]["base_url"]
).hostname not in ["localhost", "127.0.0.1", "::1"]:
    raise SystemExit(
        "This integration benchmark requires local Ollama, without paid/remote APIs"
    )
manifest = load_json(a.manifest)
if manifest.get("origin") != "synthetic":
    raise SystemExit("Synthetic recordings only")
if a.workspace.resolve() == REPO or REPO in a.workspace.resolve().parents:
    raise SystemExit("Choose a private workspace outside the application repository")
session = {
    "manifestSha256": digest_file(a.manifest),
    "configSha256": digest_file(a.config),
    "origin": "synthetic",
}
session_file = a.workspace / "benchmark-session.json"
if session_file.exists() and load_json(session_file) != session:
    raise SystemExit("Use a new workspace for a different corpus/configuration")
store = Store(a.workspace)
try:
    if any(j["origin"] != "synthetic" for j in store.jobs()):
        raise SystemExit("Not a synthetic-only workspace")
    write_json(session_file, session)
    audio_seconds = 0
    paths = []
    for item in manifest["recordings"]:
        file = (a.manifest.parent / item["file"]).resolve()
        paths.append(file)
        with wave.open(str(file), "rb") as wav:
            audio_seconds += wav.getnframes() / wav.getframerate()
        ingest(
            store,
            file,
            "s-local-benchmark",
            "2000-01-01",
            "synthetic",
            "synthetic-integration-benchmark",
        )
    started = time.monotonic()
    with ResourceSampler() as resources:
        result = run(store, cfg)
    wall = time.monotonic() - started
    library = current(store)
    # Verify reconnection/import idempotence without invoking either model again.
    assert all(
        not ingest(
            store,
            file,
            "s-local-benchmark",
            "2000-01-01",
            "synthetic",
            "synthetic-integration-benchmark",
        )[1]
        for file in paths
    )
    quality = [load_json(f) for f in (store.root / "quality").glob("**/*.json")]
    summary = {
        **session,
        "model": cfg["provider"]["model"],
        "audioSeconds": audio_seconds,
        "currentInvocationSeconds": round(wall, 3),
        "jobs": [
            {k: j[k] for k in ["id", "source_name", "stage", "attempts", "error"]}
            for j in store.jobs()
        ],
        "results": result,
        "recordCounts": {k: len(v) for k, v in library.items()},
        "classifiedSources": sum(q.get("classifiedSources", 0) for q in quality),
        "unclassifiedSources": sum(q.get("unclassifiedSources", 0) for q in quality),
        "quality": quality,
        "hardware": inventory(),
        "resources": resources.summary(),
        "duplicateImportPrevented": True,
        "limitations": "Synthetic audio; counts/schema validity do not establish clinical accuracy. Current invocation excludes work before a restart; use uninterrupted trials for throughput.",
    }
    if a.export_test:
        review = store.root / "synthetic-review.json"
        approve_synthetic(store, review)
        summary["exportedRecords"] = export(
            store, review, REPO / "fixtures/generated/public"
        )
    write_json(store.root / "pipeline-benchmark.json", summary)
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in ["hardware", "resources", "quality", "session", "results"]
            },
            indent=2,
        )
    )
    if any(j["stage"] != "done" for j in store.jobs()):
        raise SystemExit(1)
finally:
    store.close()
