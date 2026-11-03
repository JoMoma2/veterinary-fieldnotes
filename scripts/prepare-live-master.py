"""Preserve an exclusively synthetic master archive before first real deployment.

Explicit, one-time operation. Moves synthetic records intact, never removes their
history, never handles a clinical archive and never uses a force push.
"""
import argparse, json
from pathlib import Path
from vet_pipeline.github import _git, _verify_private
from vet_pipeline.library import read_library
from vet_pipeline.recovery import verify_snapshot
from vet_pipeline.util import write_json, now
p = argparse.ArgumentParser()
p.add_argument('--checkout', type=Path, required=True)
p.add_argument('--apply', action='store_true')
p.add_argument('--push', action='store_true')
a = p.parse_args()
c = a.checkout.resolve()
_verify_private(c)
if _git(c, 'status', '--porcelain').stdout.strip():
    raise SystemExit('Private checkout must be clean; owner changes are never overwritten')
if _git(c, 'branch', '--show-current').stdout.strip() != 'main':
    raise SystemExit('Use the dedicated private main checkout')
marker = c / 'production-storage.json'
if marker.exists():
    print(json.dumps({'status': 'already-reserved', 'marker': str(marker)}))
    raise SystemExit(0)
_git(c, 'fetch', 'origin', 'main')
_git(c, 'merge', '--ff-only', 'origin/main')
archive = c / 'archive'
lib, _ = verify_snapshot(archive)
if any(e['origin'] != 'synthetic' for k, records in lib.items() if k != 'topics' for e in records):
    raise SystemExit('Refusing to move a clinical/mixed archive')
label = 'pre-live-' + now().replace(':', '').replace('.', '-').replace('T', '-')
dest = c / 'synthetic-validation' / label
result = {'status': 'planned', 'syntheticArchive': str(dest.relative_to(c) / 'archive'),
          'productionArchive': 'archive', 'clinicalRecordsUploaded': False}
if a.apply:
    dest.mkdir(parents=True)
    _git(c, 'mv', 'archive', str(dest.relative_to(c) / 'archive'))
    if (c / 'processing-status.json').exists():
        _git(c, 'mv', 'processing-status.json', str(dest.relative_to(c) / 'processing-status.json'))
    if verify_snapshot(dest / 'archive')[0] != lib:
        raise RuntimeError('Moved synthetic archive differs; all files/history retained for recovery')
    write_json(marker, {'schemaVersion': 1, 'reservedOrigin': 'authorized-record',
                        'archivePath': 'archive', 'syntheticArchive': result['syntheticArchive'],
                        'preparedAt': now(), 'note': 'Production archive absent until first authorized real knowledge sync. Synthetic snapshots/history retained separately.'})
    _git(c, 'add', '--', 'synthetic-validation', 'production-storage.json')
    _git(c, 'commit', '-m', 'Preserve synthetic validation separately and reserve live knowledge archive')
    result.update(status='committed', commit=_git(c, 'rev-parse', 'HEAD').stdout.strip())
    if a.push:
        _git(c, 'push', 'origin', 'main')
        remote = _git(c, 'ls-remote', 'origin', 'refs/heads/main').stdout.split()
        if not remote or remote[0] != result['commit']:
            raise RuntimeError('Prepared commit retained locally; remote confirmation failed')
        result['remoteVerified'] = True
print(json.dumps(result, indent=2))
