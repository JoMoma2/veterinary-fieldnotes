import copy
import json
import pytest
from jsonschema import ValidationError
from vet_pipeline.grounded import request, project, source_map
from vet_pipeline.extraction import KIND, validate_extraction
from vet_pipeline.ingest import ingest
from vet_pipeline.library import commit, current, retrieve


def transcript(
    text="For synthetic case AMBER-TRAINING, the owner reports grooming. Diagnosis unknown.",
):
    return {"segments": [{"start": 1.25, "end": 8.75, "text": text}]}


def lesson(t, **changes):
    token = next(iter(source_map(t)))
    row = {
        "title": "Recorded observations",
        "sources": [token],
        "topic": "new",
        "newTopic": "Grooming observations",
        "facts": [
            {
                "source": token,
                "kind": "unknown",
                "quote": t["segments"][0]["text"],
                "question": "What was recorded?",
            }
        ],
        "isCase": True,
        "caseLabel": "AMBER-TRAINING",
        "species": "Unknown",
    }
    return {**row, **changes}


def save(store, tmp_path, t, data, name):
    f = tmp_path / (name + ".json")
    f.write_text(json.dumps(t))
    id, _ = ingest(store, f, "s-test", "2000-01-01", "synthetic", "test")
    validate_extraction(data, t)
    commit(store, store.get(id), t, data)
    store.update(id, stage="done")


def test_program_assigns_identifiers_times_and_flashcard_links():
    t = transcript()
    schema, payload = request(t, [], KIND)
    assert "start" not in json.dumps(schema)
    assert "localId" not in json.dumps(schema)
    data, quality = project({"discussions": [lesson(t)]}, t, [], KIND)
    validate_extraction(data, t)
    d = data["discussions"][0]
    q = data["questions"][0]
    assert d["quotes"] == t["segments"]
    assert d["localId"] == "g1" and q["sourceDiscussionIds"] == ["g1"]
    assert q["answer"] == d["facts"][0]["text"]
    assert quality["classifiedSources"] == 1
    assert data["cases"][0]["diagnosis"] is None


def test_model_cannot_add_a_source_id_or_timestamp():
    t = transcript()
    raw = {"discussions": [lesson(t)]}
    raw["discussions"][0]["sources"] = ["made-up"]
    with pytest.raises(ValidationError):
        project(raw, t, [], KIND)
    raw = {"discussions": [lesson(t, start=999)]}
    with pytest.raises(ValidationError):
        project(raw, t, [], KIND)


def test_ungrounded_fact_is_quarantined_and_original_is_preserved():
    t = transcript()
    row = lesson(t)
    row["facts"][0]["quote"] = "Confirmed diagnosis: FIP"
    data, quality = project({"discussions": [row]}, t, [], KIND)
    validate_extraction(data, t)
    assert quality["unclassifiedSources"] == 1 and quality["warnings"]
    assert data["articles"] == data["cases"] == data["questions"] == []
    assert data["discussions"][0]["facts"] == []
    assert t["segments"][0]["text"] in data["discussions"][0]["account"]


def test_empty_model_response_cannot_silently_discard_source():
    t = transcript()
    data, quality = project({"discussions": []}, t, [], KIND)
    assert quality["unclassifiedSources"] == 1
    assert len(data["discussions"]) == 1
    assert data["discussions"][0]["title"].startswith("Unclassified")


def test_negative_case_relationship_is_not_associated():
    t = transcript(
        "Returning to a different dog, not case AMBER-TRAINING. Diagnosis unknown."
    )
    data, quality = project({"discussions": [lesson(t)]}, t, [], KIND)
    validate_extraction(data, t)
    assert data["cases"][0]["caseKey"].startswith("unlinked-e-")
    assert quality["warnings"]


