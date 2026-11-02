from __future__ import annotations
import copy, hashlib, json, os, shutil, uuid
from pathlib import Path
from .library import current, validate_library, write_library, GROUPS
from .util import load_json, write_json, now, lock


def record_hash(record):
    return hashlib.sha256(
        json.dumps(
            {k: v for k, v in record.items() if k != "publication"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def review_template(store, output):
    data = current(store)
    review = {
        "schemaVersion": 1,
        "entries": [
            {
                "kind": group,
                "id": e["id"],
                "sha256": record_hash(e),
                "approved": False,
                "privacyReviewed": False,
                "reviewedBy": "",
                "reviewedAt": "",
                "authorizationRef": "",
            }
            for group, entries in data.items()
            if group != "topics"
            for e in entries
        ],
    }
    write_json(output, review)
    return review


def approve_synthetic(store, output):
    lib = current(store)
    if any(
        e["origin"] != "synthetic"
        for group, v in lib.items()
        if group != "topics"
        for e in v
    ):
        raise ValueError("Synthetic approval cannot approve real records")
    review = review_template(store, output)
    for e in review["entries"]:
        e.update(
            approved=True,
            privacyReviewed=True,
            reviewedBy="Synthetic test review",
            reviewedAt=now(),
            authorizationRef="synthetic-test-only",
        )
    write_json(output, review)


def export(store, review_path: Path, target: Path, allow_clinical=False):
    with lock(store.root):
        lib = current(store)
        review = load_json(review_path)
        if review.get("schemaVersion") != 1:
            raise ValueError("Unsupported review version")
        approvals = {(v["kind"], v["id"]): v for v in review["entries"]}
        output = {k: [] for k in GROUPS}
        output["topics"] = copy.deepcopy(lib["topics"])
        for group, entries in lib.items():
            if group == "topics":
                continue
            for e in entries:
                approval = approvals.get((group, e["id"]))
                if not approval or not approval.get("approved"):
                    continue
                if e["origin"] != "synthetic" and not allow_clinical:
                    raise ValueError(
                        "Clinical publication requires explicit --allow-clinical after authorized privacy review"
                    )
                if approval["sha256"] != record_hash(e):
                    raise ValueError("Approval is stale: content changed after review")
                if not approval.get("privacyReviewed") or not all(
                    approval.get(k)
                    for k in ["reviewedBy", "reviewedAt", "authorizationRef"]
                ):
                    raise ValueError(
                        "Approval lacks required authorization/privacy review"
                    )
                e = copy.deepcopy(e)
                # Audit identities and authorization details remain in the private review file.
                e["publication"] = {
                    "status": "approved",
                    "audience": "public",
                    "reviewedBy": "Authorized publication review",
                    "reviewedAt": approval["reviewedAt"],
                    "authorizationRef": "reviewed-export",
                }
                output[group].append(e)
        shifts = {s["id"] for s in output["shifts"]}
        output["discussions"] = [
            d for d in output["discussions"] if d["shiftId"] in shifts
        ]
        ds = {d["id"] for d in output["discussions"]}
        arts = {a["id"] for a in output["articles"]}
        output["cases"] = [
            c for c in output["cases"] if any(x in ds for x in c["sourceDiscussionIds"])
        ]
        cs = {c["id"] for c in output["cases"]}
        for group, entries in output.items():
            for e in entries:
                if "sourceDiscussionIds" in e:
                    e["sourceDiscussionIds"] = [
                        x for x in e["sourceDiscussionIds"] if x in ds
                    ]
                if "articleIds" in e:
                    e["articleIds"] = [x for x in e["articleIds"] if x in arts]
                if "relatedArticleIds" in e:
                    e["relatedArticleIds"] = [
                        x for x in e["relatedArticleIds"] if x in arts
                    ]
                if "caseIds" in e:
                    e["caseIds"] = [x for x in e["caseIds"] if x in cs]
                for f in e.get("facts", []):
                    f["sourceDiscussionIds"] = [
                        x for x in f["sourceDiscussionIds"] if x in ds
                    ]
        output["questions"] = [
            q for q in output["questions"] if q["sourceDiscussionIds"]
        ]
        # Do not expose metadata for recordings with no approved discussion.
        for shift in output["shifts"]:
            rs = {
                s["recordingId"]
                for d in output["discussions"]
                if d["shiftId"] == shift["id"]
                for s in d["segments"]
            }
            shift["recordings"] = [r for r in shift["recordings"] if r["id"] in rs]
        validate_library(output)
        target = target.absolute()
        if target.is_symlink():
            raise ValueError("Export target must be a directory, not a symlink")
        if store.root == target or store.root in target.parents:
            raise ValueError("Export outside the private workspace")
        if target.exists() and set(p.name for p in target.iterdir()) - set(GROUPS) - {
            "topics.json",
            ".gitkeep",
            ".vet-public-export",
        }:
            raise ValueError(
                "Target contains unrelated files; select a dedicated public content directory"
            )
        staged = target.with_name(target.name + ".staged-" + uuid.uuid4().hex)
        write_library(staged, output)
        write_json(staged / ".vet-public-export", {"schemaVersion": 1})
        # Existing exports are retained until explicit operator removal. Never merge stale public records.
        previous = target.with_name(target.name + ".previous")
        if previous.exists():
            if not (previous / ".vet-public-export").exists():
                raise ValueError(
                    "Previous export is not marked as exporter-owned; preserve it and select a clean target"
                )
            shutil.rmtree(previous)
        if target.exists():
            write_json(target / ".vet-public-export", {"schemaVersion": 1})
            os.replace(target, previous)
        try:
            os.replace(staged, target)
        except BaseException:
            if previous.exists():
                os.replace(previous, target)
            raise
        return {k: len(v) for k, v in output.items()}
