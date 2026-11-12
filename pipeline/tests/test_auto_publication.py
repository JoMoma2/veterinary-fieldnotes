"""Publication boundaries: private evidence, literal edits, medical holds and retries."""
import copy
import json
import subprocess

import pytest

from vet_pipeline import auto_publication as ap
from vet_pipeline.library import current, validate_library
from vet_pipeline.runner import run
from vet_pipeline.util import load_json


def safe(batch, cfg, path):
    return {x['key']: {'key': x['key'], 'safe': True, 'reason': 'Non-identifying fixture',
                       'redactions': []} for x in batch}


def clinical_fixture(store, cfg, first, monkeypatch):
    # Synthetic test data simulates the clinical-origin branch; never deployed.
    run(store, cfg)
    with store.db:
        for row in list(store.db.execute('SELECT kind,id,data FROM library_records')):
            record = json.loads(row['data'])
            if row['kind'] != 'topics':
                record['origin'] = 'authorized-record'
            store.db.execute('UPDATE library_records SET data=? WHERE kind=? AND id=?',
                             (json.dumps(record), row['kind'], row['id']))
    monkeypatch.setattr('vet_pipeline.evaluation.verified_local_model', lambda c: 'fixture-model')
    monkeypatch.setattr('vet_pipeline.patient_privacy.ensure_registry', lambda *a: {'entities':[], 'caseNames':{}})
    monkeypatch.setattr(ap.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 3, 'inactive\n'))
    return {'enabled': True, 'patientNamePolicy':'owner-species-sex-v1', 'authorizationRef': 'fixture-only', 'workspace': str(store.root),
            'project': 'veterinary-fieldnotes', 'checkout': str(ap.REPO), 'notBefore': ''}


def test_literal_redaction_never_rewrites_private_source_or_medical_question():
    record = {'title': 'Call Alice about the ECG', 'summary': 'Electrical activity is not blood flow.', 'body': 'Alice spoke.'}
    original = copy.deepcopy(record)
    decision = {'safe': True, 'redactions': [{'field': 'title', 'text': 'Alice'}, {'field': 'body', 'text': 'Alice'}]}
    redacted = ap.apply_decision(record, 'articles', decision)
    assert record == original
    assert 'Alice' not in str(redacted) and redacted['summary'] == record['summary']
    with pytest.raises(ValueError, match='nonliteral'):
        ap.apply_decision(record, 'articles', {'safe': True, 'redactions': [{'field': 'body', 'text': 'Bob'}]})
    assert ap.apply_decision({'prompt': 'Alice?', 'answer': 'Yes', 'explanation': 'Fictional'}, 'questions',
        {'safe': True, 'redactions': [{'field': 'prompt', 'text': 'Alice'}]}) is None
    assert ap.apply_decision({'title': 'Email a@example.com', 'summary': 'Notes', 'body': 'Text'}, 'articles',
                             {'safe': True, 'redactions': []}) is None


def test_automatic_projection_strips_raw_evidence_hashes_and_name_based_ids(store, cfg, first, monkeypatch):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    before = current(store)
    result, audit = ap.project(store, cfg, settings, safe)
    validate_library(result)
    assert current(store) == before
    assert result['articles'] and result['discussions']
    assert not result['questions']  # No independent reference proof in this fixture.
    assert any(x['status'] == 'held-medical' for x in audit)
    raw = json.dumps(result)
    assert 'sourceSha256' not in raw and 'fileModifiedAt' not in raw
    assert not any(record['id'] in raw for g, entries in before.items() for record in entries)
    assert all(d['publication']['reviewedBy'] == 'Automated local privacy gate' for d in result['discussions'])
    def forbidden(*args):
        pytest.fail('Unchanged records must reuse hash-bound privacy decisions')
    again, _ = ap.project(store, cfg, settings, forbidden)
    assert again == result


def test_changed_content_loses_cached_approval_and_withheld_dependencies_are_removed(store, cfg, first, monkeypatch):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    ap.project(store, cfg, settings, safe)
    article = current(store)['articles'][0]
    article['body'] += '\nPrivate patient name: Alice.'
    with store.db:
        store.db.execute('UPDATE library_records SET data=? WHERE kind=? AND id=?',
                         (json.dumps(article), 'articles', article['id']))
    reviewed = []
    def hold(batch, cfg, path):
        reviewed.extend(batch)
        return {x['key']: {'key': x['key'], 'safe': False, 'reason': 'Private detail', 'redactions': []} for x in batch}
    result, _ = ap.project(store, cfg, settings, hold)
    assert len(reviewed) == 1 and 'Alice' in str(reviewed)
    assert all(a['title'] != article['title'] for a in result['articles'])
    assert 'Alice' not in json.dumps(result)
    validate_library(result)


def test_no_clinical_projection_from_synthetic_records(store, cfg, first):
    run(store, cfg)
    with pytest.raises(ValueError, match='Synthetic'):
        ap.project(store, cfg, {'authorizationRef': 'fixture'}, safe)


def test_real_export_cannot_silently_disable_the_patient_name_policy(store,cfg,first,monkeypatch):
    settings=clinical_fixture(store,cfg,first,monkeypatch);settings.pop('patientNamePolicy')
    with pytest.raises(ValueError,match='patient-name policy'):ap.project(store,cfg,settings,safe)


