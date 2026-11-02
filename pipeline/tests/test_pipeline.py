import copy, json, os, time, wave, sys, types
from pathlib import Path
import pytest
from vet_pipeline.util import REPO, load_json, write_json, lock, digest_file
from vet_pipeline.ingest import ingest, transcribe, transcript_valid
from vet_pipeline.runner import run, reset_failed
from vet_pipeline.library import (
    current,
    current_root,
    read_library,
    validate_library,
    retrieve,
)
from vet_pipeline.extraction import Provider, validate_extraction, chunks
from vet_pipeline.publication import approve_synthetic, review_template, export
from vet_pipeline.backup import (
    create_key,
    create_backup,
    restore,
    inspect_backup,
    cleanup,
    upload_backups,
)
from vet_pipeline.config import authorize_provider

F = REPO / "fixtures/pipeline/transcripts"


def add(store, name="02-followup.json", shift="s-2026-10-22"):
    return ingest(store, F / name, shift, "2026-10-22", "synthetic", "test")[0]


def test_full_workflow_consolidates_preserves_contradiction_and_exports(
    store, cfg, first, tmp_path
):
    assert run(store, cfg)[0]["status"] == "done"
    lib = current(store)
    old = next(a for a in lib["articles"] if a["id"] == "a-urinary-observations")[
        "body"
    ]
    add(store)
    add(store, "03-workaround.json")
    assert all(r["status"] == "done" for r in run(store, cfg))
    lib = validate_library(current(store))
    assert len(lib["articles"]) == 4
    assert len(lib["cases"]) == 1
    assert len(lib["discussions"]) == 6
    a = next(a for a in lib["articles"] if a["id"] == "a-urinary-observations")
    assert a["body"].startswith(old)
    assert "contradict" in a["body"]
    assert len(a["sourceDiscussionIds"]) == 2
    c = lib["cases"][0]
    assert c["diagnosis"] is None and c["outcome"] is None
    assert len(c["sourceDiscussionIds"]) == 2
    assert len(lib["questions"]) == 3
    assert list((store.root / "quarantine").glob("*.json"))
    assert all(
        e["publication"]["audience"] == "private"
        for group in ["articles", "cases", "shifts", "discussions", "questions"]
        for e in lib[group]
    )
    review = tmp_path / "review.json"
    approve_synthetic(store, review)
    target = tmp_path / "export"
    counts = export(store, review, target)
    assert counts["articles"] == 4
    validate_library(read_library(target))
    assert (
        "test"
        not in (target / "articles/a-urinary-observations.md")
        .read_text()
        .split("---")[1]
        .lower()
    )


def test_repeat_connection_deduplicates_without_rerunning(store, cfg, first):
    assert run(store, cfg)
    id, created = ingest(
        store, F / "01-first.json", "s-2026-10-22", "2026-10-22", "synthetic", "test"
    )
    assert id == first and not created
    before = current_root(store).resolve()
    assert run(store, cfg) == []
    assert current_root(store).resolve() == before


def test_one_failed_recording_does_not_abort_other_files_and_retries_are_bounded(
    store, cfg, first, monkeypatch
):
    second = add(store)
    original = Provider.extract

    def fail(self, t, context, origin):
        if t["fixtureKey"] == "first":
            raise TimeoutError("PRIVATE_TEST_SENTINEL")
        return original(self, t, context, origin)

    monkeypatch.setattr(Provider, "extract", fail)
    r = run(store, cfg)
    assert r[0]["status"] == "failed" and r[1]["status"] == "done"
    assert store.get(second)["stage"] == "done"
    run(store, cfg, True)
    run(store, cfg, True)
    assert store.get(first)["attempts"] == 3
    assert run(store, cfg, True) == []
    assert "PRIVATE_TEST_SENTINEL" not in (store.root / "events.jsonl").read_text()
    monkeypatch.setattr(Provider, "extract", original)
    reset_failed(store, first)
    assert run(store, cfg)[0]["status"] == "done"


def test_failure_after_extraction_never_calls_provider_again(
    store, cfg, first, monkeypatch
):
    import vet_pipeline.runner as runner

    real = runner.commit
    monkeypatch.setattr(
        runner, "commit", lambda *a: (_ for _ in ()).throw(OSError("disk full"))
    )
    assert run(store, cfg)[0]["stage"] == "commit"
    assert store.get(first)["stage"] == "commit"
    monkeypatch.setattr(runner, "commit", real)
    monkeypatch.setattr(
        Provider, "extract", lambda *a: pytest.fail("provider repeated")
    )
    assert run(store, cfg, True)[0]["status"] == "done"


