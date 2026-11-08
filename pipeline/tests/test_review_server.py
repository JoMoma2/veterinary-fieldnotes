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


def test_saved_endpoint_preserves_bookmarks_after_move(tmp_path):
    import json
    from vet_pipeline.review_server import saved_endpoint
    state = {'url': 'http://127.0.0.1:52139/' + 'a' * 43 + '/review/index.html', 'loopbackOnly': True}
    (tmp_path / 'review-server.json').write_text(json.dumps(state))
    assert saved_endpoint(tmp_path) == ('a' * 43, 52139)
    for bad in ['https://127.0.0.1:52139/', 'http://external.example:80/' + 'a' * 43 + '/review/index.html',
                state['url'] + '?other=1', state['url'].replace('127.0.0.1', 'name@127.0.0.1'),
                state['url'].replace('a' * 43, 'short')]:
        (tmp_path / 'review-server.json').write_text(json.dumps({**state, 'url': bad}))
        with pytest.raises(ValueError):
            saved_endpoint(tmp_path)


def test_old_workspace_symlink_keeps_audio_links_working(tmp_path):
    moved = tmp_path / 'organized'; moved.mkdir()
    old = tmp_path / 'old-workspace'; old.symlink_to(moved, target_is_directory=True)
    (moved / 'inputs').mkdir(); (moved / 'inputs/test.wav').write_bytes(b'old audio')
    with running(old) as (client, prefix):
        assert client.get(prefix + 'inputs/test.wav').content == b'old audio'


def test_experiment_landing_reuses_context_report_without_a_live_ledger(tmp_path):
    (tmp_path / 'review').mkdir()
    (tmp_path / 'review/shift-context.html').write_text('<h1>Saved experiment</h1>')
    with running(tmp_path) as (client, prefix):
        assert client.get(prefix + 'review/index.html').text == '<h1>Saved experiment</h1>'
    assert not (tmp_path / 'jobs.sqlite3').exists()
    assert not (tmp_path / 'review/index.html').exists()


def test_diagnostics_link_actual_files_without_directory_listing_or_missing_json(tmp_path):
    from vet_pipeline.morning import diagnostic_links
    folder = tmp_path / 'quality/test'; folder.mkdir(parents=True)
    (folder / 'step 1.json').write_text('{}')
    secret = tmp_path.parent / 'outside.json'; secret.write_text('private')
    (folder / 'escape.json').symlink_to(secret)
    links = diagnostic_links(tmp_path, 'test')
    assert 'quality/test/step%201.json' in links
    assert 'escape.json' not in links and 'transcription-details' not in links
    assert 'href="../../quality/test/"' not in links
    (tmp_path / 'review/recordings').mkdir(parents=True)
    (tmp_path / 'review/recordings/test.html').write_text(links)
    with running(tmp_path) as (client, prefix):
        assert client.get(prefix + 'quality/test/step%201.json').status_code == 200
        assert client.get(prefix + 'quality/test/').status_code == 404
    assert 'No saved diagnostic' in diagnostic_links(tmp_path, 'missing')
