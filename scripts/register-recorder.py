"""No arguments opens the owner registration dialog; --stage installs disabled units/shortcuts."""
import argparse, json, os, sys
from pathlib import Path
from vet_pipeline.recorder_setup import stage, register, gui
p = argparse.ArgumentParser()
p.add_argument('--stage', action='store_true')
p.add_argument('--mount', type=Path)
p.add_argument('--authorization-ref', default='')
p.add_argument('--activate', action='store_true')
p.add_argument('--storage-authorization-ref', default='')
a = p.parse_args()
os.umask(0o077)
try:
    result = stage() if a.stage else register(a.mount, a.authorization_ref, a.activate, a.storage_authorization_ref) if a.mount else gui()
    if result:
        print(json.dumps(result, indent=2))
except Exception as error:
    message = str(error) if isinstance(error, ValueError) else type(error).__name__
    if not a.stage and not a.mount:
        import subprocess
        subprocess.run(['zenity', '--error', '--title=Fieldnotes setup', '--text=' + message])
    else:
        print(json.dumps({'error': type(error).__name__, 'message': message}), file=sys.stderr)
    raise SystemExit(1)
