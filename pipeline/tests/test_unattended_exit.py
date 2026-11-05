import pytest


@pytest.mark.parametrize('failed,result,expected', [
    (False, {'incomplete': 1, 'processing': [{'status': 'deferred'}]}, 0),
    (True, {'incomplete': 1, 'processing': [{'status': 'deferred'}]}, 1),
    (False, {'incomplete': 1, 'discoveryError': 'OSError'}, 1),
    (False, {'incomplete': 1, 'imports': [{'status': 'failed'}]}, 1),
    (False, {'incomplete': 1, 'processing': [{'status': 'failed'}]}, 1),
    (False, {'incomplete': 1, 'master_sync': {'pending': True, 'status': 'awaiting-authorization'}}, 0),
    (False, {'incomplete': 1, 'master_sync': {'pending': True, 'status': 'failed'}}, 1),
])
def test_timer_exit_distinguishes_waiting_from_failure(store, first, monkeypatch, failed, result, expected):
    from vet_pipeline import cli
    if failed:
        store.update(first, error='ValueError', attempts=1)
    monkeypatch.setattr(cli, 'dispatch', lambda *a: result)
    monkeypatch.setattr('sys.argv', ['vet-pipeline', '--workspace', str(store.root), 'unattended'])
    assert cli.main() == expected
