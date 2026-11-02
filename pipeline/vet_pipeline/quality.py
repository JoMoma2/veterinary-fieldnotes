"""Inspectable ground-truth screens. These are not semantic/clinical accuracy scores."""

from __future__ import annotations
import re
from .util import atomic_write


def normalized(text):
    return " ".join(re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower()))


def fact_screen(data, gold, transcript):
    results = []
    for expected in gold.get("facts", []):
        segment = transcript["segments"][expected["segment"]]
        candidates = []
        in_account = False
        for discussion in data["discussions"]:
            # Correct-looking IDs alone do not establish a correct source link.
            if not any(
                q["start"] == segment["start"]
                and q["end"] == segment["end"]
                and expected["quote"] in q["text"]
                for q in discussion["quotes"]
            ):
                continue
            if not discussion["localId"].startswith("unclassified-") and normalized(
                expected["quote"]
            ) in normalized(discussion["account"]):
                in_account = True
            for fact in discussion["facts"]:
                if normalized(expected["quote"]) in normalized(fact["text"]):
                    candidates.append(
                        {
                            "kind": fact["kind"],
                            "text": fact["text"],
                            "discussion": discussion["localId"],
                        }
                    )
        correct = any(f["kind"] in expected["kinds"] for f in candidates)
        results.append(
            {
                **expected,
                "status": "captured-with-source-and-kind"
                if correct
                else "evidence-kind-mismatch"
                if candidates
                else "not-matched",
                "matches": candidates,
                "preservedInAccount": in_account,
            }
        )
    association_flags = []
    expected_cases = gold.get("expected_case_sources", {})
    if "expected_case_sources" in gold:
        for case in data["cases"]:
            if case["caseKey"].startswith("unlinked-e-"):
                continue
            allowed = expected_cases.get(case["caseKey"])
            if allowed is None:
                association_flags.append(
                    "Unexpected case association: " + case["caseKey"]
                )
                continue
            valid = {
                (transcript["segments"][i]["start"], transcript["segments"][i]["end"])
                for i in allowed
            }
            for d in data["discussions"]:
                if d["localId"] in case["discussionIds"] and any(
                    (q["start"], q["end"]) not in valid for q in d["quotes"]
                ):
                    association_flags.append(
                        "Case includes unrelated source: " + case["caseKey"]
                    )
    return {
        "expectedFactCount": len(results),
        "matchedFactCount": sum(
            f["status"] == "captured-with-source-and-kind" for f in results
        ),
        "kindMismatchCount": sum(
            f["status"] == "evidence-kind-mismatch" for f in results
        ),
        "accountPreservedFactCount": sum(f["preservedInAccount"] for f in results),
        "factComparisons": results,
        "caseAssociationFlags": association_flags,
        "limitation": "Strict extractive-clause/source/type screen, not semantic accuracy. Partial clauses may be undercounted; omissions, narrative hallucinations and question quality require human review.",
    }


def review_markdown(report, path):
    lines = [
        "# Local extraction comparison",
        "",
        f"Model: `{report['model']}`. Protocol: `{report.get('extractionProtocol', 'legacy')}`.",
        "",
        "PRIVATE BENCHMARK ARTIFACT. Automated matching is not medical accuracy. Read the actual accounts, evidence and questions. No fact is externally verified.",
        "",
    ]
    for row in report["results"]:
        lines += [
            "## " + row["input"],
            "",
            f"Structural acceptance: {row['valid']}; wall time: {row['seconds']} s.",
            "",
        ]
        if not row["valid"]:
            lines += [f"Rejected: {row.get('reason', row.get('error'))}", ""]
        quality = row.get("extractionQuality", {})
        if quality:
            lines += [
                f"Sources classified: {quality.get('classifiedSources')}/{quality.get('inputSources')}; preserved unclassified: {quality.get('unclassifiedSources')}.",
                "",
            ]
        screen = row.get("factScreen", {})
        if screen:
            lines += [
                f"Strict source/type matches: {screen['matchedFactCount']}/{screen['expectedFactCount']}; kind mismatches: {screen['kindMismatchCount']}.",
                "",
                f"Expected clauses present in classified source accounts: {screen.get('accountPreservedFactCount')}/{screen['expectedFactCount']}. This includes source wording, not a semantic accuracy score.",
                "",
                "| Expected recorded fact | Acceptable kinds | Screen |",
                "| --- | --- | --- |",
            ]
            lines += [
                f"| {f['quote'].replace('|', '/')} | {', '.join(f['kinds'])} | {f['status']} |"
                for f in screen["factComparisons"]
            ]
            lines += [
                "",
                "Case-association flags: " + str(screen["caseAssociationFlags"]),
                "",
            ]
        for discussion in row.get("output", {}).get("discussions", []):
            lines += ["### " + discussion["title"], "", discussion["account"], ""]
            lines += [f"- **{f['kind']}**: {f['text']}" for f in discussion["facts"]]
            lines += ["", "Evidence:", ""]
            lines += [
                f"> [{q['start']}–{q['end']}] {q['text']}" for q in discussion["quotes"]
            ]
            lines += [""]
        for q in row.get("output", {}).get("questions", []):
            lines += [
                "Question: " + q.get("prompt", ""),
                "",
                "Answer: " + q.get("answer", str(q.get("correct", ""))),
                "",
            ]
        for c in row.get("output", {}).get("cases", []):
            lines += [
                f"Case: {c['caseKey']} / {c['species']}; diagnosis: {c['diagnosis'] or 'Unknown'}; outcome: {c['outcome'] or 'Unknown'}.",
                "",
                "Discussion links: " + ", ".join(c["discussionIds"]),
                "",
                "Link evidence: " + c["linkEvidence"],
                "",
            ]
        for a in row.get("output", {}).get("articles", []):
            lines += [
                f"Article target: {a['topicKey']} — {a['title']}; sources: {', '.join(a['discussionIds'])}",
                "",
            ]
    atomic_write(path, "\n".join(lines) + "\n")
