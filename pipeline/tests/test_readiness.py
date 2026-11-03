import copy, json, wave
from pathlib import Path
import pytest
from vet_pipeline.budget import messages_budget
from vet_pipeline.config import config
from vet_pipeline.extraction import (
    planned_chunks,
    Provider,
    InputBudgetError,
    extract_recording,
)
from vet_pipeline.grounded import project, source_map
from vet_pipeline.util import REPO, load_json, write_json, digest_file


def test_complete_message_budget_counts_schema_identifiers_and_output():
    p = config()["provider"]
    p.update(
        context_window=512,
        max_output_tokens=100,
        chat_overhead_tokens=20,
        context_safety_tokens=30,
    )
    b = messages_budget(
        [
            {"role": "system", "content": "é"},
            {"role": "user", "content": "schema " + ("e-abcdef " * 60)},
        ],
        p,
    )
    assert b["messages"][0]["tokens"] == 2
    assert not b["fits"]
    assert b["reservedOutputTokens"] == 100 and b["chatAllowance"] == 20


def test_offline_tokenizer_disables_any_saved_truncation(tmp_path):
    from tokenizers import Tokenizer, models, pre_tokenizers

    t = Tokenizer(models.WordLevel({"[UNK]": 0, "a": 1}, unk_token="[UNK]"))
    t.pre_tokenizer = pre_tokenizers.Whitespace()
    t.enable_truncation(2)
    file = tmp_path / "tokenizer.json"
    t.save(str(file))
    p = config()["provider"]
    p.update(tokenizer_path=str(file), tokenizer_sha256=digest_file(file))
    b = messages_budget([{"role": "user", "content": "a " * 20}], p)
    assert b["messages"][0]["tokens"] == 20
    p["tokenizer_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        messages_budget([{"role": "user", "content": "a"}], p)


def test_plans_are_complete_immutable_and_keep_old_boundaries(store, cfg, first):
    cfg["provider"].update(kind="ollama", model="local")
    t = {
        "segments": [
            {
                "start": i * 2,
                "end": i * 2 + 1,
                "text": "Recorded unknown observation. " * 8,
            }
            for i in range(12)
        ]
    }
    chunks = planned_chunks(store, store.get(first), t, cfg, [])
    assert len(chunks) > 1
    assert [s for c in chunks for s in c["segments"]] == t["segments"]
    plan = store.root / "extractions" / first / "chunk-plan.json"
    before = digest_file(plan)
    cfg["provider"]["context_window"] = 32768
    assert planned_chunks(store, store.get(first), t, cfg, []) == chunks
    assert digest_file(plan) == before
    changed = copy.deepcopy(t)
    changed["segments"][0]["text"] = "Changed source"
    with pytest.raises(ValueError, match="differs"):
        planned_chunks(store, store.get(first), changed, cfg, [])


def test_oversize_is_rejected_before_http(cfg, monkeypatch):
    cfg["provider"].update(
        kind="ollama", model="local", context_window=512, max_output_tokens=400
    )
    monkeypatch.setattr(
        "httpx.Client", lambda **kw: pytest.fail("oversized request reached HTTP")
    )
    with pytest.raises(InputBudgetError):
        Provider(cfg).extract(
            {"segments": [{"start": 0, "end": 1, "text": "Unknown."}]}, [], "synthetic"
        )


def test_legacy_good_checkpoint_is_reused_without_repacking(
    store, cfg, first, monkeypatch
):
    t = load_json(REPO / "fixtures/pipeline/transcripts/01-first.json")
    data = Provider(cfg).extract(t, [], "synthetic")
    file = store.root / "extractions" / first / "0000.json"
    write_json(file, data)
    before = digest_file(file)
    monkeypatch.setattr(
        Provider, "extract", lambda *a: pytest.fail("legacy good inference repeated")
    )
    result = extract_recording(store, store.get(first), t, cfg, [])
    assert len(result["discussions"]) == len(data["discussions"])
    assert digest_file(file) == before
    assert load_json(file.parent / "chunk-plan.json")["strategy"] == "legacy-boundaries"


def test_literal_missing_information_is_useful_but_context_stays_unassigned():
    from vet_pipeline.extraction import KIND

    t = {
        "segments": [
            {
                "start": 0,
                "end": 4,
                "text": "A blood sample was collected, but no results are stated.",
            }
        ]
    }
    data, q = project({"discussions": []}, t, [], KIND)
    d = data["discussions"][0]
    assert d["facts"] == [{"kind": "unknown", "text": "no results are stated."}]
    assert d["topics"][0]["id"] == "unclassified-source"
    assert data["cases"] == data["articles"] == []
    assert q["unclassifiedSources"] == 1 and q["deterministicUnknownSources"] == 1


def wav(path, rate=48000, channels=2, seconds=2):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b"\x00\x01" * channels * rate * seconds)