def test_anonymous_patient_cannot_link_across_recordings(store, tmp_path):
    t = transcript("Returning to an unidentified dog. Diagnosis unknown.")
    row = lesson(t, caseLabel=None)
    data, _ = project({"discussions": [row]}, t, [], KIND)
    save(store, tmp_path, t, data, "first")
    # Distinct files with the same excerpt are still different unidentified patients.
    t2 = {**t, "importNote": "different recording"}
    save(store, tmp_path, t2, data, "second")
    assert len(current(store)["cases"]) == 2


def test_literal_label_case_and_whitespace_variants_require_continuation(
    store, tmp_path
):
    t = transcript("For synthetic case amber training, diagnosis unknown.")
    data, _ = project(
        {"discussions": [lesson(t, caseLabel="amber training")]}, t, [], KIND
    )
    save(store, tmp_path, t, data, "first")
    t2 = transcript("Returning to case AMBER-TRAINING: outcome unknown.")
    data2, _ = project({"discussions": [lesson(t2)]}, t2, [], KIND)
    save(store, tmp_path, t2, data2, "second")
    assert len(current(store)["cases"]) == 1
    assert len(current(store)["cases"][0]["sourceDiscussionIds"]) == 2


def test_repeated_label_without_continuation_is_separate(store, tmp_path):
    t = transcript()
    data, _ = project({"discussions": [lesson(t)]}, t, [], KIND)
    save(store, tmp_path, t, data, "first")
    t2 = transcript("For case AMBER-TRAINING, a new report states outcome unknown.")
    data2, _ = project({"discussions": [lesson(t2)]}, t2, [], KIND)
    save(store, tmp_path, t2, data2, "second")
    assert len(current(store)["cases"]) == 2


def test_prior_content_is_only_a_topic_index_and_additions_preserve_body(
    store, tmp_path
):
    t = transcript()
    data, _ = project({"discussions": [lesson(t)]}, t, [], KIND)
    save(store, tmp_path, t, data, "first")
    before = current(store)["articles"][0]["body"]
    context = retrieve(store, t, 6000)
    context[0]["body"] = "PRIVATE_OLD_CONTENT_DO_NOT_COPY"
    _, payload = request(t, context, KIND)
    assert "PRIVATE_OLD_CONTENT" not in json.dumps(payload)
    key = next(v["topicKey"] for v in context if v["kind"] == "article")
    t2 = transcript(
        "Returning to case AMBER-TRAINING: grooming was reported; outcome unknown."
    )
    row = lesson(t2, topic=key, newTopic="")
    data2, _ = project({"discussions": [row]}, t2, context, KIND)
    save(store, tmp_path, t2, data2, "second")
    assert len(current(store)["articles"]) == 1
    assert current(store)["articles"][0]["body"].startswith(before)


def test_explicit_separate_topics_cannot_be_grouped():
    t = transcript()
    t["segments"].append(
        {
            "start": 9,
            "end": 12,
            "text": "Separate teaching topic: no result is available.",
        }
    )
    row = lesson(t)
    row["sources"] = list(source_map(t))
    data, quality = project({"discussions": [row]}, t, [], KIND)
    assert quality["unclassifiedSources"] == 2
    assert data["cases"] == []


def test_case_only_quote_repair_uses_original_source_wording():
    t = transcript()
    row = lesson(t)
    row["facts"][0]["quote"] = t["segments"][0]["text"].upper()
    data, quality = project({"discussions": [row]}, t, [], KIND)
    assert data["discussions"][0]["facts"][0]["text"] == t["segments"][0]["text"]
    assert quality["repairs"][0]["kind"] == "unique casing/whitespace citation repair"


def test_quote_repair_cannot_change_numbers_or_negation():
    t = transcript(
        "For case AMBER-TRAINING, lactate 4.2. Administration was not documented."
    )
    row = lesson(t)
    row["facts"][0]["quote"] = "lactate 42"
    data, quality = project({"discussions": [row]}, t, [], KIND)
    assert quality["unclassifiedSources"] == 1
    assert data["articles"] == []
    assert "Administration was not documented" in data["discussions"][0]["account"]