def test_crash_after_snapshot_swap_is_idempotent(store, cfg, first, monkeypatch):
    original = store.update

    def fail(id, **fields):
        if fields.get("stage") == "done":
            raise OSError("crash after snapshot")
        original(id, **fields)

    monkeypatch.setattr(store, "update", fail)
    assert run(store, cfg)[0]["status"] == "failed"
    count = len(current(store)["discussions"])
    monkeypatch.setattr(store, "update", original)
    assert run(store, cfg, True)[0]["status"] == "done"
    assert len(current(store)["discussions"]) == count


def test_provider_timeout_resumes_transcript_without_transcribing_again(
    store, cfg, first, monkeypatch
):
    original = Provider.extract
    monkeypatch.setattr(
        Provider, "extract", lambda *a: (_ for _ in ()).throw(TimeoutError())
    )
    run(store, cfg)
    assert store.get(first)["stage"] == "extract"
    monkeypatch.setattr(Provider, "extract", original)
    monkeypatch.setattr(
        "vet_pipeline.runner.transcribe",
        lambda *a: pytest.fail("transcription repeated"),
    )
    assert run(store, cfg, True)[0]["status"] == "done"


def test_invalid_quote_is_rejected(store, cfg, first):
    t = load_json(F / "01-first.json")
    d = Provider(cfg).extract(t, [], "synthetic")
    d["discussions"][0]["quotes"][0]["text"] = "invented result"
    with pytest.raises(ValueError):
        validate_extraction(d, t)


def test_publication_is_fail_closed_and_approval_binds_exact_content(
    store, cfg, first, tmp_path
):
    run(store, cfg)
    review = tmp_path / "review"
    review_template(store, review)
    target = tmp_path / "export"
    assert export(store, review, target)["articles"] == 0
    approve_synthetic(store, review)
    add(store)
    run(store, cfg)
    with pytest.raises(ValueError, match="stale"):
        export(store, review, target)
    assert not list((target / "articles").glob("*.md"))


def test_unapproved_sources_and_recording_metadata_are_omitted(
    store, cfg, first, tmp_path
):
    run(store, cfg)
    review = tmp_path / "review"
    approve_synthetic(store, review)
    r = load_json(review)
    for e in r["entries"]:
        if e["kind"] == "discussions":
            e["approved"] = False
    write_json(review, r)
    target = tmp_path / "out"
    export(store, review, target)
    lib = read_library(target)
    assert not lib["discussions"] and not lib["cases"] and not lib["questions"]
    assert not lib["shifts"][0]["recordings"]
    assert all(not a["sourceDiscussionIds"] for a in lib["articles"])


def test_encrypted_backups_restore_and_refuse_corruption_or_overwrite(
    store, cfg, first, tmp_path
):
    run(store, cfg)
    key = tmp_path / "key"
    create_key(key)
    file = create_backup(store, key, tmp_path / "backups")
    file2 = create_backup(store, key, tmp_path / "backups")
    assert file != file2
    assert b"AMBER-TRAINING" not in file.read_bytes()
    target = tmp_path / "restore"
    restore(file, key, target)
    assert current(store) == read_library(target)
    with pytest.raises(ValueError):
        restore(file, key, target)
    raw = bytearray(file.read_bytes())
    raw[-12] ^= 1
    file.write_bytes(raw)
    with pytest.raises(Exception):
        inspect_backup(file, key)
    assert current(store) == read_library(target)


def test_cleanup_requires_confirmed_backup_and_keeps_original(
    store, cfg, first, tmp_path
):
    run(store, cfg)
    cfg["retention"].update(days=0, enabled=True, require_remote=True)
    assert cleanup(store, cfg, True) == []
    key = tmp_path / "key"
    create_key(key)
    create_backup(store, key, tmp_path / "backups")
    assert cleanup(store, cfg, True) == []
    cfg["retention"]["require_remote"] = False
    # An unresolved quarantined question is a retention hold.
    assert cleanup(store, cfg, True) == []
    (store.root / "quarantine" / f"{first}-questions.json").unlink()
    assert cleanup(store, cfg, False) == [first]
    assert (store.root / "inputs" / f"{first}.json").exists()
    cleanup(store, cfg, True)
    assert not (store.root / "inputs" / f"{first}.json").exists()
    assert (F / "01-first.json").exists()


