"""Open the local private report without hidden-file restrictions in Snap browsers."""
import json
import re
from vet_pipeline.private import private_path
from vet_pipeline.locations import location
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit
import webbrowser

workspace=location('data','library');unit='vet-fieldnotes-review.service'
selection=location('config','active-review.json')
if selection.exists():
    selected=json.loads(selection.read_text())
    workspace=private_path(selected['workspace']);unit=selected['unit']
    if not re.fullmatch(r'vet-fieldnotes-[a-z0-9-]*review[a-z0-9-]*[.]service',unit):raise ValueError('Expected a FieldNotes read-only review unit')
subprocess.run(['systemctl', '--user', 'start', unit], check=True)
state = workspace / 'review-server.json'
for _ in range(30):
    if state.is_file():
        url = json.loads(state.read_text())['url']
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
            raise ValueError('Expected a private loopback review URL')
        webbrowser.open(url)
        break
    time.sleep(.1)
else:
    raise RuntimeError('Private review server did not initialize')
