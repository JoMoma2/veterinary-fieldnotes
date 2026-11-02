from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime
from pathlib import Path
from .config import config
from .store import Store
from .util import lock


def main():
    p = argparse.ArgumentParser(
        description="Veterinary Fieldnotes local processing and publication"
    )
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path(
            os.environ.get("VET_WORKSPACE", Path.home() / ".local/share/vet-fieldnotes")
        ),
    )
    p.add_argument("--config", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("ingest")
    a.add_argument("paths", nargs="+", type=Path)
    a.add_argument("--shift", required=True)
    a.add_argument("--date", required=True)
    a.add_argument(
        "--origin", choices=["synthetic", "authorized-record"], required=True
    )
    a.add_argument("--authorization-ref", required=True)
    a = sub.add_parser("run")
    a.add_argument("--force-retry", action="store_true")
    sub.add_parser("status")
    a = sub.add_parser("retry")
    a.add_argument("id")
    a = sub.add_parser("review-template")
    a.add_argument("output", type=Path)
    a = sub.add_parser("approve-synthetic")
    a.add_argument("output", type=Path)
    a = sub.add_parser("export")
    a.add_argument("--review", required=True, type=Path)
    a.add_argument("--target", required=True, type=Path)
    a.add_argument("--allow-clinical", action="store_true")
    a = sub.add_parser("backup-key")
    a.add_argument("path", type=Path)
    a = sub.add_parser("backup")
    a.add_argument("--key", required=True, type=Path)
    a.add_argument("--destination", required=True, type=Path)
    a = sub.add_parser("restore")
    a.add_argument("backup", type=Path)
    a.add_argument("--key", required=True, type=Path)
    a.add_argument("--target", required=True, type=Path)
    a = sub.add_parser("apply-edits")
    a.add_argument("--source", required=True, type=Path)
    a = sub.add_parser("recover-library")
    a.add_argument("--source", required=True, type=Path)
    a = sub.add_parser("retry-upload")
    a.add_argument("id")
    sub.add_parser("upload")
    a = sub.add_parser("cleanup")
    a.add_argument("--apply", action="store_true")
    a = sub.add_parser("scan")
    a.add_argument("--source", type=Path)
    a.add_argument("--date", default=datetime.now().date().isoformat())
    a = sub.add_parser("nightly")
    a.add_argument("--date", default=datetime.now().date().isoformat())
    a.add_argument("--key", type=Path)
    a.add_argument("--backup-directory", type=Path)
    a = sub.add_parser("sync-master")
    a.add_argument("--checkout", required=True, type=Path)
    a.add_argument("--allow-clinical", action="store_true")
    a.add_argument("--push", action="store_true")
    a = sub.add_parser("benchmark")
    a.add_argument("inputs", nargs="+", type=Path)
    a.add_argument("--output", required=True, type=Path)
    a.add_argument(
        "--origin", choices=["synthetic", "authorized-record"], default="synthetic"
    )
    a.add_argument("--authorization-ref", default="")
    args = p.parse_args()
    cfg = config(args.config)
    os.umask(0o077)
    store = Store(args.workspace)
    try:
        result = dispatch(args, store, cfg)
        print(json.dumps(result, indent=2, default=str))
        # A partial run is observable to systemd/cron while successful files stay committed.
        if isinstance(result, list) and any(
            isinstance(x, dict) and x.get("status") == "failed" for x in result
        ):
            return 1
        if args.command == "nightly" and (
            any(j["stage"] != "done" for j in store.jobs())
            or result.get("backup_error")
            or any(
                x.get("status") == "failed"
                for k in ["imports", "processing", "uploads"]
                for x in result.get(k, [])
            )
        ):
            return 1
        return 0
    except Exception as e:
        # Operator messages from local validation are safe; HTTP/JSON provider exceptions are class-only.
        message = (
            str(e)
            if isinstance(e, (ValueError, FileNotFoundError))
            else type(e).__name__
        )
        print(
            json.dumps({"error": type(e).__name__, "message": message}), file=sys.stderr
        )
        return 1
    finally:
        store.close()


def dispatch(a, store, cfg):
    from . import backup, publication, automation
    from .runner import run, reset_failed

    if a.command == "ingest":
        from .ingest import ingest

        result = []
        with lock(store.root):
            for file in a.paths:
                try:
                    id, created = ingest(
                        store, file, a.shift, a.date, a.origin, a.authorization_ref
                    )
                    result.append({"id": id, "imported": created})
                except Exception as e:
                    result.append(
                        {
                            "source": file.name,
                            "status": "failed",
                            "error": type(e).__name__,
                        }
                    )
        return result
    if a.command == "run":
        return run(store, cfg, a.force_retry)
    if a.command == "status":
        return [dict(j) for j in store.jobs()]
    if a.command == "retry":
        with lock(store.root):
            reset_failed(store, a.id)
        return {"reset": a.id}
    if a.command == "review-template":
        return publication.review_template(store, a.output)
    if a.command == "approve-synthetic":
        publication.approve_synthetic(store, a.output)
        return {"review": str(a.output)}
    if a.command == "export":
        return publication.export(store, a.review, a.target, a.allow_clinical)
    if a.command == "backup-key":
        backup.create_key(a.path)
        return {
            "keyFile": str(a.path),
            "note": "Store a separate secure copy; losing the key makes backups unrecoverable.",
        }
    if a.command == "backup":
        return {"backup": str(backup.create_backup(store, a.key, a.destination))}
    if a.command == "restore":
        return {"restored": str(backup.restore(a.backup, a.key, a.target))}
    if a.command == "apply-edits":
        from .editing import apply_edits

        return apply_edits(store, a.source)
    if a.command == "recover-library":
        from .recovery import recover_library

        return recover_library(store, a.source)
    if a.command == "retry-upload":
        with lock(store.root):
            backup.retry_upload(store, a.id)
        return {"reset": a.id}
    if a.command == "upload":
        with lock(store.root):
            return backup.upload_backups(store, cfg)
    if a.command == "cleanup":
        return {"eligible": backup.cleanup(store, cfg, a.apply), "deleted": a.apply}
    if a.command in ["scan", "nightly"]:
        sources = [a.source] if getattr(a, "source", None) else automation.discover(cfg)
        imported = [
            row
            for source in sources
            for row in automation.scan(store, cfg, source, a.date)
        ]
        if a.command == "scan":
            return imported
        result = {"imports": imported, "processing": run(store, cfg)}
        if a.key and a.backup_directory:
            try:
                result["backup"] = str(
                    backup.backup_if_changed(store, a.key, a.backup_directory)
                )
            except Exception as e:
                result["backup_error"] = type(e).__name__
        if cfg["backup"]["remote"]:
            with lock(store.root):
                result["uploads"] = backup.upload_backups(store, cfg)
        apply_retention = cfg["retention"]["enabled"] and not result.get("backup_error")
        result["cleanup"] = {
            "eligible": backup.cleanup(store, cfg, apply_retention),
            "deleted": bool(apply_retention),
        }
        return result
    if a.command == "sync-master":
        from .github import sync_master

        return sync_master(store, a.checkout, cfg, a.allow_clinical, a.push)
    if a.command == "benchmark":
        from .benchmark import benchmark

        return benchmark(cfg, a.inputs, a.output, a.origin, a.authorization_ref)


if __name__ == "__main__":
    raise SystemExit(main())
