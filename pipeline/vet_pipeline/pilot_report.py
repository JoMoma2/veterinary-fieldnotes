"""Single-file private pilot viewer, including audio for sandboxed file browsers."""
import base64
import hashlib
import html
import json
import re
from pathlib import Path

from .evaluation import session
from .ingest import transcript_valid
from .private import private_path
from .util import atomic_write, load_json


SCRIPT = """document.addEventListener('click',event=>{
const button=event.target.closest('button[data-player]');if(!button)return;
const audio=document.getElementById(button.dataset.player),start=Number(button.dataset.start);
if(!audio||!Number.isFinite(start)||start<0)return;
const seek=()=>{audio.currentTime=start;};
if(audio.readyState)seek();else audio.addEventListener('loadedmetadata',seek,{once:true});
audio.play().catch(()=>{document.getElementById('playback-status').textContent='Playback was blocked by the browser. Try the audio player’s Play button.';});
});"""


def render_pilot(root, output=None):
    root = private_path(root)
    pilot = load_json(root / 'pilot.json')
    prepared = []
    total = 0
    for item in pilot['samples']:
        label = item['label']
        if not re.fullmatch('[a-z][a-z0-9_-]{0,59}', label):
            raise ValueError('Invalid pilot label')
        folder = root / label
        if root not in folder.resolve().parents:
            raise ValueError('Pilot source escapes the private workspace')
        folder, _ = session(folder)  # Verify the original and working-copy hashes.
        audio = folder / 'audio/normalized.wav'
        if root not in audio.resolve().parents:
            raise ValueError('Pilot audio escapes the private workspace')
        total += audio.stat().st_size
        if total > 32 * 1024**2:
            raise ValueError('Single-file pilot audio limit is 32 MiB; keep full recordings separate')
        text = transcript_valid(load_json(folder / 'transcript.json'))
        prepared.append((item, text, audio))
    e = lambda value: html.escape(str(value), quote=True)
    title = pilot.get('title', 'Fieldnotes — small recorder-settings test')
    body = '<h1 id="top">' + e(title) + '</h1><p>Private evaluation. Audio excerpts and their transcripts are embedded in this file. No server or additional file access is needed. Text is unreviewed; passing a repetition screen does not establish accuracy.</p><nav>'
    body += ' · '.join('<a href="#' + e(item['label']) + '">' + e(item['label'].title()) + ' excerpt</a>' for item, _, _ in prepared) + '</nav><p id="playback-status" role="status"></p>'
    body += '<p>' + e(pilot.get('description', 'Both samples use the same candidate settings. Earlier/later setting-change labels are provisional; exact gain-change timing and recorder clock times are unverified.')) + '</p>'
    for item, transcript, audio in prepared:
        label = item['label']
        encoded = base64.b64encode(audio.read_bytes()).decode('ascii')
        body += '<section id="' + e(label) + '"><h2>' + e(label.title()) + ' excerpt</h2><p>Source: ' + e(item['sourceName']) + '; recording-relative excerpt starts at ' + e(item['sourceStartSeconds']) + ' seconds.</p>'
        if item.get('description'):
            body += '<p>' + e(item['description']) + '</p>'
        if item.get('quality', {}).get('reviewRequired'):
            body += '<p role="note"><strong>Review required:</strong> ' + e('; '.join(item['quality'].get('reasons', []))) + '</p>'
        body += '<audio id="audio-' + e(label) + '" controls preload="metadata" src="data:audio/wav;base64,' + encoded + '"></audio><p>Click a timestamp to play from that point in the excerpt.</p>'
        body += '<details><summary>Transcription quality screening</summary><pre>' + e(json.dumps(item.get('quality', {}), indent=2)) + '</pre></details><h3>Unreviewed transcript</h3>'
        for segment in transcript['segments']:
            body += '<p><button type="button" data-player="audio-' + e(label) + '" data-start="' + str(segment['start']) + '">' + e(f"{segment['start']:.2f}–{segment['end']:.2f}s") + '</button> ' + e(segment['text']) + '</p>'
        body += '<p><a href="#top">Back to top</a></p></section>'
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = "default-src 'none'; style-src 'unsafe-inline'; media-src data:; script-src 'sha256-" + script_hash + "'; base-uri 'none'; form-action 'none'"
    document = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="' + e(csp) + '"><title>' + e(title) + '</title><style>body{max-width:1100px;margin:auto;padding:24px;font:17px/1.6 system-ui;background:#faf8f2;color:#18332f;overflow-wrap:anywhere}section{background:white;padding:18px;margin:20px 0;border:1px solid #b8c9bf;border-radius:10px}audio{width:100%}pre{white-space:pre-wrap}button{font:inherit;padding:4px 8px;cursor:pointer}a{color:#12645c}nav a{display:inline-block;padding:8px}</style></head><body>' + body + '<script>' + SCRIPT + '</script></body></html>'
    output = private_path(output) if output is not None else root / 'index.html'
    if output.suffix.lower() != '.html':
        raise ValueError('Pilot export must be an HTML report')
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(output, document)
    output.chmod(0o600)
    return output
