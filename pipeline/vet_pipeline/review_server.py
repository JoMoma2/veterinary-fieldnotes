"""Read-only loopback viewer for private reports and seekable retained audio.

No inference, editing, upload or publication endpoints. A private capability URL
avoids granting arbitrary web pages access to the loopback archive.
"""
import html
import io
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import sqlite3
from urllib.parse import unquote, urlsplit

from .private import private_path
from .util import write_json


def live_status(root):
    db = sqlite3.connect(f'file:{root}/jobs.sqlite3?mode=ro', uri=True, timeout=5)
    try:
        counts = dict(db.execute('SELECT stage,COUNT(*) FROM jobs GROUP BY stage'))
    finally:
        db.close()
    e = lambda v: html.escape(str(v), quote=True)
    extra = ''
    from .util import load_json
    for path in sorted((root / 'shift-extraction').glob('*/experiment.json')):
        try:
            experiment = load_json(path)
            completed = list((path.parent / 'calls').glob('episode-[0-9][0-9][0-9].json'))
            extra += '<p>Whole-shift AI: <strong>' + e(experiment['status']) + '</strong>; saved detailed episodes: ' + str(len(completed)) + '; context: ' + e(experiment['provider']['context_window']) + ' tokens. The first episode map may take time; unchanged recording counts do not mean inference has stopped.</p>'
        except (OSError, ValueError, KeyError):
            extra += '<p>Whole-shift progress is being updated; refresh shortly.</p>'
    return '<section><h2>Live saved progress</h2><p>' + e(sum(counts.values())) + ' recordings imported so far. Stage counts: ' + e(counts) + '.</p>' + extra + '<p>The detailed summary below is the last generated report. Refresh this page to update saved counts.</p></section>'


def candidate_preview(root):
    """Read a transactionally committed snapshot without opening a writable Store."""
    import json
    from .publication import record_hash
    from .morning import page
    e = lambda v: html.escape(str(v), quote=True)
    db = sqlite3.connect(f'file:{root}/jobs.sqlite3?mode=ro', uri=True, timeout=5)
    try:
        records = [(kind, json.loads(data)) for kind, data in db.execute('SELECT kind,data FROM library_records ORDER BY kind,id')]
        pending = db.execute("SELECT COUNT(*) FROM jobs WHERE stage != 'done'").fetchone()[0]
    finally:
        db.close()
    body = '<p><a href="index.html">Morning processing report</a></p><p><strong>Private publication candidates — nothing here is approved or published.</strong> Owner review and applicable privacy/publication authorization are still required. This view has no publish button or upload endpoint.</p>'
    body += '<p>' + str(len(records)) + ' saved records; ' + str(pending) + ' imported recordings still incomplete or awaiting review. Other files may still be importing. Refresh for a new snapshot.</p>'
    if not records:
        body += '<p>No candidates yet. Imports, transcription and extraction can continue independently.</p>'
    group = None
    for kind, record in records:
        if kind != group:
            body += '<h2>' + e(kind.title()) + '</h2>'; group = kind
        title = record.get('title') or record.get('prompt') or record.get('name') or record['id']
        body += '<details><summary>' + e(title) + '</summary><p>Permanent ID: ' + e(record['id']) + '</p>'
        body += '<p>Exact candidate SHA256: <code>' + record_hash(record) + '</code></p>'
        if kind == 'questions':
            from .question_verification import status
            # This read-only adapter needs only the existing workspace root.
            from types import SimpleNamespace
            body += '<p>Independent medical verification: ' + e(status(SimpleNamespace(root=root),record)['status']) + '</p>'
        if kind == 'articles':
            body += '<pre>' + e(record['body']) + '</pre>'
        else:
            body += '<pre>' + e(json.dumps(record, indent=2, ensure_ascii=False)) + '</pre>'
        body += '</details>'
    return page('Fieldnotes — private publication preview', body).encode()


class ReviewHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log capability URLs, patient text, or recording identifiers.

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()

    def send_head(self):
        port = self.server.server_port
        if self.headers.get('Host') not in [f'127.0.0.1:{port}', f'localhost:{port}']:
            self.send_error(403); return None
        origin = self.headers.get('Origin')
        if origin and origin not in [f'http://127.0.0.1:{port}', f'http://localhost:{port}']:
            self.send_error(403); return None
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send_error(403); return None
        path = unquote(urlsplit(self.path).path)
        prefix = '/' + self.server.capability + '/'
        if not path.startswith(prefix):
            self.send_error(404); return None
        relative = path[len(prefix):] or 'review/index.html'
        parts = Path(relative).parts
        allowed = {'review': {'.html', '.json'}, 'inputs': {'.wav'}, 'normalized': {'.wav'},
                   'filtered': {'.wav'}, 'transcripts': {'.json'}, 'transcription-details': {'.json'},
                   'transcription-quality': {'.json'}, 'quality': {'.json'}, 'extractions': {'.json'}}
        root = self.server.private_root
        try:
            candidate = (root / relative).resolve()
        except (OSError, ValueError):
            self.send_error(404); return None
        # Experiments have a shift-context report rather than a live-job index.
        # Keep the saved landing URL useful without rewriting frozen reports.
        if relative == 'review/index.html' and not candidate.exists():
            relative = 'review/shift-context.html'
            candidate = (root / relative).resolve()
        preview = relative == 'review/publication-preview.html'
        if not parts or parts[0] not in allowed or '..' in parts or root not in candidate.parents or candidate.suffix.lower() not in allowed[parts[0]] or (not preview and not candidate.is_file()):
            self.send_error(404); return None
        if preview:
            try:
                source = io.BytesIO(candidate_preview(root))
            except (OSError, ValueError, sqlite3.Error):
                self.send_error(503); return None
        elif relative == 'review/question-verification.html':
            from types import SimpleNamespace
            from .question_verification import document
            connection = sqlite3.connect(f'file:{root}/jobs.sqlite3?mode=ro', uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            try:
                source = io.BytesIO(document(SimpleNamespace(root=root, db=connection)).encode())
            except (OSError, ValueError, KeyError, sqlite3.Error):
                self.send_error(503); return None
            finally:
                connection.close()
        elif relative == 'review/index.html':
            content = candidate.read_bytes()
            try:
                status = live_status(root).encode()
            except sqlite3.Error:
                status = b'<p>Live ledger temporarily unavailable; retained reports remain below.</p>'
            source = io.BytesIO(content.replace(b'</h1>', b'</h1><p><a href="publication-preview.html">Review proposed website material (private; publication on hold)</a></p>' + status, 1))
        else:
            source = candidate.open('rb')
        source.seek(0, 2); size = source.tell(); source.seek(0)
        start, end = 0, size - 1
        header = self.headers.get('Range')
        if header:
            match = re.fullmatch(r'bytes=(\d{0,20})-(\d{0,20})', header)
            if not match or not any(match.groups()) or size == 0:
                source.close(); self.send_error(416); return None
            a, b = match.groups()
            if a:
                start = int(a); end = min(int(b), size - 1) if b else size - 1
            else:
                start = max(0, size - int(b))
            if start > end or start >= size or (not a and int(b) == 0):
                source.close()
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.end_headers()
                return None
        self.send_response(206 if header else 200)
        self.send_header('Content-Type', self.guess_type(str(candidate)))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        if header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        source.seek(start)
        self.remaining = max(0, end - start + 1)
        return source

    def copyfile(self, source, output):
        try:
            while self.remaining:
                data = source.read(min(65536, self.remaining))
                if not data:
                    break
                output.write(data)
                self.remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browsers cancel range downloads when seeking.


def server(workspace, capability, port=0):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,100}', capability):
        raise ValueError('A private random review capability is required')
    root = private_path(workspace)
    http = ThreadingHTTPServer(('127.0.0.1', port), ReviewHandler)
    http.private_root = root
    http.capability = capability
    http.daemon_threads = True
    return http



def saved_endpoint(workspace):
    """Reuse a private endpoint after relocation without breaking existing bookmarks.

    Never follow a configured host or expose a capability in logs. Bind only
    loopback; an occupied saved port fails safely rather than changing the URL.
    """
    import json
    state = Path(workspace) / 'review-server.json'
    data = json.loads(state.read_text())
    u = urlsplit(data['url'])
    match = re.fullmatch(r'/([A-Za-z0-9_-]{32,100})/review/index[.]html', u.path)
    if (u.scheme != 'http' or u.hostname != '127.0.0.1' or u.username or u.password
            or u.query or u.fragment or not u.port or not match
            or data.get('loopbackOnly') is not True):
        raise ValueError('Invalid saved private loopback endpoint')
    return match.group(1), u.port


def main():
    import argparse
    import os
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--reuse-state', action='store_true', help='Keep an existing private review URL after moving its workspace')
    args = p.parse_args()
    os.umask(0o077)
    root = private_path(args.workspace)
    token, port = saved_endpoint(root) if args.reuse_state and (root / 'review-server.json').exists() else (secrets.token_urlsafe(32), 0)
    http = server(root, token, port)
    url = f'http://127.0.0.1:{http.server_port}/{token}/review/index.html'
    write_json(root / 'review-server.json', {'url': url, 'pid': os.getpid(), 'loopbackOnly': True})
    print('Private read-only review server ready on loopback.', flush=True)
    try:
        http.serve_forever()
    finally:
        http.server_close()


if __name__ == '__main__':
    main()
