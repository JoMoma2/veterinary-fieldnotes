"""Canonical owner-local locations; private data is a sibling of the source repo."""
import os
from pathlib import Path


def fieldnotes_home():
    return Path(os.environ.get("FIELDNOTES_HOME", Path.home() / "FieldNotes")).expanduser().resolve()


def location(*parts):
    return fieldnotes_home().joinpath(*parts)
