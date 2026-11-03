"""Exercise the reviewed publisher without changing GitHub or public content."""
import json
import runpy
import subprocess
from pathlib import Path

import pytest

from vet_pipeline.util import REPO


@pytest.mark.parametrize("visibility", ["PUBLIC", "PRIVATE"])
def test_publisher_uses_production_toolchain_only_for_public_checkout(tmp_path, monkeypatch, visibility):
    checkout = tmp_path / "public-checkout"
    checkout.mkdir()
    monkeypatch.chdir(tmp_path)
    calls = []
    exports = []

    def command(args, **kwargs):
        # Retain only the nonsecret dataset flag, never the inherited environment.
        calls.append((args, kwargs.get("env", {}).get("LIBRARY_DATASET")))
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 0, json.dumps({"visibility": visibility}))
        return subprocess.CompletedProcess(args, 1 if args[:3] == ["git", "diff", "--cached"] else 0)

    def export(*args):
        exports.append(args[2])
        return {"articles": 0}

    monkeypatch.setattr(subprocess, "run", command)
    monkeypatch.setattr("vet_pipeline.publication.export", export)
    monkeypatch.setenv("LIBRARY_DATASET", "demo")
    monkeypatch.setattr("sys.argv", ["publish-approved.py", "--workspace", str(tmp_path / "private-workspace"),
                                   "--review", str(tmp_path / "approval.json"), "--checkout", "public-checkout", "--push"])
    if visibility == "PRIVATE":
        with pytest.raises(SystemExit, match="separate public"):
            runpy.run_path(str(REPO / "scripts/publish-approved.py"), run_name="__main__")
        assert not exports and len(calls) == 1
    else:
        runpy.run_path(str(REPO / "scripts/publish-approved.py"), run_name="__main__")
        assert exports == [checkout / "content/public"]
        builds = [(args, mode) for args, mode in calls if len(args) > 1 and args[1] == "run"]
        assert builds == [([str(checkout / "scripts/local-node.sh"), "run", "check"], "production"),
                          ([str(checkout / "scripts/local-node.sh"), "run", "build"], "production")]
        assert (["git", "push", "origin", "main"], None) in calls
