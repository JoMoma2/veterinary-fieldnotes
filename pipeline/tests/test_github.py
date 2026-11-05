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


def test_pending_push_survives_restart_and_retries_without_inference(
    store, cfg, first, checkout, monkeypatch
):
    from vet_pipeline.extraction import Provider
    from vet_pipeline.cli import dispatch, main
    from types import SimpleNamespace
    from vet_pipeline.util import load_json

    run(store, cfg)
    expected = current(store)
    cfg["github"].update(enabled=True, checkout=str(checkout[0]))
    original = github._git
    clock = [1000]
    monkeypatch.setattr(github.time, "time", lambda: clock[0])

    def offline(path, *args, **kw):
        if args[0] == "push":
            raise TimeoutError("sensitive stderr must not be logged")
        return original(path, *args, **kw)

    monkeypatch.setattr(github, "_git", offline)
    private_config = store.root / "sync.toml"
    private_config.write_text('[github]\nenabled=true\ncheckout=' + json.dumps(str(checkout[0])) + '\n')
    monkeypatch.setattr("sys.argv", ["vet-pipeline", "--workspace", str(store.root),
                                   "--config", str(private_config), "run"])
    assert main() == 1
    failed = load_json(store.root / "master-sync/state.json")
    assert failed["pending"] and failed["error"] == "TimeoutError"
    committed = git(checkout[0], "rev-parse", "HEAD").stdout
    assert "sensitive stderr" not in (store.root / "master-sync/events.jsonl").read_text()
    assert github.sync_pending_master(store, cfg)["status"] == "deferred"
    assert current(store) == expected and store.get(first)["stage"] == "done"
    monkeypatch.setattr(github, "_git", original)
    monkeypatch.setattr(Provider, "extract", lambda *a: pytest.fail("inference repeated"))
    clock[0] = failed["retryAfter"] + 1
    fresh = Store(store.root)
    try:
        result = dispatch(SimpleNamespace(command="run", force_retry=False), fresh, cfg)
        assert result["processing"] == []
        assert result["master_sync"]["remote_verified"]
        assert not load_json(store.root / "master-sync/state.json")["pending"]
    finally:
        fresh.close()
    assert git(checkout[0], "rev-parse", "HEAD").stdout == committed


def test_nightly_github_storage_needs_no_independent_backup_credentials(
    store, cfg, first, checkout, monkeypatch
):
    from vet_pipeline.cli import dispatch
    from types import SimpleNamespace

    cfg["github"].update(enabled=True, checkout=str(checkout[0]))
    monkeypatch.setattr("vet_pipeline.automation.discover", lambda cfg: [])
    result = dispatch(SimpleNamespace(command="nightly", date="2026-10-22",
                                     key=None, backup_directory=None), store, cfg)
    assert result["master_sync"]["remote_verified"]
    assert not cfg["backup"]["remote"] and "backup_error" not in result
    assert store.get(first)["stage"] == "done"
    assert not store.db.execute("SELECT * FROM artifacts").fetchall()
    assert result["cleanup"]["deleted"] is False


def test_new_knowledge_is_synced_even_during_previous_success_cache(
    store, cfg, first, checkout
):
    run(store, cfg)
    cfg["github"].update(enabled=True, checkout=str(checkout[0]))
    previous = github.sync_pending_master(store, cfg)
    ingest(store, REPO / "fixtures/pipeline/transcripts/02-followup.json",
           "s-2026-10-22", "2026-10-22", "synthetic", "test")
    run(store, cfg)
    updated = github.sync_pending_master(store, cfg)
    assert updated["remote_verified"] and updated["commit"] != previous["commit"]
    assert verify_snapshot(checkout[0] / "archive")[0] == current(store)


def test_automatic_clinical_sync_does_not_bypass_explicit_authorization(
    store, cfg, first, checkout, monkeypatch
):
    run(store, cfg)
    row = store.db.execute("SELECT kind,id,data FROM library_records WHERE kind='articles' LIMIT 1").fetchone()
    record = json.loads(row["data"])
    record["origin"] = "authorized-record"
    with store.db:
        store.db.execute("UPDATE library_records SET data=? WHERE kind=? AND id=?",
                         (json.dumps(record), row["kind"], row["id"]))
    before = git(checkout[0], "rev-parse", "HEAD").stdout
    cfg["github"].update(enabled=True, checkout=str(checkout[0]), allow_clinical=True)
    sync = github.sync_master
    monkeypatch.setattr(github, 'sync_master', lambda *a, **k: pytest.fail('unauthorized Git operation attempted'))
    blocked = github.sync_pending_master(store, cfg)
    assert blocked['pending'] and blocked['status'] == 'awaiting-authorization'
    assert blocked['attempts'] == 0 and 'error' not in blocked
    assert github.sync_pending_master(store, cfg) == blocked
    assert git(checkout[0], "rev-parse", "HEAD").stdout == before
    monkeypatch.setattr(github, 'sync_master', sync)
    monkeypatch.setattr('vet_pipeline.extraction.Provider.extract', lambda *a: pytest.fail('repeated inference'))
    cfg['backup']['allow_clinical_remote'] = True
    assert github.sync_pending_master(store, cfg)['remote_verified']


def test_prepare_live_archive_preserves_synthetic_history_and_keeps_origin_separate(store, cfg, first, checkout, monkeypatch):
    import runpy
    from vet_pipeline.util import load_json

    run(store, cfg)
    original = current(store)
    path, remote = checkout
    github.sync_master(store, path, cfg, push=True)
    monkeypatch.setattr('sys.argv', ['prepare-live-master.py', '--checkout', str(path), '--apply', '--push'])
    runpy.run_path(str(REPO / 'scripts/prepare-live-master.py'), run_name='__main__')
    marker = load_json(path / 'production-storage.json')
    assert marker['reservedOrigin'] == 'authorized-record'
    assert not (path / 'archive').exists()
    assert verify_snapshot(path / marker['syntheticArchive'])[0] == original
    with pytest.raises(ValueError, match='reserved for authorized real knowledge'):
        github.sync_master(store, path, cfg, push=True)
    # Synthetic fixture facts with a simulated authorized origin exercise storage gates locally.
    for row in store.db.execute("SELECT kind,id,data FROM library_records WHERE kind<>'topics'").fetchall():
        data = json.loads(row['data']); data['origin'] = 'authorized-record'
        with store.db:
            store.db.execute('UPDATE library_records SET data=? WHERE kind=? AND id=?',
                             (json.dumps(data), row['kind'], row['id']))
    cfg['backup']['allow_clinical_remote'] = True
    result = github.sync_master(store, path, cfg, allow_clinical=True, push=True)
    assert result['remote_verified']
    assert verify_snapshot(path / marker['syntheticArchive'])[0] == original
