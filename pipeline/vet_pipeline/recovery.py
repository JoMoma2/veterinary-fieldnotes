from __future__ import annotations
import json
import hashlib
from pathlib import Path
from .library import read_library, validate_library, materialize
from .util import load_json, lock, now


def verify_snapshot(source: Path):
    lib = validate_library(read_library(source))
    manifest = load_json(source / "manifest.json")
    actual = hashlib.sha256(
        json.dumps(lib, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if manifest.get("contentHash") != actual:
        raise ValueError(
            "Recovery snapshot content does not match its integrity manifest"
        )
    recording_ids = {r["id"] for shift in lib["shifts"] for r in shift["recordings"]}
    if set(manifest.get("applied", [])) != recording_ids:
        raise ValueError("Recovery snapshot is missing completed-recording checkpoints")
    cases = {c["id"] for c in lib["cases"]}
    if not set(manifest.get("caseKeys", {}).values()) <= cases:
        raise ValueError("Recovery snapshot has invalid case continuity references")
    return lib, manifest


def recover_library(store, source: Path):
    with lock(store.root):
        if (
            store.jobs()
            or store.db.execute("SELECT COUNT(*) FROM library_records").fetchone()[0]
        ):
            raise ValueError("Recover into a new, empty workspace")
        lib, manifest = verify_snapshot(source)
        with store.db:
            for group, entries in lib.items():
                for e in entries:
                    store.db.execute(
                        "INSERT INTO library_records VALUES(?,?,?)",
                        (
                            group,
                            e["id"],
                            json.dumps(e, sort_keys=True, ensure_ascii=False),
                        ),
                    )
            for id in manifest["applied"]:
                store.db.execute("INSERT INTO applied_recordings VALUES(?)", (id,))
            for key, id in manifest.get("caseKeys", {}).items():
                store.db.execute("INSERT INTO case_keys VALUES(?,?)", (key, id))
            for shift in lib["shifts"]:
                for r in shift["recordings"]:
                    if not r.get("sourceSha256"):
                        raise ValueError(
                            "Recording hash required to restore duplicate detection"
                        )
                    store.db.execute(
                        "INSERT INTO jobs(id,sha256,shift_id,shift_date,origin,authorization_ref,source_name,source_mtime,source_kind,sequence,stage,created_at,completed_at,cleaned) VALUES(?,?,?,?,?,?,?,?,?,?,'done',?,?,1)",
                        (
                            r["id"],
                            r["sourceSha256"],
                            shift["id"],
                            shift["date"],
                            shift["origin"],
                            "restored-authorized-archive",
                            "restored-recording",
                            0,
                            "transcript",
                            r["sequence"],
                            now(),
                            now(),
                        ),
                    )
        materialize(store)
        return {
            "restored_records": sum(map(len, lib.values())),
            "completed_recordings": len(store.jobs()),
        }
