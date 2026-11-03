from __future__ import annotations
import hashlib, json, os, subprocess, time
from datetime import datetime
from pathlib import Path
from .ingest import ingest
from .util import lock, load_json, write_json


def inventory():
    result = subprocess.run(
        ["lsblk", "--json", "--paths", "--output",
         "NAME,LABEL,UUID,MOUNTPOINTS,TRAN,RM,SERIAL,MODEL"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    found = []
    def walk(items, usb=False, serial=""):
        for item in items:
            is_usb = usb or item.get("tran") == "usb"
            child_serial = item.get("serial") or serial
            if is_usb:
                found.append({**item, "serial": child_serial})
            walk(item.get("children", []), is_usb, child_serial)
    walk(json.loads(result.stdout)["blockdevices"])
    return found


def matches(item, u):
    return all(not u.get(setting) or item.get(field) == u[setting]
               for setting, field in [("device_uuid", "uuid"),
                                      ("device_serial", "serial"), ("device_label", "label")])


def discover(cfg):
    u = cfg["usb"]
    if not u["roots"] or not any(u.get(k) for k in ["device_uuid", "device_serial", "device_label", "sentinel"]):
        return []
    devices = inventory()
    if u["automount_read_only"] and (u["device_uuid"] or u["device_serial"]):
        for item in devices:
            if matches(item, u) and item.get("uuid") and not any(item.get("mountpoints") or []):
                subprocess.run(["udisksctl", "mount", "--block-device", item["name"],
                                "--options", "ro", "--no-user-interaction"],
                               check=True, capture_output=True, timeout=30)
        devices = inventory()
    mounts = []
    for item in devices:
        if not matches(item, u):
            continue
        for mount in item.get("mountpoints") or []:
            if not mount:
                continue
            p = Path(mount).resolve()
            if not any(p == Path(root).resolve() or Path(root).resolve() in p.parents for root in u["roots"]):
                continue
            if u["sentinel"] and not (p / u["sentinel"]).is_file():
                continue
            mounts.append(p)
    return sorted(set(mounts))


def scan(store, cfg, source: Path, date: str, shift_id=None, observed_stability=False):
    u = cfg["usb"]
    if not u["authorization_ref"]:
        raise ValueError(
            "USB importing requires a recording/processing authorization reference"
        )
    if not source.is_dir():
        raise ValueError("Recorder directory is unavailable")
    # Deterministic import ordering only; mtimes remain unverified and never establish actual discussion clock time.
    files = sorted(
        (
            p
            for p in source.glob(u["glob"])
            if p.is_file() and not p.is_symlink() and p.suffix.lower() == ".wav"
        ),
        key=lambda p: (p.stat().st_mtime_ns, str(p.relative_to(source))),
    )
    results = []
    device = hashlib.sha256(str(source).encode()).hexdigest()[:8]
    shift = shift_id or "s-" + date + "-" + device
    with lock(store.root):
        observation_file = store.root / "usb-observations.json"
        observations = load_json(observation_file) if observation_file.exists() else {}
        for path in files:
            try:
                if source.resolve() not in path.resolve().parents:
                    raise ValueError("Path escapes recorder root")
                stat = path.stat()
                if observed_stability:
                    key = str(path.resolve())
                    signature = [stat.st_size, stat.st_mtime_ns]
                    old = observations.get(key, {})
                    if old.get("signature") != signature or old.get("since", 0) > time.time():
                        old = {"signature": signature, "since": time.time()}
                        observations[key] = old
                    if time.time() - old["since"] < u["stable_seconds"]:
                        results.append({"source": str(path.relative_to(source)), "status": "waiting-stable"})
                        continue
                elif time.time() - stat.st_mtime < u["stable_seconds"]:
                    continue
                id, created = ingest(
                    store, path, shift, date, u["origin"], u["authorization_ref"]
                )
                metadata_path = store.root / "source-metadata" / (id + ".json")
                metadata = load_json(metadata_path) if metadata_path.exists() else {}
                occurrence = {"relativePath": str(path.relative_to(source)), "mountAtImport": str(source),
                              "modifiedNs": path.stat().st_mtime_ns, "sizeBytes": path.stat().st_size}
                occurrences = metadata.setdefault("sourceOccurrences", [])
                if occurrence not in occurrences:
                    occurrences.append(occurrence)
                    write_json(metadata_path, metadata)
                results.append({"id": id, "imported": created})
            except Exception as e:
                results.append(
                    {
                        "source": str(path.relative_to(source)),
                        "status": "failed",
                        "error": type(e).__name__,
                    }
                )
        if observed_stability:
            write_json(observation_file, observations)
    return results
