from __future__ import annotations
import json, subprocess
from pathlib import Path
from .library import current, write_library
from .util import write_json, lock


def sync_master(store, checkout: Path, cfg, allow_clinical=False, push=False):
    # This path is a separately initialized private checkout. No audio, transcripts, keys, or credentials are copied.
    if not (checkout / ".git").exists():
        raise ValueError("Initialize the private master checkout first")
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "visibility"],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if json.loads(repo.stdout)["visibility"] != "PRIVATE":
        raise ValueError(
            "Master synchronization requires a verified private GitHub repository"
        )
    with lock(store.root):
        lib = current(store)
        real = any(
            e["origin"] != "synthetic"
            for group, values in lib.items()
            if group != "topics"
            for e in values
        )
        if real and not (allow_clinical and cfg["backup"]["allow_clinical_remote"]):
            raise ValueError(
                "Private repository storage of clinical material requires explicit authorization"
            )
        target = checkout / "archive"
        # Historical snapshots in Git remain restorable; current projection is refreshed in full.
        import shutil

        staged = checkout / ".archive-staged"
        if staged.exists():
            shutil.rmtree(staged)
        write_library(staged, lib)
        if target.exists():
            shutil.rmtree(target)
        staged.rename(target)
        write_json(
            checkout / "processing-status.json",
            [
                {
                    "id": j["id"],
                    "sha256": j["sha256"],
                    "stage": j["stage"],
                    "attempts": j["attempts"],
                    "error": j["error"],
                }
                for j in store.jobs()
            ],
        )
        subprocess.run(
            ["git", "add", "--", "archive", "processing-status.json"],
            cwd=checkout,
            check=True,
            timeout=30,
        )
        changed = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=checkout, timeout=30
        ).returncode
        if changed == 1:
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Save authorized knowledge snapshot",
                    "--",
                    "archive",
                    "processing-status.json",
                ],
                cwd=checkout,
                check=True,
                timeout=30,
            )
        elif changed != 0:
            raise RuntimeError("Unable to inspect staged master changes")
        if push:
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=checkout,
                check=True,
                timeout=90,
                capture_output=True,
            )
        return {"updated": changed == 1, "pushed": push}
