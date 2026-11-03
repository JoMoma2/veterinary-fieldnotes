"""Shared private-workspace boundary for owner-only evaluation and recovery tools."""

from __future__ import annotations
import os
from pathlib import Path
from .util import atomic_write


def private_path(path):
    path = Path(path).expanduser().resolve()
    # Some managed environments have empty .git placeholder directories in /tmp;
    # only actual worktree markers/metadata establish a checkout boundary.
    if any(
        (parent / ".git").is_file() or (parent / ".git/HEAD").is_file()
        for parent in [path, *path.parents]
    ):
        raise ValueError(
            "Private evaluation/backup material must be outside every Git checkout, including the master repository"
        )
    return path


def initialize_private(path):
    path = private_path(path)
    if path.exists() and any(p.name != ".gitignore" for p in path.iterdir()):
        raise ValueError("Choose a new empty private evaluation directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    atomic_write(path / ".gitignore", "*\n")
    return path
