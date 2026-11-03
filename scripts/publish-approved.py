"""Explicit reviewed publication; never called by the recorder watcher."""

import argparse, json, os, subprocess
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
a.checkout = a.checkout.expanduser().resolve()
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
# Use the same supported, user-local Node toolchain as local builds. A caller's
# demonstration environment must never select the dataset for publication.
node_runner = str(a.checkout / "scripts/local-node.sh")
build_environment = {**os.environ, "LIBRARY_DATASET": "production"}
subprocess.run([node_runner, "run", "check"], cwd=a.checkout, env=build_environment, check=True)
subprocess.run([node_runner, "run", "build"], cwd=a.checkout, env=build_environment, check=True)
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
