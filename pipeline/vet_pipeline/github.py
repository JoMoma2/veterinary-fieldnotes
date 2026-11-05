from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse

from .library import current, materialize, validate_library, write_library
from .recovery import verify_snapshot
from .util import load_json, write_json, lock, now


def _git(checkout, *args, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=checkout,
        check=check,
        capture_output=True,
        text=True,
        timeout=90,
    )


def _verify_private(checkout):
    # Verify the actual push remote, not GH_REPO or gh's inferred default repository.
    remote = _git(checkout, "remote", "get-url", "--push", "origin").stdout.strip()
    if remote.startswith("git@github.com:"):
        name = remote.removeprefix("git@github.com:").removesuffix(".git")
    else:
        url = urlparse(remote)
        if (
            url.scheme != "https"
            or url.hostname != "github.com"
            or url.username
            or url.password
        ):
            raise ValueError(
                "Master origin must be a credential-free GitHub repository URL"
            )
        name = url.path.strip("/").removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        raise ValueError("Invalid master GitHub repository")
    repo = subprocess.run(
        ["gh", "repo", "view", name, "--json", "visibility"],
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
    return name


def sync_master(store, checkout: Path, cfg, allow_clinical=False, push=False):
    checkout = checkout.resolve()
    if not (checkout / ".git").exists():
        raise ValueError("Initialize the private master checkout first")
    repository = _verify_private(checkout)
    if _git(checkout, "branch", "--show-current").stdout.strip() != "main":
        raise ValueError("Master synchronization requires the main branch")
    with lock(store.root):
        lib = validate_library(current(store))
        policy = checkout / "production-storage.json"
        if policy.exists():
            reserved = load_json(policy)
            if reserved.get("reservedOrigin") != "authorized-record" or reserved.get("archivePath") != "archive":
                raise ValueError("Unsupported production archive reservation")
            if any(e["origin"] == "synthetic" for group, values in lib.items() if group != "topics" for e in values):
                raise ValueError("Production private archive is reserved for authorized real knowledge; use a separate synthetic repository")
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
        # A lost/empty local database must not replace a populated remote archive.
        tracked = _git(
            checkout, "ls-tree", "-r", "--name-only", "HEAD", "archive", check=False
        )
        incoming = {
            f"archive/{group}/{e['id']}{'.md' if group == 'articles' else '.json'}"
            for group, entries in lib.items()
            if group != "topics"
            for e in entries
        }
        old_records = {
            p
            for p in tracked.stdout.splitlines()
            if len(Path(p).parts) == 3
            and Path(p).parts[1]
            in ["articles", "cases", "shifts", "discussions", "questions"]
        }
        if old_records - incoming:
            raise ValueError(
                "Local archive is missing committed records; recover from remote before synchronizing"
            )
        unrelated = [
            p
            for p in _git(
                checkout, "diff", "--cached", "--name-only"
            ).stdout.splitlines()
            if not (p.startswith("archive/") or p == "processing-status.json")
        ]
        if unrelated:
            raise ValueError("Unrelated staged changes must be committed separately")
        snapshot = materialize(store)
        if snapshot is None:
            raise ValueError("No completed knowledge to synchronize")
        target, staged, previous = (
            checkout / name
            for name in ["archive", ".archive-staged", ".archive-previous"]
        )
        if any(p.is_symlink() for p in [target, staged, previous]):
            raise ValueError("Master archive directories must not be symlinks")
        if staged.exists():
            shutil.rmtree(staged)
        write_library(staged, lib)
        write_json(staged / "manifest.json", load_json(snapshot / "manifest.json"))
        verify_snapshot(staged)
        if previous.exists():
            shutil.rmtree(previous)
        if target.exists():
            os.replace(target, previous)
        try:
            os.replace(staged, target)
        except BaseException:
            if previous.exists():
                os.replace(previous, target)
            raise
        write_json(
            checkout / "processing-status.json",
            [
                {key: j[key] for key in ["id", "sha256", "stage", "attempts", "error"]}
                for j in store.jobs()
            ],
        )
        _git(checkout, "add", "--", "archive", "processing-status.json")
        changed = _git(
            checkout,
            "diff",
            "--cached",
            "--quiet",
            "--",
            "archive",
            "processing-status.json",
            check=False,
        ).returncode
        if changed == 1:
            _git(
                checkout,
                "commit",
                "-m",
                "Save authorized knowledge snapshot",
                "--",
                "archive",
                "processing-status.json",
            )
        elif changed != 0:
            raise RuntimeError("Unable to inspect staged master changes")
        commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
        verified = False
        if push:
            _git(checkout, "push", "origin", "main")
            remote_head = _git(
                checkout, "ls-remote", "origin", "refs/heads/main"
            ).stdout.split()
            if not remote_head or remote_head[0] != commit:
                raise RuntimeError("Remote master commit verification failed")
            verified = True
        if previous.exists():
            shutil.rmtree(previous)
        return {
            "updated": changed == 1,
            "pushed": push,
            "remote_verified": verified,
            "commit": commit,
            "repository": repository,
        }


def sync_pending_master(store, cfg, *, force=False, checkout=None, allow_clinical=None):
    """One durable push attempt per invocation; retry pending work across restarts.

    Network failures never reset recording stages. Backoff is capped, not a busy
    retry loop or a permanent abandonment after a temporary Internet outage.
    """
    settings = cfg["github"]
    if not settings["enabled"] and not force:
        return {"status": "disabled", "pending": False}
    checkout = Path(checkout or settings["checkout"]).expanduser().resolve()
    clinical = settings["allow_clinical"] if allow_clinical is None else allow_clinical
    directory = store.root / "master-sync"
    statefile = directory / "state.json"
    with lock(directory):
        with lock(store.root):
            library = current(store)
            if not any(library[k] for k in library if k != "topics"):
                return {"status": "idle", "pending": False}
            fingerprint = hashlib.sha256(json.dumps(
                {"library": library, "checkout": str(checkout), "allowClinical": clinical,
                 "storageAuthorized": cfg["backup"]["allow_clinical_remote"]},
                sort_keys=True, ensure_ascii=False,
            ).encode()).hexdigest()
        prior = load_json(statefile) if statefile.exists() else {}
        same = prior.get("snapshotSha256") == fingerprint
        real = any(e['origin'] != 'synthetic' for group, values in library.items()
                   if group != 'topics' for e in values)
        if real and not (clinical and cfg['backup']['allow_clinical_remote']):
            # Intentional local-only mode is not an Internet/upload failure.
            # Preserve a durable pending snapshot without any Git/network call.
            if same and prior.get('status') == 'awaiting-authorization':
                return prior
            state = {'snapshotSha256': fingerprint, 'checkout': str(checkout),
                     'status': 'awaiting-authorization', 'pending': True,
                     'attempts': 0, 'retryAfter': 0,
                     'reason': 'Private GitHub storage awaits separate authorization; local processing continues'}
            write_json(statefile, state)
            with (directory / 'events.jsonl').open('a') as log:
                log.write(json.dumps({'at': now(), 'status': state['status']}) + '\n')
                log.flush()
                os.fsync(log.fileno())
            return state
        clock = time.time()
        if same and not force and prior.get("retryAfter", 0) > clock:
            return {**prior, "status": "deferred" if prior.get("pending") else "verified"}
        attempts = prior.get("attempts", 0) if same else 0
        state = {
            "snapshotSha256": fingerprint, "checkout": str(checkout),
            "status": "pending", "pending": True, "attempts": attempts + 1,
            "retryAfter": clock + min(settings["max_retry_seconds"],
                settings["retry_seconds"] * 2 ** min(attempts, 10)),
            "lastAttemptAt": now(),
        }
        # Persist before any remote call. SIGINT/power loss leaves a retryable intent.
        write_json(statefile, state)
        try:
            result = sync_master(store, checkout, cfg, allow_clinical=clinical, push=True)
        except Exception as error:
            state.update(status="failed", error=type(error).__name__)
        else:
            state.update(result, status="verified", pending=False, attempts=0,
                         retryAfter=time.time() + settings["verify_interval_seconds"],
                         lastSuccessAt=now())
        write_json(statefile, state)
        # Class-only errors: Git stderr may include private paths or credentials.
        with (directory / "events.jsonl").open("a") as log:
            log.write(json.dumps({"at": now(), "status": state["status"],
                                  "error": state.get("error"),
                                  "commit": state.get("commit")}) + "\n")
            log.flush()
            os.fsync(log.fileno())
        return state