def test_oversize_record_is_held_without_truncating_or_blocking_other_records(store, cfg, first, monkeypatch):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    article = current(store)['articles'][0]
    article['body'] = 'Lengthy educational note. ' * 2000
    with store.db:
        store.db.execute('UPDATE library_records SET data=? WHERE kind=? AND id=?',
                         (json.dumps(article), 'articles', article['id']))
    seen = []
    def capture(batch, cfg, path):
        assert ap.messages_budget(ap.privacy_messages(batch), cfg['provider'])['fits']
        seen.extend(batch)
        return safe(batch, cfg, path)
    result, audit = ap.project(store, cfg, settings, capture)
    assert any(x['id'] == article['id'] and x['status'] == 'held-context' for x in audit)
    assert result['articles'] and all(a['body'] != article['body'] for a in result['articles'])
    assert not any(article['body'] in str(x) for x in seen)
    assert next(a for a in current(store)['articles'] if a['id'] == article['id'])['body'] == article['body']


def test_incomplete_or_invented_gate_decisions_cannot_publish(store, cfg, first, monkeypatch):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    with pytest.raises(ValueError, match='coverage'):
        ap.project(store, cfg, settings, lambda *args: {})
    assert not (store.root / 'publication/last-deployment.json').exists()


def test_publication_waits_for_main_worker_and_never_publishes_pre_authorization_runs(store, cfg, first, monkeypatch):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    monkeypatch.setattr(ap.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(ap.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, 'activating\n'))
    assert ap.cycle(store, cfg, settings, safe)['status'] == 'waiting-for-processing'
    monkeypatch.setattr(ap.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 3, 'inactive\n'))
    settings['notBefore'] = '2999-01-01T00:00:00Z'
    with pytest.raises(ValueError, match='future runs only'):
        ap.cycle(store, cfg, settings, safe)


def test_simultaneous_idle_import_poll_cannot_starve_publication(store, cfg, first, monkeypatch):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    states = iter(['activating', 'active', 'inactive'])
    observed = []
    def command(args, **kwargs):
        state = next(states)
        observed.append(state)
        return subprocess.CompletedProcess(args, 0 if state == 'active' else 3, state + '\n')
    monkeypatch.setattr(ap.subprocess, 'run', command)
    monkeypatch.setattr(ap.time, 'sleep', lambda seconds: None)
    result = ap.cycle(store, cfg, settings, safe, deploy=False)
    assert result['status'] == 'local-preview-only' and result['counts']['articles']
    assert observed == ['activating', 'active', 'inactive']


def test_busy_extraction_is_never_waited_out_or_unknown_service_assumed_idle(store, first, monkeypatch):
    monkeypatch.setattr(ap.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 3, 'activating\n'))
    monkeypatch.setattr(ap.time, 'sleep', lambda seconds: pytest.fail('Actual queued work must defer immediately'))
    assert not ap.processing_is_idle(store)
    monkeypatch.setattr(ap.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, ''))
    with pytest.raises(RuntimeError, match='service state'):
        ap.processing_is_idle(store)


def test_raw_source_appendix_and_archive_topics_are_never_public_candidates():
    lib = {'topics': [{'id': 'source-archive'}, {'id': 'ecg'}], 'articles': [], 'cases': [], 'questions': [],
           'shifts': [], 'discussions': [
               {'topics': ['source-archive'], 'account': 'Secret source'},
               {'topics': ['ecg'], 'account': 'Useful lesson\n\nRecorded source wording:\nSecret raw transcript', 'segments': []}]}
    result = ap.prepared(lib)
    assert len(result['discussions']) == 1
    assert result['discussions'][0]['account'] == 'Useful lesson'
    assert 'Secret' not in json.dumps(result)
    assert 'Secret raw transcript' in str(lib)


def test_retry_receipt_only_written_after_all_real_deploy_steps_succeed(store, cfg, first, monkeypatch, tmp_path):
    settings = clinical_fixture(store, cfg, first, monkeypatch)
    checkout = tmp_path / 'website'
    (checkout / 'content/public').mkdir(parents=True)
    settings['checkout'] = str(checkout)
    monkeypatch.setattr(ap, 'REPO', checkout)
    calls = []
    def command(args, **kw):
        if args[0] == 'systemctl':
            return subprocess.CompletedProcess(args, 3, 'inactive\n')
        calls.append(args[-1])
        assert kw['env']['LIBRARY_DATASET'] == 'production'
        if args[-1] == 'deploy' and calls.count('deploy') == 1:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(ap.subprocess, 'run', command)
    with pytest.raises(subprocess.CalledProcessError):
        ap.cycle(store, cfg, settings, safe)
    assert not (store.root / 'publication/last-deployment.json').exists()
    assert (checkout / 'content/public/topics.json').exists()
    result = ap.cycle(store, cfg, settings, safe)
    assert result['status'] == 'published'
    assert load_json(store.root / 'publication/last-deployment.json')['revision']
    assert ap.cycle(store, cfg, settings, safe)['status'] == 'up-to-date'
    assert calls == ['check', 'build', 'deploy', 'check', 'build', 'deploy']
