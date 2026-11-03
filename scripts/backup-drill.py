"""Two-version synthetic remote restore drill. Requires an authenticated rclone remote.

Only encrypted synthetic library files are uploaded. No real clinical input, sync,
remote deletion or encryption-key upload is supported.
"""

import argparse, json, os, uuid
from pathlib import Path
from vet_pipeline.backup import (
    create_key,
    create_backup,
    upload_backups,
    fetch_backup,
    restore,
    remote_storage_type,
)
from vet_pipeline.config import config
from vet_pipeline.ingest import ingest
from vet_pipeline.library import current, read_library
from vet_pipeline.private import initialize_private, private_path
from vet_pipeline.runner import run
from vet_pipeline.store import Store
from vet_pipeline.util import REPO, write_json, digest_file

p = argparse.ArgumentParser()
p.add_argument("--config", type=Path, required=True)
p.add_argument("--directory", type=Path, required=True)
a = p.parse_args()
os.umask(0o077)
cfg = config(a.config)
if not cfg["backup"]["remote"]:
    raise SystemExit(
        "Authenticate/configure a remote first; no independent-cloud result is claimed without one"
    )
root = initialize_private(a.directory)
# Namespace the drill to avoid altering any existing cloud directory or backup.
cfg["backup"]["remote"] = (
    cfg["backup"]["remote"].rstrip("/") + "/synthetic-drill-" + uuid.uuid4().hex
)
cfg["backup"]["allow_clinical_remote"] = False
mock = config()
source = root / "source-workspace"
store = Store(source)
key = private_path(root.parent / (root.name + "-recovery.key"))
create_key(key)
versions = []
try:
    for number, file in enumerate(["01-first.json", "02-followup.json"], 1):
        ingest(
            store,
            REPO / "fixtures/pipeline/transcripts" / file,
            "s-backup-drill",
            "2000-01-01",
            "synthetic",
            "synthetic-backup-drill",
        )
        if any(x["status"] != "done" for x in run(store, mock)):
            raise RuntimeError("Synthetic fixture processing failed")
        file = create_backup(store, key, root / "local-backups")
        versions.append(
            {
                "filename": file.name,
                "sha256": digest_file(file),
                "library": current(store),
            }
        )
        uploaded = upload_backups(store, cfg)
        if any(x["status"] != "verified" for x in uploaded):
            raise RuntimeError(
                "Remote backup verification failed; successful local backups are retained"
            )
finally:
    store.close()
# Simulate an unavailable source computer without destructive erasure.
source.rename(root / "unavailable-source-workspace")
(root / "local-backups").rename(root / "unavailable-local-backups")
results = []
for number, version in enumerate(versions, 1):
    downloaded = fetch_backup(
        cfg,
        version["filename"],
        key,
        root / "replacement" / version["filename"],
        version["sha256"],
    )
    restored = restore(downloaded, key, root / "replacement" / f"library-{number}")
    if read_library(restored) != version["library"]:
        raise RuntimeError("Restored synthetic library differs from its saved version")
    results.append(
        {
            "version": number,
            "filename": version["filename"],
            "downloadHashVerified": True,
            "restoredLibraryMatches": True,
        }
    )
backend = remote_storage_type(cfg)
known_cloud = backend in {"drive", "s3", "b2", "azureblob", "dropbox", "onedrive", "gcs"}
report = {
    "backend": backend,
    "independentProviderVerified": known_cloud,
    "origin": "synthetic",
    "remote": cfg["backup"]["remote"],
    "versions": results,
    "sourceWorkspaceUnavailableDuringRestore": not source.exists(),
    "keysUploaded": False,
    "keyFile": str(key),
    "offMachineKeyCustodyVerified": False,
    "note": "Store a recoverable key copy off this computer before production use; this drill only simulates replacement workspaces.",
}
write_json(root / "restore-drill.json", report)
print(json.dumps(report, indent=2))
