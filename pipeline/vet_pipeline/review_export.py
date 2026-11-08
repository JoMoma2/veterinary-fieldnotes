"""Owner-visible, standalone review copies; never part of a website build."""
import html

from .private import private_path
from .util import atomic_write, load_json


def export(root):
    experiment = load_json(root / 'experiment.json')
    if not experiment.get('ownerResultsDirectory'):
        return
    target = private_path(experiment['ownerResultsDirectory'])
    target.mkdir(parents=True, exist_ok=True, mode=0o700); target.chmod(0o700)
    body = '<h1>Last shift — speakers and medical study questions</h1><p>PRIVATE, unreviewed AI output. Anonymous voice matches and role/confidence annotations are hypotheses, not confirmed identities. No publication.</p>'
    for source, filename, title in [
        ('readable-notes.md', 'Medical-notes.md', 'Medical notes and questions'),
        ('speaker-transcript.md', 'Speaker-labelled-transcript.md', 'Speaker-labelled transcript'),
    ]:
        path = root / source
        if not path.exists():
            continue
        text = path.read_text()
        atomic_write(target / filename, text)
        body += '<h2>' + html.escape(title) + '</h2>'
        for line in text.splitlines():
            if line.startswith('#'):
                body += '<h3>' + html.escape(line.lstrip('# ')) + '</h3>'
            elif line:
                body += '<p>' + html.escape(line) + '</p>'
    body += '<p>This standalone copy needs no report links, server or internet. Audio-enabled review remains in the private workspace.</p>'
    document = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'"><title>Private Fieldnotes results</title><style>body{max-width:1000px;margin:auto;padding:24px;background:#faf8f2;color:#18332f;font:17px/1.65 system-ui;overflow-wrap:anywhere}h2{border-top:2px solid #9fb8ad;padding-top:20px}p{white-space:pre-wrap}</style></head><body>' + body + '</body></html>'
    atomic_write(target / 'Results.html', document)
