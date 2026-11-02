"""Explicit reviewed publication; never called by the recorder watcher."""

import argparse, json, subprocess
from pathlib import Path
from vet_pipeline.config import config
from vet_pipeline.store import Store
from vet_pipeline.publication import export

p = argparse.ArgumentParser()
p.add_argument("--workspace", required=True, type=Path)
p.add_argument("--review", required=True, type=Path)
p.add_argument("--checkout", required=True, type=Path)
p.add_argument("--allow-clinical", action="store_true")
p.add_argument("--push", action="store_true")
a = p.parse_args()
visibility = subprocess.run(
    ["gh", "repo", "view", "--json", "visibility"],
    cwd=a.checkout,
    check=True,
    capture_output=True,
    text=True,
)
if json.loads(visibility.stdout)["visibility"] != "PUBLIC":
    raise SystemExit("Expected the separate public website repository")
store = Store(a.workspace)
try:
    counts = export(store, a.review, a.checkout / "content/public", a.allow_clinical)
finally:
    store.close()
subprocess.run(["npm", "run", "check"], cwd=a.checkout, check=True)
subprocess.run(["npm", "run", "build"], cwd=a.checkout, check=True)
subprocess.run(["git", "add", "--", "content/public"], cwd=a.checkout, check=True)
changed = subprocess.run(
    ["git", "diff", "--cached", "--quiet", "--", "content/public"], cwd=a.checkout
).returncode
if changed == 1:
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "Publish reviewed educational content",
            "--",
            "content/public",
        ],
        cwd=a.checkout,
        check=True,
    )
elif changed != 0:
    raise SystemExit("Could not inspect approved content diff")
if a.push:
    subprocess.run(["git", "push", "origin", "main"], cwd=a.checkout, check=True)
print(json.dumps({"counts": counts, "pushed": a.push}))
