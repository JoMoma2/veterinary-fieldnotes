"""Synthetic-only real GitHub loss/recovery drill. Does not touch production content or real workspaces."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from vet_pipeline import github
from vet_pipeline.backup import create_key, create_backup, restore
from vet_pipeline.config import config
from vet_pipeline.ingest import ingest
from vet_pipeline.library import current
from vet_pipeline.recovery import recover_library, verify_snapshot
from vet_pipeline.runner import run
from vet_pipeline.store import Store
from vet_pipeline.util import REPO, now, write_json

p = argparse.ArgumentParser()
p.add_argument("--checkout", required=True, type=Path)
p.add_argument("--work", required=True, type=Path)
p.add_argument("--report", required=True, type=Path)
a = p.parse_args()
if a.work.exists():
    raise SystemExit("Use a new dedicated drill directory")
os.umask(0o077)
a.work.mkdir(parents=True)
s = Store(a.work / "synthetic-source")
cfg = config()
for name in ["01-first.json", "02-followup.json", "03-workaround.json"]:
    ingest(
        s,
        REPO / "fixtures/pipeline/transcripts" / name,
        "s-2026-10-22",
        "2026-10-22",
        "synthetic",
        "synthetic-remote-durability-drill",
    )
assert all(r["status"] == "done" for r in run(s, cfg))
expected = current(s)
first = github.sync_master(s, a.checkout, cfg, push=True)
# Add a legitimate owner edit, commit locally, interrupt only the outgoing push, then retry.
row = s.db.execute(
    "SELECT id,data FROM library_records WHERE kind='articles' ORDER BY id LIMIT 1"
).fetchone()
record = json.loads(row["data"])
record["body"] += "\n\nSynthetic durability check: this addition must survive recovery."
with s.db:
    s.db.execute(
        "UPDATE library_records SET data=? WHERE kind='articles' AND id=?",
        (json.dumps(record), row["id"]),
    )
expected = current(s)
original = github._git
try:

    def interrupted(checkout, *args, **kwargs):
        if args[0] == "push":
            raise TimeoutError("Synthetic interruption before network push")
        return original(checkout, *args, **kwargs)

    github._git = interrupted
    try:
        github.sync_master(s, a.checkout, cfg, push=True)
    except TimeoutError:
        pass
    else:
        raise AssertionError("Interruption was not exercised")
finally:
    github._git = original
resumed = github.sync_master(s, a.checkout, cfg, push=True)
assert resumed["remote_verified"] and not resumed["updated"]
# Delete only this drill's generated archive checkout; regenerate without extraction.
shutil.rmtree(a.checkout / "archive")
repaired = github.sync_master(s, a.checkout, cfg, push=True)
assert (
    not repaired["updated"] and verify_snapshot(a.checkout / "archive")[0] == expected
)
key = a.work / "backup.key"
create_key(key)
backup = create_backup(s, key, a.work / "encrypted-backups")
restore(backup, key, a.work / "restored-files")
restored = Store(a.work / "backup-recovery")
recover_library(restored, a.work / "restored-files")
assert current(restored) == expected
restored.close()
# Close and move the local source out of reach; clone from GitHub into an independent path.
s.close()
os.rename(a.work / "synthetic-source", a.work / "simulated-lost-computer")
fresh_clone = a.work / "fresh-remote-clone"
subprocess.run(
    ["gh", "repo", "clone", resumed["repository"], str(fresh_clone)],
    check=True,
    capture_output=True,
)
fresh = Store(a.work / "replacement-computer")
recover_library(fresh, fresh_clone / "archive")
assert current(fresh) == expected
_, new = ingest(
    fresh,
    REPO / "fixtures/pipeline/transcripts/01-first.json",
    "s-2026-10-22",
    "2026-10-22",
    "synthetic",
    "synthetic-recovery-test",
)
assert not new
fresh.close()
report = {
    "at": now(),
    "syntheticOnly": True,
    "repository": resumed["repository"],
    "remoteCommit": resumed["commit"],
    "counts": {k: len(v) for k, v in expected.items()},
    "checks": {
        "verifiedGitHubPush": True,
        "interruptedPushResumed": True,
        "accidentalCheckoutDeletionRepaired": True,
        "freshCloneWithoutSourceWorkspaceRecovered": True,
        "duplicateDetectionRecovered": True,
        "caseContinuityManifestRecovered": True,
        "encryptedBackupRestored": True,
    },
    "independentProviderBackup": "Not configured; encrypted backup used in this drill is local. A GitHub clone proves off-computer storage, not a second-provider backup.",
    "keyCustody": "Drill-only key remains in the protected work directory. No key or audio was uploaded.",
}
write_json(a.report, report)
print(json.dumps(report, indent=2))