def test_private_evaluation_copy_conversion_and_immutability(tmp_path):
    pytest.importorskip("av")
    from vet_pipeline.evaluation import prepare, session

    source = tmp_path / "recorder.wav"
    wav(source)
    before = digest_file(source)
    root = tmp_path / "private"
    prepare(source, root, "2000-01-01", "synthetic-permission", "synthetic")
    assert digest_file(source) == before
    with wave.open(str(root / "audio/normalized.wav"), "rb") as f:
        assert (
            f.getframerate(),
            f.getnchannels(),
            f.getsampwidth(),
            f.getnframes(),
        ) == (16000, 1, 2, 32000)
    assert (root / ".gitignore").read_text() == "*\n"
    assert not root.stat().st_mode & 0o077
    (root / "audio/normalized.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="audio changed"):
        session(root)


def test_private_workspaces_refuse_both_public_and_private_git_checkouts(tmp_path):
    from vet_pipeline.private import private_path

    checkout = tmp_path / "master"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    (checkout / ".git/HEAD").write_text("ref: refs/heads/main\n")
    with pytest.raises(ValueError, match="every Git"):
        private_path(checkout / "evaluations/run")
    with pytest.raises(ValueError, match="every Git"):
        private_path(REPO / "private-evaluation")


def test_eval_config_refuses_remote_and_local_proxy_routes(tmp_path):
    from vet_pipeline.evaluation import local_config

    for url in [
        "https://example.invalid",
        "http://127.0.0.1:8082",
        "http://localhost:11434/proxy",
    ]:
        f = tmp_path / "config.toml"
        f.write_text(
            '[provider]\nkind="ollama"\nmodel="qwen3:30b"\nbase_url="' + url + '"\n'
        )
        with pytest.raises(ValueError, match="only local"):
            local_config(f)


def test_cloud_backed_model_is_refused_before_receiving_private_text(cfg, monkeypatch):
    import httpx
    from vet_pipeline.evaluation import verified_local_model

    cfg["provider"].update(kind="ollama", model="fake:cloud")
    original = httpx.Client

    def handle(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "fake:cloud",
                        "size": 200000000,
                        "remote_host": "https://remote.invalid",
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    with pytest.raises(ValueError, match="cloud-backed"):
        verified_local_model(cfg)


def test_private_review_html_escapes_text_and_does_not_publish(tmp_path):
    pytest.importorskip("av")
    from vet_pipeline.evaluation import prepare, report_session

    source = tmp_path / "source.wav"
    wav(source, 16000, 1)
    root = tmp_path / "pilot"
    prepare(source, root, "2000-01-01", "test", "synthetic")
    (root / "recollections.md").write_text(
        '<script>fetch("https://leak.invalid")</script>'
    )
    report_session(root)
    text = (root / "review.html").read_text()
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert "script-src 'none'" in text
    assert "audio/original.wav" in text and "audio/normalized.wav" in text
    assert "No clinical accuracy claim" in text


def test_fetch_remote_encrypted_version_authenticates_before_restore(
    store, cfg, first, tmp_path, monkeypatch
):
    from vet_pipeline.runner import run
    from vet_pipeline.backup import create_key, create_backup, fetch_backup, restore
    from vet_pipeline.library import current, read_library
    import subprocess

    run(store, cfg)
    key = tmp_path / "key"
    create_key(key)
    artifact = create_backup(store, key, tmp_path / "backups")
    encrypted = artifact.read_bytes()
    cfg["backup"]["remote"] = "fake:versions"

    def copy(args, **kwargs):
        assert args[1:3] == ["copyto", "--immutable"]
        Path(args[-1]).write_bytes(encrypted)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", copy)
    downloaded = fetch_backup(
        cfg,
        artifact.name,
        key,
        tmp_path / "replacement/version.vkb",
        digest_file(artifact),
    )
    restore(downloaded, key, tmp_path / "replacement/library")
    assert read_library(tmp_path / "replacement/library") == current(store)
    with pytest.raises(ValueError, match="must not exist"):
        fetch_backup(cfg, artifact.name, key, downloaded)
    with pytest.raises(ValueError, match="exact versioned"):
        fetch_backup(cfg, "../backup-bad.vkb", key, tmp_path / "escape.vkb")


def test_cloud_upload_guard_checks_records_even_without_real_jobs(
    store, cfg, first, monkeypatch
):
    from vet_pipeline.runner import run
    from vet_pipeline.backup import upload_backups
    import subprocess

    run(store, cfg)
    row = store.db.execute(
        "SELECT id,data FROM library_records WHERE kind='articles' LIMIT 1"
    ).fetchone()
    data = json.loads(row["data"])
    data["origin"] = "authorized-record"
    with store.db:
        store.db.execute(
            "UPDATE library_records SET data=? WHERE kind='articles' AND id=?",
            (json.dumps(data), row["id"]),
        )
    cfg["backup"]["remote"] = "fake:versions"
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("clinical upload attempted")
    )
    with pytest.raises(ValueError, match="not authorized"):
        upload_backups(store, cfg)


def test_reference_versions_and_asr_integrity_are_separate(tmp_path, monkeypatch):
    pytest.importorskip("av")
    from vet_pipeline.evaluation import prepare, transcribe_session, input_transcript
    from vet_pipeline.config import config

    source = tmp_path / "source.wav"
    wav(source, 16000, 1)
    root = tmp_path / "pilot"
    prepare(source, root, "2000-01-01", "test", "synthetic")
    settings = config()
    settings["provider"].update(kind="ollama", model="qwen3:30b")
    monkeypatch.setattr("vet_pipeline.evaluation.local_config", lambda path: settings)
    monkeypatch.setattr(
        "vet_pipeline.evaluation.transcribe",
        lambda *args: {
            "segments": [{"start": 0, "end": 1, "text": "Outcome unknown."}]
        },
    )
    transcribe_session(root, None)
    with pytest.raises(ValueError, match="manually-corrected"):
        input_transcript(root, "reference")
    ref = load_json(root / "reference.json")
    ref["referenceStatus"] = "manually-corrected"
    ref["segments"][0]["text"] = "Diagnosis unknown."
    write_json(root / "reference.json", ref)
    assert (
        input_transcript(root, "reference")[0]["segments"][0]["text"]
        == "Diagnosis unknown."
    )
    assert input_transcript(root, "asr")[0]["segments"][0]["text"] == "Outcome unknown."
    assert transcribe_session(root, None)["cached"]
    (root / "transcript.json").write_text("{}")
    with pytest.raises(ValueError, match="ASR transcript changed"):
        input_transcript(root, "reference")


def test_private_pilot_records_and_report_survive_cached_replay(tmp_path, monkeypatch):
    pytest.importorskip("av")
    from vet_pipeline.evaluation import prepare, transcribe_session, extract_session

    source = tmp_path / "source.wav"
    wav(source, 16000, 1, seconds=60)
    root = tmp_path / "pilot"
    prepare(source, root, "2000-01-01", "synthetic-test", "synthetic")
    settings = config()
    monkeypatch.setattr("vet_pipeline.evaluation.local_config", lambda path: settings)
    monkeypatch.setattr("vet_pipeline.evaluation.verified_local_model", lambda cfg: "test-digest")
    monkeypatch.setattr("vet_pipeline.evaluation.transcribe", lambda *a: load_json(REPO / "fixtures/pipeline/transcripts/01-first.json"))
    transcribe_session(root, None)
    first = extract_session(root, None)
    assert first["jobsDone"] and first["records"]["articles"] > 0
    result = root / "results" / first["result"]
    before = digest_file(result / "run.json")
    assert extract_session(root, None)["result"] == first["result"]
    assert digest_file(result / "run.json") == before
    assert (result / "editable-library/topics.json").exists()
    review = (root / "review.html").read_text()
    assert first["result"] in review and "Input SHA256" in review
    assert "Article target:" in review and "Study:" in review
    write_json(result / "input.json", {"segments": []})
    with pytest.raises(ValueError, match="Saved extraction input changed"):
        extract_session(root, None)


def test_named_local_backup_remote_is_not_cloud(cfg, tmp_path):
    from vet_pipeline.backup import remote_storage_type

    path = tmp_path / "rclone.conf"
    path.write_text("[named-local]\ntype = local\n[cloud]\ntype = drive\nclient_secret = never-print\n")
    cfg["backup"].update(config_file=str(path), remote="named-local:archive")
    assert remote_storage_type(cfg) == "local"
    cfg["backup"]["remote"] = "cloud:archive"
    assert remote_storage_type(cfg) == "drive"
    cfg["backup"]["remote"] = "unknown:archive"
    assert remote_storage_type(cfg) == "unknown"


def test_compatible_wire_messages_match_preflight_budget(cfg, monkeypatch):
    import httpx

    cfg["provider"].update(kind="openai-compatible", model="test", allow_paid=True,
                            context_window=32768)
    monkeypatch.setenv("VET_AI_API_KEY", "test-only-not-a-credential")
    captured = {}
    original = httpx.Client

    def handle(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"discussions": []}'}, "finish_reason": "stop"}]})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    p = Provider(cfg)
    p.extract({"segments": [{"start": 0, "end": 1, "text": "Outcome unknown."}]}, [], "synthetic")
    assert p.last_budget == messages_budget(captured["messages"], cfg["provider"])
    assert captured["max_tokens"] == cfg["provider"]["max_output_tokens"]
