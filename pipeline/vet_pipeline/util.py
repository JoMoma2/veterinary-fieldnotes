from __future__ import annotations
import contextlib, fcntl, hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from .locations import local_path

REPO = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest_file(path: Path):
    path = local_path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path: Path, data: str | bytes):
    path = local_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data.encode() if isinstance(data, str) else data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        d = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def load_json(path: Path):
    path = local_path(path)
    return json.loads(path.read_text())


@contextlib.contextmanager
def lock(workspace: Path):
    workspace = local_path(workspace)
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (workspace / "pipeline.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another pipeline process owns this workspace") from None
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
