"""Canonical owner-local locations; private data is a sibling of the source repo."""
import os
from pathlib import Path


def fieldnotes_home():
    return Path(os.environ.get("FIELDNOTES_HOME", Path.home() / "FieldNotes")).expanduser().resolve()


def location(*parts):
    return fieldnotes_home().joinpath(*parts)


# Read old immutable profiles/checkpoints without keeping home-folder aliases.
# Only owner-local FieldNotes prefixes match; arbitrary text/JSON is never rewritten.
LEGACY_LOCATIONS = {
    'vet-knowledge-library': 'app',
    'vet-knowledge-master': 'repositories/master',
    'Fieldnotes-private-review': 'reports',
    '.config/vet-fieldnotes': 'config',
    '.local/share/vet-fieldnotes': 'data/workspace',
    '.local/share/vet-fieldnotes-live': 'data/library',
    '.local/share/vet-fieldnotes-archives': 'data/archives',
    '.local/share/vet-fieldnotes-evaluations': 'data/evaluations',
    '.local/share/vet-fieldnotes-device-settings': 'data/device-settings',
    '.local/share/vet-fieldnotes-repairs': 'data/repairs',
    '.local/share/vet-fieldnotes-validation': 'data/validation',
    '.local/share/vet-fieldnotes-ai': 'ai',
    '.local/share/vet-fieldnotes-tools': 'tools/maintenance',
    '.local/share/vet-fieldnotes-toolchain': 'tools/runtime',
    '.local/share/vet-fieldnotes-setup': 'tools/setup',
    'Downloads/voice-calibration-labels.json': 'inbox/voice-calibration-labels.json',
}


def local_path(value):
    """Translate a known former filesystem prefix at the point of file access.

    Does not resolve symlinks, follow outside paths, or change serialized evidence,
    model bindings or request fingerprints. Relative paths keep normal semantics.
    """
    path = Path(value).expanduser()
    if path.is_absolute():
        home = Path.home()
        for old, new in LEGACY_LOCATIONS.items():
            try:
                suffix = path.relative_to(home / old)
            except ValueError:
                continue
            return fieldnotes_home() / new / suffix
    return path
