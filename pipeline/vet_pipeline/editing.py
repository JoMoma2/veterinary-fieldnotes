from __future__ import annotations
import json
from .library import current, read_library, validate_library, materialize
from .publication import record_hash
from .util import lock


def apply_edits(store, source):
    with lock(store.root):
        previous = current(store)
        edited = validate_library(read_library(source))
        changed = 0
        for group, entries in previous.items():
            if group == "topics":
                continue  # Categories may be reorganized once all references remain valid.
            if not {e["id"] for e in entries} <= {e["id"] for e in edited[group]}:
                raise ValueError(
                    "Stable knowledge/case/discussion IDs cannot be removed by an edit"
                )
        old = {
            (group, e["id"]): e for group, entries in previous.items() for e in entries
        }
        for group, entries in edited.items():
            for e in entries:
                before = old.get((group, e["id"]))
                if group != "topics" and (
                    before is None or record_hash(before) != record_hash(e)
                ):
                    e["publication"] = {"status": "draft", "audience": "private"}
                    changed += 1
        with store.db:
            store.db.execute("DELETE FROM library_records")
            for group, entries in edited.items():
                for e in entries:
                    store.db.execute(
                        "INSERT INTO library_records VALUES(?,?,?)",
                        (
                            group,
                            e["id"],
                            json.dumps(e, sort_keys=True, ensure_ascii=False),
                        ),
                    )
        materialize(store)
        return {"changed_records": changed, "review_required": True}