def test_ambiguous_case_only_quote_repair_is_not_guessed():
    t = transcript("Diagnosis unknown. diagnosis unknown.")
    row = lesson(t, isCase=False, caseLabel=None)
    row["facts"][0]["quote"] = "DIAGNOSIS UNKNOWN."
    data, quality = project({"discussions": [row]}, t, [], KIND)
    assert quality["unclassifiedSources"] == 1


def test_uncertain_diagnosis_and_proposal_cannot_become_confirmed_treatment():
    t = transcript(
        "For case AMBER-TRAINING, obstruction is a concern, not confirmed. Norepinephrine was proposed."
    )
    row = lesson(t)
    token = row["sources"][0]
    row["facts"] = [
        {
            "source": token,
            "kind": "confirmed-diagnosis",
            "quote": "obstruction is a concern, not confirmed.",
            "question": "",
        },
        {
            "source": token,
            "kind": "actual-treatment",
            "quote": "Norepinephrine was proposed.",
            "question": "",
        },
    ]
    data, quality = project({"discussions": [row]}, t, [], KIND)
    assert [f["kind"] for f in data["discussions"][0]["facts"]] == [
        "clinical-suspicion",
        "proposed-treatment",
    ]
    assert data["cases"][0]["diagnosis"] is None
    assert len(quality["repairs"]) == 2


def test_existing_unique_acronym_topic_is_reused():
    t = transcript("FIP remains a differential, not a diagnosis.")
    row = lesson(t, caseLabel=None, isCase=False, newTopic="FIP teaching clarification")
    context = [
        {
            "kind": "article",
            "topicKey": "fip",
            "title": "Feline infectious peritonitis (FIP)",
            "body": "DO_NOT_COPY",
        }
    ]
    data, quality = project({"discussions": [row]}, t, context, KIND)
    assert data["articles"][0]["topicKey"] == "fip"
    assert "DO_NOT_COPY" not in data["articles"][0]["bodyAddition"]


def test_unrelated_existing_topic_cannot_absorb_equipment_instruction():
    t = {
        "segments": [
            {"start": 0, "end": 4, "text": "Pump training was discussed."},
            {"start": 5, "end": 9, "text": "Identify the ultrasound connector."},
        ]
    }
    row = lesson(
        t,
        caseLabel=None,
        isCase=False,
        topic="pump",
        newTopic="",
        title="Ultrasound connector",
    )
    token = list(source_map(t))[1]
    row["sources"] = [token]
    row["facts"][0].update(source=token, quote=t["segments"][1]["text"])
    context = [
        {"kind": "article", "topicKey": "pump", "title": "Classroom pump exercise"}
    ]
    data, quality = project({"discussions": [row]}, t, context, KIND)
    assert data["articles"][0]["topicKey"] == "ultrasound-connector"
    assert any(
        r["kind"] == "unrelated topic binding prevented" for r in quality["repairs"]
    )


def test_low_context_budget_is_explicit_instead_of_silent_truncation(store, cfg, first):
    from vet_pipeline.extraction import extract_recording

    cfg["provider"].update(
        kind="ollama", model="not-called", context_window=2048, max_output_tokens=2048
    )
    with pytest.raises(ValueError, match="Insufficient context budget"):
        extract_recording(store, store.get(first), transcript(), cfg, [])


def test_coarse_utterance_alignment_reports_actual_offset():
    from vet_pipeline.audio_benchmark import utterance_alignment

    text = "The owner reported repeated grooming and unknown urine volume."
    result = utterance_alignment(
        [{"start": 1.1, "text": text}],
        {"segments": [{"start": 1.25, "end": 5, "text": text}]},
    )
    assert result["meanAbsoluteStartErrorSeconds"] == pytest.approx(0.15)


