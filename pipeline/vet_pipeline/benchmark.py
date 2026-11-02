from __future__ import annotations
import hashlib
import json
import tempfile
import time
from pathlib import Path

from .extraction import Provider, validate_extraction, PROMPT, SCHEMA
from .hardware import ResourceSampler, inventory
from .ingest import ingest, transcript_valid
from .library import current, commit, retrieve
from .store import Store
from .util import load_json, write_json, now, digest_file


def score_output(data, gold):
    # Quoted transcript text is deliberately excluded: copying a quote is not extraction completeness.
    claims = " ".join(
        [
            d["account"]
            + " "
            + d["conclusions"]
            + " "
            + " ".join(f["text"] for f in d["facts"])
            for d in data["discussions"]
        ]
        + [a["bodyAddition"] for a in data["articles"]]
    ).lower()
    expected = gold.get("must_capture", [])
    captured = [s for s in expected if s.lower() in claims]
    missed = [s for s in expected if s.lower() not in claims]
    flags = []
    for field in gold.get("must_remain_unknown", []):
        if any(c.get(field) is not None for c in data["cases"]):
            flags.append("Unexpected non-null case " + field)
    for kind in gold.get("unsupported_evidence_kinds", []):
        if any(f["kind"] == kind for d in data["discussions"] for f in d["facts"]):
            flags.append("Unsupported evidence kind " + kind)
    for word in gold.get("must_not_assert", []):
        if word.lower() in claims:
            flags.append("Forbidden assertion marker: " + word)
    terms = gold.get("terminology", [])
    return {
        "captured_markers": captured,
        "missed_markers": missed,
        "lexical_capture_fraction": len(captured) / len(expected) if expected else None,
        "hallucination_review_flags": flags,
        "terminology_present": [t for t in terms if t.lower() in claims],
        "terminology_missing": [t for t in terms if t.lower() not in claims],
        "screening_limit": "Lexical/type checks are review aids. Paraphrases, negation, factual correctness, and semantic hallucinations need human adjudication.",
    }


def benchmark(cfg, inputs, output, origin="synthetic", authorization_ref=""):
    if origin == "authorized-record" and not authorization_ref:
        raise ValueError(
            "Authorized benchmark requires a recording/processing authorization reference"
        )
    hardware = inventory()
    rows = []
    with tempfile.TemporaryDirectory(prefix="vet-benchmark-") as tmp:
        store = Store(Path(tmp) / "private")
        try:
            for file in inputs:
                start = time.monotonic()
                provider = Provider(cfg)
                row = {"input": file.name}
                with ResourceSampler() as resources:
                    try:
                        t = transcript_valid(load_json(file))
                        if (
                            sum(len(s["text"]) for s in t["segments"])
                            > cfg["provider"]["transcript_char_limit"]
                        ):
                            raise ValueError(
                                "Benchmark transcript exceeds configured input budget"
                            )
                        job_id, _ = ingest(
                            store,
                            file,
                            "s-benchmark",
                            "2000-01-01",
                            origin,
                            authorization_ref or "synthetic-benchmark",
                        )
                        before = {
                            a["id"]: a["body"] for a in current(store)["articles"]
                        }
                        context = retrieve(
                            store, t, cfg["provider"]["context_char_limit"]
                        )
                        inference_start = time.monotonic()
                        data = provider.extract(t, context, origin)
                        inference_seconds = time.monotonic() - inference_start
                        # Retain structured responses and timing even when validation rejects them.
                        # Reports are private artifacts, never website content.
                        row.update(
                            output=data,
                            providerMetrics=provider.last_metrics,
                            inferenceSeconds=round(inference_seconds, 3),
                        )
                        validate_extraction(data, t)
                        commit(store, store.get(job_id), t, data)
                        store.update(job_id, stage="done")
                        after = current(store)
                        if any(
                            not next(
                                a["body"] for a in after["articles"] if a["id"] == id
                            ).startswith(body)
                            for id, body in before.items()
                        ):
                            raise ValueError(
                                "Benchmark detected destructive article update"
                            )
                        gold_file = file.with_suffix(".expected.json")
                        gold = load_json(gold_file) if gold_file.exists() else {}
                        row.update(
                            valid=True,
                            inputSha256=digest_file(file),
                            inferenceSeconds=round(inference_seconds, 3),
                            retrievedContextIds=[x["id"] for x in context],
                            providerMetrics=provider.last_metrics,
                            consolidation={
                                "articlesAfter": len(after["articles"]),
                                "casesAfter": len(after["cases"]),
                                "earlierArticleTextPreserved": True,
                                "caseCountMatchesExpectation": len(after["cases"])
                                == gold["expected_cases_after"]
                                if "expected_cases_after" in gold
                                else None,
                            },
                            output=data,
                            **score_output(data, gold),
                        )
                    except Exception as e:
                        row.update(valid=False, error=type(e).__name__)
                        row.setdefault("providerMetrics", provider.last_metrics)
                        if "output" not in row and provider.last_content is not None:
                            row["rawResponse"] = provider.last_content
                        if type(e) is ValueError:
                            row["reason"] = str(e)
                row["seconds"] = round(time.monotonic() - start, 3)
                row["hardwareUtilization"] = resources.summary()
                row["manual_review"] = {
                    "important_information_captured": None,
                    "important_information_missed": None,
                    "invented_details": None,
                    "clinical_terminology": None,
                    "case_linking": None,
                    "safe_additive_updates": None,
                    "reviewer": None,
                }
                rows.append(row)
        finally:
            store.close()
    report = {
        "schemaVersion": 2,
        "at": now(),
        "provider": cfg["provider"]["kind"],
        "model": cfg["provider"]["model"],
        "generation": {
            k: cfg["provider"][k]
            for k in ["context_window", "max_output_tokens", "thinking", "keep_alive"]
        },
        "promptContractSha256": hashlib.sha256(
            (
                "schema-in-prompt-v1\n" + PROMPT + json.dumps(SCHEMA, sort_keys=True)
            ).encode()
        ).hexdigest(),
        "schemaIncludedInPrompt": True,
        "hardware": hardware,
        "origin": origin,
        "warning": "Screening metrics are not clinical accuracy scores. Human review is required. No 90% capture claim is implied. Results include private model output; keep authorized-record reports outside the public repository.",
        "results": rows,
    }
    write_json(output, report)
    return report
