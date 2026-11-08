"""Open the local private report without hidden-file restrictions in Snap browsers."""
import json
from vet_pipeline.locations import location
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit
import webbrowser

subprocess.run(['systemctl', '--user', 'start', 'vet-fieldnotes-review.service'], check=True)
state = location('data', 'library', 'review-server.json')
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