def test_backup_upload_failure_does_not_repeat_extraction(
    store, cfg, first, tmp_path, monkeypatch
):
    run(store, cfg)
    key = tmp_path / "key"
    create_key(key)
    create_backup(store, key, tmp_path / "backups")
    cfg["backup"]["remote"] = "test:encrypted"
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: (_ for _ in ()).throw(TimeoutError())
    )
    for _ in range(5):
        upload_backups(store, cfg)
    assert store.db.execute("SELECT attempts FROM artifacts").fetchone()[0] == 3
    assert run(store, cfg) == []
    assert store.get(first)["stage"] == "done"


def test_remote_provider_and_paid_api_require_explicit_configuration(cfg):
    cfg["provider"].update(
        kind="openai-compatible",
        model="candidate",
        base_url="https://inference.invalid/v1",
    )
    with pytest.raises(ValueError, match="Remote"):
        authorize_provider(cfg, "synthetic")
    cfg["provider"]["allow_remote"] = True
    with pytest.raises(ValueError, match="API use"):
        authorize_provider(cfg, "synthetic")
    cfg["provider"]["allow_paid"] = True
    authorize_provider(cfg, "synthetic")
    with pytest.raises(ValueError, match="Clinical"):
        authorize_provider(cfg, "authorized-record")


def test_mock_refuses_real_records(cfg):
    with pytest.raises(ValueError):
        authorize_provider(cfg, "authorized-record")


def test_synthetic_and_clinical_workspaces_cannot_mix(store, first):
    with pytest.raises(ValueError, match="separate workspaces"):
        ingest(
            store,
            F / "02-followup.json",
            "s-other",
            "2026-10-22",
            "authorized-record",
            "permission",
        )


def test_source_authorization_and_valid_offsets_are_required(store):
    with pytest.raises(ValueError):
        ingest(store, F / "01-first.json", "s-test", "2026-10-22", "synthetic", "")
    with pytest.raises(ValueError):
        transcript_valid({"segments": [{"start": 10, "end": 2, "text": "x"}]})
    with pytest.raises(ValueError):
        transcript_valid({"segments": [{"start": float("nan"), "end": 2, "text": "x"}]})


def test_wav_import_full_transcription_adapter_and_stable_offsets(
    store, cfg, tmp_path, monkeypatch
):
    wav = tmp_path / "voice.WAV"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 80000)
    id, created = ingest(store, wav, "s-audio", "2026-10-22", "synthetic", "test")
    assert created

    class Model:
        def __init__(self, *a, **kw):
            assert kw["device"] == "cpu"

        def transcribe(self, *a, **kw):
            return iter(
                [
                    types.SimpleNamespace(
                        start=1.0, end=3.0, text="Synthetic speech.", words=[]
                    )
                ]
            ), types.SimpleNamespace(language="en")

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model)
    )
    cfg["transcription"]["model"] = "test"
    t = transcribe(store, store.get(id), cfg)
    assert t["segments"][0]["start"] == 1.0
    assert wav.exists()
    assert ingest(store, wav, "s-audio", "2026-10-22", "synthetic", "test")[1] is False


def test_truncated_wav_is_not_queued(store, tmp_path):
    wav = tmp_path / "broken.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0" * 16000)
    wav.write_bytes(wav.read_bytes()[:-200])
    with pytest.raises(ValueError, match="Truncated"):
        ingest(store, wav, "s-test", "2026-10-22", "synthetic", "test")
    assert not store.jobs()


def test_workspace_lock_prevents_duplicate_writers(store):
    with lock(store.root):
        with pytest.raises(RuntimeError):
            with lock(store.root):
                pass


def test_targeted_retrieval_never_sends_entire_library(store, cfg, first):
    run(store, cfg)
    context = retrieve(store, load_json(F / "02-followup.json"), 2000)
    assert len(json.dumps(context)) < 2400
    assert any(c["topicKey"] == "fip-reasoning" for c in context)


def test_transcript_chunking_keeps_offsets_and_enforces_limit():
    t = {
        "segments": [
            {"start": 0, "end": 1, "text": "a" * 10},
            {"start": 10, "end": 11, "text": "b" * 10},
        ]
    }
    c = chunks(t, 15)
    assert len(c) == 2 and c[1]["segments"][0]["start"] == 10
    with pytest.raises(ValueError):
        chunks(t, 5)


def test_recovery_rebuilds_deduplication_and_case_continuity(
    store, cfg, first, tmp_path
):
    from vet_pipeline.recovery import recover_library
    from vet_pipeline.store import Store

    run(store, cfg)
    key = tmp_path / "key"
    create_key(key)
    backup = create_backup(store, key, tmp_path / "backups")
    source = tmp_path / "restored"
    restore(backup, key, source)
    fresh = Store(tmp_path / "fresh")
    try:
        recover_library(fresh, source)
        assert current(fresh) == current(store)
        assert (
            ingest(
                fresh,
                F / "01-first.json",
                "s-2026-10-22",
                "2026-10-22",
                "synthetic",
                "test",
            )[1]
            is False
        )
        add(fresh)
        run(fresh, cfg)
        assert len(current(fresh)["cases"]) == 1
    finally:
        fresh.close()


