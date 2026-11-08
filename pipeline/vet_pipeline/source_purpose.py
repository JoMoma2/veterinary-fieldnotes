"""Private content-hash exclusions for nonclinical recorder material.

Stored outside configuration/Git so already-running evaluation workers can keep
their immutable profiles. An excluded source is retained, never deleted.
"""
import re
import sqlite3

from .private import private_path
from .util import load_json, write_json, lock, now


class ReferenceOnlySource(ValueError):
    """This exact recording is designated for voice enrollment, not knowledge."""


def exclusions(workspace):
    path = workspace / 'source-exclusions.json'
    if not path.exists():
        return {}
    value = load_json(path)
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('entries'), dict):
        raise ValueError('Invalid source-purpose registry; import stopped safely')
    for sha, record in value['entries'].items():
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha) or not isinstance(record, dict) or record.get('purpose') != 'owner-voice-reference':
            raise ValueError('Invalid source-purpose entry; import stopped safely')
    return value['entries']


def register_reference(workspace, reference, sha256):
    workspace = private_path(workspace); reference = private_path(reference)
    if not re.fullmatch('[a-f0-9]{64}', sha256):
        raise ValueError('Expected a complete content hash')
    with lock(workspace):
        entries = exclusions(workspace)
        db_path = workspace / 'jobs.sqlite3'
        if db_path.exists():
            db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
            try:
                if db.execute('SELECT 1 FROM jobs WHERE sha256=?', (sha256,)).fetchone():
                    raise ValueError('Reference already has a knowledge job; preserve it and resolve its purpose explicitly')
            finally:
                db.close()
        entries.setdefault(sha256, {'purpose': 'owner-voice-reference', 'workspace': str(reference), 'registeredAt': now()})
        write_json(workspace / 'source-exclusions.json', {'version': 1, 'entries': entries})
