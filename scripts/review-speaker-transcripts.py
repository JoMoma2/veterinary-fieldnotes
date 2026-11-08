"""Transcript-only local owner-voice pilot; never starts knowledge extraction."""
import argparse, os, signal
from vet_pipeline.private import private_path
from vet_pipeline.util import load_json, write_json, now
from pathlib import Path
from vet_pipeline.speaker_transcripts import prepare, run, render
p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
a=sub.add_parser('prepare')
for name in ['reference','comparison','labels','manifest','directory','visible']:a.add_argument('--'+name,type=Path,required=True)
a.add_argument('--owner-label',default='Owner')
for name in ['run','report']:sub.add_parser(name).add_argument('directory',type=Path)
a=p.parse_args();os.umask(0o077)
if a.command=='prepare':prepare(a.reference,a.comparison,a.labels,a.manifest,a.directory,a.visible,a.owner_label)
elif a.command=='run':
    def interrupted(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try: run(a.directory)
    except BaseException as error:
        root = private_path(a.directory)
        state = load_json(root / 'progress.json')
        state.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                     errorClass=type(error).__name__, updatedAt=now())
        write_json(root / 'progress.json', state); render(root)
        raise
else:render(a.directory)