def test_105_independent_files_are_checkpointed_without_105_library_copies(
    store, cfg, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        Provider,
        "extract",
        lambda *a: {"discussions": [], "articles": [], "cases": [], "questions": []},
    )
    for i in range(105):
        file = tmp_path / f"part-{i}.json"
        write_json(
            file,
            {
                "serial": i,
                "segments": [
                    {
                        "start": 0,
                        "end": 1,
                        "text": "Synthetic irrelevant background conversation.",
                    }
                ],
            },
        )
        ingest(store, file, "s-batch", "2026-10-22", "synthetic", "test")
    result = run(store, cfg)
    assert len(result) == 105 and all(x["status"] == "done" for x in result)
    assert len(current(store)["shifts"][0]["recordings"]) == 105
    assert len(list((store.root / "library/snapshots").iterdir())) == 1
    assert run(store, cfg) == []


def test_usb_scan_defers_changing_files_preserves_original_and_uses_hashes(
    store, cfg, tmp_path
):
    from vet_pipeline.automation import scan

    source = tmp_path / "recorder"
    source.mkdir()
    wav = source / "REC001.WAV"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0" * 16000)
    cfg["usb"].update(origin="synthetic", authorization_ref="test", stable_seconds=30)
    assert scan(store, cfg, source, "2026-10-22") == []
    os.utime(wav, (time.time() - 100, time.time() - 100))
    assert scan(store, cfg, source, "2026-10-22")[0]["imported"]
    assert not scan(store, cfg, source, "2026-10-22")[0]["imported"]
    assert wav.exists()


def test_usb_discovery_requires_configured_matching_usb_mount(
    cfg, tmp_path, monkeypatch
):
    from vet_pipeline.automation import discover

    mount = tmp_path / "recorder"
    mount.mkdir()
    (mount / ".approved").touch()
    cfg["usb"].update(
        roots=[str(tmp_path)], device_label="RECORDER", sentinel=".approved"
    )
    output = {
        "blockdevices": [
            {
                "name": "/dev/sdx",
                "tran": "usb",
                "children": [{"label": "RECORDER", "mountpoints": [str(mount)]}],
            },
            {
                "name": "/dev/nvme",
                "tran": "nvme",
                "label": "RECORDER",
                "mountpoints": ["/"],
            },
        ]
    }
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: types.SimpleNamespace(stdout=json.dumps(output)),
    )
    assert discover(cfg) == [mount]
    cfg["usb"]["device_label"] = "OTHER"
    assert discover(cfg) == []


def test_both_provider_protocols_use_structured_requests_without_paid_calls(
    cfg, monkeypatch
):
    import httpx

    t = load_json(F / "01-first.json")
    response = load_json(REPO / "fixtures/pipeline/responses/first.json")
    original = httpx.Client
    seen = []

    def handle(request):
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        if request.url.path == "/api/chat":
            return httpx.Response(
                200, json={"message": {"content": json.dumps(response)}}
            )
        assert request.headers["Authorization"] == "Bearer test-only"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(response)}}]}
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    cfg["provider"].update(kind="ollama", model="candidate")
    assert Provider(cfg).extract(t, [], "synthetic") == response
    monkeypatch.setenv("VET_AI_API_KEY", "test-only")
    cfg["provider"].update(
        kind="openai-compatible", base_url="http://127.0.0.1:9999/v1", allow_paid=True
    )
    assert Provider(cfg).extract(t, [], "synthetic") == response
    assert (
        seen[0][0] == "/api/chat"
        and seen[0][1]["format"]
        == __import__("vet_pipeline.extraction", fromlist=["SCHEMA"]).SCHEMA
    )
    assert seen[1][0] == "/v1/chat/completions"


def test_owner_edits_preserve_ids_and_invalidate_publication_reviews(
    store, cfg, first, tmp_path
):
    from vet_pipeline.editing import apply_edits
    from vet_pipeline.library import write_library

    run(store, cfg)
    before = current(store)
    edited = copy.deepcopy(before)
    edited["articles"][0]["title"] = "An owner-revised title"
    edited["topics"][0]["name"] = "A renamed category"
    folder = tmp_path / "edits"
    write_library(folder, edited)
    result = apply_edits(store, folder)
    assert result["changed_records"] == 1
    assert current(store)["articles"][0]["id"] == before["articles"][0]["id"]
    assert current(store)["articles"][0]["publication"]["status"] == "draft"
    assert read_library(current_root(store)) == current(store)


