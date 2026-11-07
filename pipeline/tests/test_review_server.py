import threading
from contextlib import contextmanager

import httpx
import pytest

from vet_pipeline.review_server import server


@contextmanager
def running(root):
    http = server(root, 't' * 43)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{http.server_port}', trust_env=False) as client:
            yield client, '/' + 't' * 43 + '/'
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=2)


def test_private_viewer_ranges_and_no_directory_or_ledger_access(tmp_path):
    (tmp_path / 'review').mkdir(); (tmp_path / 'review/index.html').write_text('<h1>Private review</h1>')
    (tmp_path / 'inputs').mkdir(); (tmp_path / 'inputs/test.wav').write_bytes(b'0123456789')
    (tmp_path / 'jobs.sqlite3').write_bytes(b'secret database')
    outside = tmp_path.parent / 'outside-secret.wav'; outside.write_bytes(b'not allowed')
    (tmp_path / 'inputs/escape.wav').symlink_to(outside)
    with running(tmp_path) as (client, prefix):
        assert client.get('/review/index.html').status_code == 404
        assert client.get(prefix + 'inputs/').status_code == 404
        assert client.get(prefix + 'jobs.sqlite3').status_code == 404
        assert client.get(prefix + 'inputs/escape.wav').status_code == 404
        assert client.get(prefix + 'inputs/%2e%2e/jobs.sqlite3').status_code == 404
        report = client.get(prefix + 'review/index.html')
        assert report.status_code == 200 and 'publication-preview.html' in report.text
        assert report.headers['Cache-Control'] == 'no-store'
        result = client.get(prefix + 'inputs/test.wav', headers={'Range':'bytes=3-5'})
        assert result.status_code == 206 and result.content == b'345'
        assert result.headers['Content-Range'] == 'bytes 3-5/10'
        assert client.get(prefix + 'inputs/test.wav', headers={'Range':'bytes=-2'}).content == b'89'
        assert client.get(prefix + 'inputs/test.wav', headers={'Range':'bytes=10-'}).status_code == 416
        assert client.head(prefix + 'inputs/test.wav').headers['Content-Length'] == '10'
        assert client.post(prefix + 'review/index.html').status_code == 501
        assert client.get(prefix + 'review/index.html', headers={'Host':'external.example'}).status_code == 403
        assert client.get(prefix + 'review/index.html', headers={'Origin':'https://external.example'}).status_code == 403


def test_candidate_preview_is_private_snapshot_without_publishing(store):
    with running(store.root) as (client, prefix):
        result = client.get(prefix + 'review/publication-preview.html')
        assert result.status_code == 200
        assert 'No candidates yet' in result.text and 'nothing here is approved' in result.text


def test_saved_candidates_are_escaped_and_hash_bound_without_any_approval(store, cfg, first):
    from vet_pipeline.runner import run
    from vet_pipeline.library import current
    from vet_pipeline.publication import record_hash
    assert run(store, cfg)[0]['status'] == 'done'
    article = current(store)['articles'][0]
    with running(store.root) as (client, prefix):
        result = client.get(prefix + 'review/publication-preview.html')
        assert result.status_code == 200
        assert record_hash(article) in result.text and article['id'] in result.text
        assert 'Owner review' in result.text
        assert all(a['publication']['status'] == 'draft' for a in current(store)['articles'])


def test_rejects_git_root_and_nonrandom_capability(tmp_path):
    with pytest.raises(ValueError, match='capability'):
        server(tmp_path, 'short')
    (tmp_path / '.git').mkdir(); (tmp_path / '.git/HEAD').write_text('ref: refs/heads/main')
    with pytest.raises(ValueError, match='outside every Git'):
        server(tmp_path, 't' * 43)
