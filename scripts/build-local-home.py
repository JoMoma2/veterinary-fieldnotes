"""Render the private owner-local starting page; never writes inside the website."""
from __future__ import annotations
import html
from pathlib import Path
from vet_pipeline.locations import fieldnotes_home
from vet_pipeline.private import private_path
from vet_pipeline.util import atomic_write, load_json


def build(root=None):
    root = private_path(root or fieldnotes_home())
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    e = lambda value: html.escape(str(value), quote=True)
    reports = root / 'reports'
    items = []
    for p in sorted(reports.rglob('*.html')) if reports.exists() else []:
        if p.name not in {'index.html', 'Results.html', 'Calibration.html'} and p.parent != reports:
            continue
        label = str(p.relative_to(reports)).replace('/Results.html', '').removesuffix('.html')
        items.append(f'<li><a href="{e(p.as_uri())}">{e(label.replace("-", " "))}</a></li>')
    folders = {
        'reports': 'Readable reports and listening reviews',
        'data/library/inputs': 'Retained original WAV recordings',
        'data/library/transcripts': 'Complete saved transcripts',
        'data/library/transcription-details': 'Raw transcription output',
        'data/evaluations': 'Private experiments and voice-reference continuation notes',
        'data/archives': 'Preserved earlier runs',
        'config': 'Private configuration and service definitions',
        'ai': 'Models and local AI environment',
        'app': 'Application source and documentation',
        'maintenance': 'Private organization and integrity records',
    }
    links = ''.join(f'<li><a href="{e((root / p).as_uri())}/">{e(label)}</a></li>'
                    for p, label in folders.items() if (root / p).is_dir())
    guide = (root / 'README.md').as_uri()
    publication = root / 'config/automatic-publication.json'
    publication_note = ('Automatic publication is enabled for future runs after privacy checks. '
                        '<a href="https://veterinary-fieldnotes.pages.dev">Open the website</a>.'
                        if publication.exists() and load_json(publication).get('enabled')
                        else 'Publication requires the owner’s applicable approval.')
    text = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FieldNotes — Start Here</title><style>
body{{font:17px/1.6 system-ui,sans-serif;max-width:920px;margin:auto;padding:30px;background:#f3f6f5;color:#16352e}}
h1{{margin-bottom:0}}section{{background:white;padding:20px 28px;border-radius:14px;margin:22px 0;border:1px solid #dce6df}}
a{{color:#15654e;text-underline-offset:3px}}li{{margin:10px 0}}.note{{color:#485d55}}code{{overflow-wrap:anywhere}}
</style><h1>FieldNotes</h1><p class="note">Your private local workspace. Opening this page does not start processing, upload or publish anything.</p>
<section><h2>Review results</h2><p>Use <strong>Fieldnotes — Morning Review</strong> in the Ubuntu applications menu for the running local report. Saved reports and past experiments are below; their dates identify the run, not a newly generated result.</p><ul>{''.join(items) or '<li>No saved reports yet.</li>'}</ul></section>
<section><h2>Find your files</h2><ul>{links}</ul><p><a href="{e(guide)}">Folder guide and operating notes</a></p></section>
<p class="note">Keep this folder private. Source recordings and transcripts remain retained. Historical saved paths are handled internally; use this folder for new work. {publication_note}</p></html>'''
    atomic_write(root / 'Start.html', text)
    return root / 'Start.html'


if __name__ == '__main__':
    build()
    print('Private FieldNotes start page refreshed.')
