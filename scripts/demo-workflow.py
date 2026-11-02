"""Run deterministic synthetic import → extraction → additive update → approval → export → encrypted restore."""

import argparse, tempfile, json
from pathlib import Path
from vet_pipeline.config import config
from vet_pipeline.store import Store
from vet_pipeline.ingest import ingest
from vet_pipeline.runner import run
from vet_pipeline.library import current, read_library
from vet_pipeline.publication import approve_synthetic, export
from vet_pipeline.backup import create_key, create_backup, restore
from vet_pipeline.util import REPO

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, default=REPO / "fixtures/generated/public")
a = p.parse_args()
with tempfile.TemporaryDirectory(prefix="vet-full-demo-") as tmp:
    root = Path(tmp)
    store = Store(root / "private")
    cfg = config()
    fixtures = REPO / "fixtures/pipeline/transcripts"

    def add(file):
        ingest(
            store,
            fixtures / file,
            "s-2026-10-22",
            "2026-10-22",
            "synthetic",
            "synthetic-demo-only",
        )

    add("01-first.json")
    assert all(r["status"] == "done" for r in run(store, cfg))
    before = next(
        a for a in current(store)["articles"] if a["id"] == "a-urinary-observations"
    )["body"]
    add("02-followup.json")
    add("03-workaround.json")
    assert all(r["status"] == "done" for r in run(store, cfg))
    lib = current(store)
    assert next(a for a in lib["articles"] if a["id"] == "a-urinary-observations")[
        "body"
    ].startswith(before)
    assert run(store, cfg) == []
    review = root / "review.json"
    approve_synthetic(store, review)
    counts = export(store, review, a.output)
    key = root / "backup.key"
    create_key(key)
    backup = create_backup(store, key, root / "backups")
    restore(backup, key, root / "restored")
    assert read_library(root / "restored") == lib
    print(
        json.dumps(
            {
                "exported": str(a.output),
                "records": counts,
                "checks": [
                    "additive update",
                    "contradiction retained",
                    "explicit case link",
                    "invalid question quarantined",
                    "resume without duplication",
                    "approved synthetic export",
                    "encrypted backup restored",
                ],
                "next": "LIBRARY_DATASET=pipeline-demo npm run build && npm run preview",
            },
            indent=2,
        )
    )
    store.close()