def test_output_limit_split_survives_interruption_without_repeating_good_child(
    store, cfg, first, monkeypatch
):
    from vet_pipeline.extraction import Provider, OutputLimitError, extract_recording
    from vet_pipeline.util import digest_file

    t = {
        "segments": [
            {"start": 0, "end": 2, "text": "First recorded fact."},
            {"start": 3, "end": 5, "text": "Second recorded fact."},
        ]
    }
    calls = []
    interrupted = False

    def infer(self, chunk, *args):
        nonlocal interrupted
        calls.append(
            len(chunk["segments"])
            if len(chunk["segments"]) > 1
            else chunk["segments"][0]["text"]
        )
        if len(chunk["segments"]) > 1:
            raise OutputLimitError("bounded test limit")
        if chunk["segments"][0]["start"] == 3 and not interrupted:
            interrupted = True
            raise KeyboardInterrupt()
        return {
            "discussions": [
                {
                    "localId": "part",
                    "title": "Source account",
                    "topics": [{"id": "source", "name": "Source"}],
                    "quotes": chunk["segments"],
                    "account": chunk["segments"][0]["text"],
                    "facts": [],
                    "questions": [],
                    "conclusions": "Unknown",
                }
            ],
            "articles": [],
            "cases": [],
            "questions": [],
        }

    monkeypatch.setattr(Provider, "extract", infer)
    with pytest.raises(KeyboardInterrupt):
        extract_recording(store, store.get(first), t, cfg, [])
    good = store.root / "extractions" / first / "0000-a.json"
    before = digest_file(good)
    data = extract_recording(store, store.get(first), t, cfg, [])
    assert digest_file(good) == before
    assert calls == [
        2,
        "First recorded fact.",
        "Second recorded fact.",
        "Second recorded fact.",
    ]
    assert len({d["localId"] for d in data["discussions"]}) == 2
    validate_extraction(data, t)


def test_adaptive_output_splitting_is_bounded(store, cfg, first, monkeypatch):
    from vet_pipeline.extraction import Provider, OutputLimitError, extract_recording

    t = {
        "segments": [
            {"start": i * 2, "end": i * 2 + 1, "text": "Synthetic source."}
            for i in range(8)
        ]
    }
    calls = []

    def fail(self, chunk, *args):
        calls.append(len(chunk["segments"]))
        raise OutputLimitError("bounded test limit")

    monkeypatch.setattr(Provider, "extract", fail)
    with pytest.raises(OutputLimitError):
        extract_recording(store, store.get(first), t, cfg, [])
    assert calls == [8, 4, 2]


def test_species_cannot_be_inferred_from_substrings_like_catheter():
    t = transcript("For case AMBER-TRAINING, a catheter was placed. Species unknown.")
    data, _ = project({"discussions": [lesson(t, species="cat")]}, t, [], KIND)
    assert data["cases"][0]["species"] == "Unknown"


def test_legacy_case_keys_keep_existing_case_identifiers(store, tmp_path):
    t = transcript()
    data, _ = project({"discussions": [lesson(t)]}, t, [], KIND)
    save(store, tmp_path, t, data, "first")
    existing = current(store)["cases"][0]["id"]
    with store.db:
        store.db.execute("DELETE FROM case_keys")
        store.db.execute(
            "INSERT INTO case_keys VALUES(?,?)", ("s-test:AMBER-TRAINING", existing)
        )
    t2 = transcript("Returning to case amber training, outcome unknown.")
    d2, _ = project(
        {"discussions": [lesson(t2, caseLabel="amber training")]}, t2, [], KIND
    )
    save(store, tmp_path, t2, d2, "second")
    assert [c["id"] for c in current(store)["cases"]] == [existing]


def test_unclassified_and_model_discussions_remain_chronological():
    t = {
        "segments": [
            {"start": 0, "end": 4, "text": "Earlier observation."},
            {"start": 5, "end": 9, "text": "Later observation."},
        ]
    }
    row = lesson(t, caseLabel=None, isCase=False)
    token = list(source_map(t))[1]
    row["sources"] = [token]
    row["facts"][0].update(source=token, quote=t["segments"][1]["text"])
    data, _ = project({"discussions": [row]}, t, [], KIND)
    assert [d["quotes"][0]["start"] for d in data["discussions"]] == [0, 5]
    validate_extraction(data, t)