def test_export_refuses_unrelated_directory(store, cfg, first, tmp_path):
    run(store, cfg)
    review = tmp_path / "review"
    approve_synthetic(store, review)
    target = tmp_path / "important"
    target.mkdir()
    (target / "do-not-overwrite.txt").write_text("keep")
    with pytest.raises(ValueError, match="unrelated"):
        export(store, review, target)
    assert (target / "do-not-overwrite.txt").read_text() == "keep"


def test_unchanged_timer_runs_reuse_verified_local_backup(store, cfg, first, tmp_path):
    from vet_pipeline.backup import backup_if_changed

    run(store, cfg)
    key = tmp_path / "key"
    create_key(key)
    a = backup_if_changed(store, key, tmp_path / "backups")
    b = backup_if_changed(store, key, tmp_path / "backups")
    assert a == b
    add(store)
    run(store, cfg)
    c = backup_if_changed(store, key, tmp_path / "backups")
    assert c != a
    assert a.exists()


def test_remote_upload_confirms_encrypted_bytes_and_retry_reset(
    store, cfg, first, tmp_path, monkeypatch
):
    from vet_pipeline.backup import retry_upload

    run(store, cfg)
    key = tmp_path / "key"
    create_key(key)
    file = create_backup(store, key, tmp_path / "backups")
    cfg["backup"]["remote"] = "test:encrypted"

    def remote(args, **kwargs):
        return types.SimpleNamespace(
            stdout=file.read_bytes() if args[1] == "cat" else b""
        )

    monkeypatch.setattr("subprocess.run", remote)
    assert upload_backups(store, cfg)[0]["status"] == "verified"
    assert upload_backups(store, cfg) == []
    id = store.db.execute("SELECT id FROM artifacts").fetchone()[0]
    retry_upload(store, id)
    assert store.db.execute("SELECT attempts FROM artifacts").fetchone()[0] == 0


def test_corrupted_file_projection_is_rebuilt_before_backup(
    store, cfg, first, tmp_path
):
    run(store, cfg)
    canonical = current(store)
    article = next((current_root(store) / "articles").glob("*.md"))
    article.write_text(
        article.read_text().replace("Source addition", "Corrupted prose")
    )
    assert read_library(current_root(store)) != canonical
    key = tmp_path / "key"
    create_key(key)
    file = create_backup(store, key, tmp_path / "backups")
    assert read_library(current_root(store)) == canonical
    assert inspect_backup(file, key)


def test_model_cannot_approve_questions_or_override_origin(
    store, cfg, first, monkeypatch
):
    original = Provider.extract

    def response(self, *args):
        data = original(self, *args)
        q = data["questions"][0]
        q["origin"] = "authorized-record"
        q["publication"] = {
            "status": "approved",
            "audience": "public",
            "reviewedBy": "model",
            "reviewedAt": "2026-10-22T00:00:00Z",
            "authorizationRef": "invented",
        }
        return data

    monkeypatch.setattr(Provider, "extract", response)
    assert run(store, cfg)[0]["status"] == "done"
    q = current(store)["questions"][0]
    assert q["origin"] == "synthetic"
    assert q["publication"] == {"status": "draft", "audience": "private"}


def test_changed_backup_key_cannot_silently_reuse_old_ciphertext(
    store, cfg, first, tmp_path
):
    from vet_pipeline.backup import backup_if_changed

    run(store, cfg)
    key = tmp_path / "key"
    other = tmp_path / "other-key"
    create_key(key)
    create_key(other)
    backup_if_changed(store, key, tmp_path / "backups")
    with pytest.raises(Exception):
        backup_if_changed(store, other, tmp_path / "backups")
    assert len(list((tmp_path / "backups").glob("*.vkb"))) == 1


def test_quarantine_write_failure_does_not_commit_away_invalid_question(
    store, cfg, first, monkeypatch
):
    import vet_pipeline.library as module

    original = module.write_json

    def fail(path, value):
        if "quarantine" in path.parts:
            raise OSError("disk failure")
        original(path, value)

    monkeypatch.setattr(module, "write_json", fail)
    assert run(store, cfg)[0]["status"] == "failed"
    assert not current(store)["articles"]
    monkeypatch.setattr(module, "write_json", original)
    assert run(store, cfg, True)[0]["status"] == "done"
    assert (store.root / "quarantine" / f"{first}-questions.json").exists()
