import json
import shutil
import subprocess

import pytest

from vet_pipeline import github
from vet_pipeline.ingest import ingest
from vet_pipeline.library import current
from vet_pipeline.recovery import recover_library, verify_snapshot
from vet_pipeline.runner import run
from vet_pipeline.store import Store
from vet_pipeline.util import REPO


def git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, check=True, capture_output=True, text=True
    )


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    path = tmp_path / "checkout"
    git(tmp_path, "clone", str(remote), str(path))
    git(path, "config", "user.name", "Synthetic Test")
    git(path, "config", "user.email", "synthetic@example.invalid")
    (path / "README.md").write_text("Synthetic private-repository test.\n")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "Initialize test")
    git(path, "push", "origin", "main")
    monkeypatch.setattr(github, "_verify_private", lambda _: "test/private")
    return path, remote


def test_sync_can_recover_entire_library_and_deduplication_on_a_fresh_machine(
    store, cfg, first, checkout, tmp_path
):
    run(store, cfg)
    expected = current(store)
    path, remote = checkout
    result = github.sync_master(store, path, cfg, push=True)
    assert result["remote_verified"]
    fresh_clone = tmp_path / "fresh-clone"
    git(tmp_path, "clone", str(remote), str(fresh_clone))
    fresh = Store(tmp_path / "replacement-computer")
    try:
        recover_library(fresh, fresh_clone / "archive")
        assert current(fresh) == expected
        assert (
            ingest(
                fresh,
                REPO / "fixtures/pipeline/transcripts/01-first.json",
                "s-2026-10-22",
                "2026-10-22",
                "synthetic",
                "test",
            )[1]
            is False
        )
    finally:
        fresh.close()
    tracked = git(path, "ls-tree", "-r", "--name-only", "HEAD").stdout
    assert "manifest.json" in tracked
    assert all(x not in tracked for x in ["transcripts/", ".wav", ".sqlite", ".key"])


def test_interrupted_push_resumes_without_duplicate_commit_or_inference(
    store, cfg, first, checkout, monkeypatch
):
    run(store, cfg)
    path, _ = checkout
    original = github._git

    def interrupted(path, *args, **kwargs):
        if args[0] == "push":
            raise TimeoutError("simulated interrupted network")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(github, "_git", interrupted)
    with pytest.raises(TimeoutError):
        github.sync_master(store, path, cfg, push=True)
    committed = git(path, "rev-parse", "HEAD").stdout
    monkeypatch.setattr(github, "_git", original)
    result = github.sync_master(store, path, cfg, push=True)
    assert not result["updated"] and result["remote_verified"]
    assert git(path, "rev-parse", "HEAD").stdout == committed


def test_accidental_checkout_deletion_is_rebuilt_from_committed_workspace(
    store, cfg, first, checkout
):
    run(store, cfg)
    path, _ = checkout
    github.sync_master(store, path, cfg, push=True)
    shutil.rmtree(path / "archive")
    result = github.sync_master(store, path, cfg, push=True)
    assert not result["updated"]
    assert verify_snapshot(path / "archive")[0] == current(store)


def test_empty_local_workspace_cannot_delete_remote_knowledge(
    store, cfg, first, checkout, tmp_path
):
    run(store, cfg)
    path, _ = checkout
    github.sync_master(store, path, cfg, push=True)
    before = git(path, "rev-parse", "HEAD").stdout
    empty = Store(tmp_path / "lost-local-data")
    try:
        with pytest.raises(ValueError, match="missing committed records"):
            github.sync_master(empty, path, cfg, push=True)
    finally:
        empty.close()
    assert git(path, "rev-parse", "HEAD").stdout == before


def test_tampered_remote_archive_is_refused_before_workspace_recovery(
    store, cfg, first, checkout, tmp_path
):
    run(store, cfg)
    path, _ = checkout
    github.sync_master(store, path, cfg)
    article = next((path / "archive/articles").glob("*.md"))
    article.write_text(
        article.read_text().replace("Source addition", "Tampered article")
    )
    fresh = Store(tmp_path / "fresh")
    try:
        with pytest.raises(ValueError, match="integrity"):
            recover_library(fresh, path / "archive")
        assert not current(fresh)["articles"]
    finally:
        fresh.close()


def test_clinical_sync_still_needs_both_authorization_gates(
    store, cfg, first, checkout
):
    run(store, cfg)
    for row in store.db.execute(
        "SELECT kind,id,data FROM library_records WHERE kind<>'topics'"
    ).fetchall():
        record = json.loads(row["data"])
        record["origin"] = "authorized-record"
        store.db.execute(
            "UPDATE library_records SET data=? WHERE kind=? AND id=?",
            (json.dumps(record), row["kind"], row["id"]),
        )
    store.db.commit()
    with pytest.raises(ValueError, match="explicit authorization"):
        github.sync_master(store, checkout[0], cfg, allow_clinical=True)
    cfg["backup"]["allow_clinical_remote"] = True
    with pytest.raises(ValueError, match="explicit authorization"):
        github.sync_master(store, checkout[0], cfg)
