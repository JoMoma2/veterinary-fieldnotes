import copy
import hashlib
import json
from pathlib import Path

import pytest

from vet_pipeline import shift_context as s
from vet_pipeline.ingest import ingest
from vet_pipeline.util import digest_file, load_json, write_json


def prepared(store, tmp_path, monkeypatch):
    for number, text in enumerate(['Sample patient is uncomfortable.', 'Returning to Sample; diagnosis unknown.']):
        path = tmp_path / f'synthetic-{number}.json'
        transcript = {'segments': [{'start': 0, 'end': 2, 'text': text}]}
        write_json(path, transcript)
        rid, _ = ingest(store, path, 's-context', '2000-01-01', 'synthetic', 'test')
        write_json(store.root / 'transcripts' / f'{rid}.json', transcript)
    monkeypatch.setattr(s, 'local_config', lambda p: {'provider': {'model': 'fixture', 'context_window': 8192, 'max_output_tokens': 4096}, 'github': {'enabled': False}})
    monkeypatch.setattr(s, 'verified_local_model', lambda c: 'synthetic-digest')
    return s.prepare(store.root, 's-context', tmp_path / 'experiment', tmp_path / 'profile.toml')


def index():
    return {'episodes': [{'title': 'Synthetic patient episode', 'patient_label': 'Sample',
                         'identity_evidence': [{'source': 'b0001', 'quote': 'Sample patient'}],
                         'association': 'tentative', 'association_reason': 'Explicit return, identity still needs review.',
                         'sources': ['b0001', 'b0002']}], 'limitations': ['Synthetic test only.']}


def detail():
    return {'title': 'Synthetic episode', 'summary': 'The transcript reports discomfort and an unknown diagnosis.',
            'summary_evidence': [{'source': 'b0001', 'quote': 'Sample patient is uncomfortable.'}, {'source': 'b0002', 'quote': 'diagnosis unknown.'}],
            'association_note': 'Synthetic source only.',
            'facts': [{'kind': 'observation', 'text': 'Discomfort was described.',
                       'evidence': [{'source': 'b0001', 'quote': 'patient is uncomfortable.'}]}],
            'practical_lessons': [], 'uncertainties': ['Diagnosis not established.'], 'study_questions': []}


def test_prepare_keeps_source_files_and_both_recordings_in_full_context(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    text = s.full_context(root)
    assert 'Sample patient is uncomfortable.' in text and 'Returning to Sample' in text
    assert len(load_json(root / 'sources.json')) == 2
    assert load_json(root / 'experiment.json')['provider']['context_window'] == 81920
    assert not (root / 'extractions').exists()
    for job in store.jobs():
        assert digest_file(store.root / 'transcripts' / (job['id'] + '.json')) == digest_file(root / 'transcripts' / (job['id'] + '.json'))
    html = (root / 'review/shift-context.html').read_text()
    assert 'Private AI draft' in html and 'No Whisper inference' in html


def test_explicit_patient_label_needs_eligible_literal_identity_evidence(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    assert s.validate_index(index(), sources)
    wrong = index(); wrong['episodes'][0]['patient_label'] = 'Another patient'
    with pytest.raises(ValueError, match='literal name'):
        s.validate_index(wrong, sources)
    sources['b0001']['eligible'] = False
    with pytest.raises(ValueError):
        s.validate_index(index(), sources)


def test_bad_citation_is_quarantined_without_discarding_valid_facts(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    value = detail(); bad = copy.deepcopy(value['facts'][0]); bad['evidence'][0]['quote'] = 'Invented diagnosis.'
    value['facts'].append(bad)
    accepted, rejected = s.validate_detail(value, sources)
    assert len(accepted['facts']) == len(rejected) == 1


def test_whole_night_is_supplied_to_each_episode_and_report_is_readable(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); calls = []
    def call(folder, cfg, context, task, schema, key):
        calls.append((key, context))
        value = index() if key == 'index' else detail()
        write_json(folder / 'calls' / (key + '.json'), {'data': value, 'metrics': {'seconds': .1, 'prompt_eval_count': 123}})
        return value
    monkeypatch.setattr(s, 'call', call)
    s.run(root)
    assert [c[0] for c in calls] == ['index', 'episode-001']
    assert calls[0][1] == calls[1][1] and 'Returning to Sample' in calls[1][1]
    assert load_json(root / 'experiment.json')['status'] == 'complete'
    text = (root / 'readable-notes.md').read_text()
    assert 'Discomfort was described' in text and 'Diagnosis not established' in text
    html = (root / 'review/shift-context.html').read_text()
    assert 'Source evidence and audio' in html and '0.00–2.00s' in html
    assert all(row['stage'] == 'transcribe' for row in store.jobs())
    write_json(root / 'calls/episode-001-raw-123456789.json', {'metrics': {'seconds': 99999}})
    s.render(root)
    assert 'Saved inference wall time: 0.2 s' in (root / 'review/shift-context.html').read_text()


def test_tampered_sources_fail_before_inference(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    (root / 'sources.json').write_text('{}')
    monkeypatch.setattr(s, 'call', lambda *a: pytest.fail('inference on changed sources'))
    with pytest.raises(ValueError, match='Immutable experiment source'):
        s.run(root)


def test_cached_call_binds_complete_prompt_and_reuses_without_gpu(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    context = s.full_context(root); task = 'Synthetic task'
    text = s.prompt(context, task, s.INDEX_SCHEMA)
    write_json(root / 'calls/index.json', {'promptSha256': s.request_fingerprint(text, load_json(root / 'experiment.json')), 'data': index()})
    assert s.call(root, {}, context, task, s.INDEX_SCHEMA, 'index') == index()
    with pytest.raises(ValueError, match='Immutable request changed'):
        s.call(root, {}, context + '\nchanged', task, s.INDEX_SCHEMA, 'index')


def test_invalid_identity_becomes_unassigned_without_losing_episode(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    value = index(); value['episodes'][0]['patient_label'] = 'Invented patient'
    accepted, rejected = s.project_index(value, sources)
    assert len(accepted['episodes']) == 1 and rejected
    assert accepted['episodes'][0]['patient_label'] is None
    assert accepted['episodes'][0]['association'] == 'unassigned'
    assert accepted['episodes'][0]['sources'] == ['b0001', 'b0002']


def test_budget_model_setting_change_invalidates_cache(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    exp = load_json(root / 'experiment.json'); text = s.prompt(s.full_context(root), 'test', s.INDEX_SCHEMA)
    before = s.request_fingerprint(text, exp)
    exp['provider']['context_window'] += 1024
    assert s.request_fingerprint(text, exp) != before


def test_invalid_summary_is_not_displayed_as_accepted_prose(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    value = detail(); value['summary_evidence'] = []; value['summary'] = '<script>unaccepted draft</script>'
    accepted, rejected = s.validate_detail(value, sources)
    assert accepted['summary'].startswith('No fully cited summary')
    assert accepted['facts'] and rejected[0]['section'] == 'summary'
    accepted.pop('_citationRepairs')
    write_json(root / 'index-map.json', index())
    write_json(root / 'calls/episode-001.json', {'data': accepted, 'metrics': {'seconds': .1}})
    write_json(root / 'calls/episode-001-rejected.json', rejected)
    s.render(root)
    text = (root / 'review/shift-context.html').read_text()
    assert 'Unaccepted model narrative' in text and '&lt;script&gt;unaccepted draft' in text
    assert '<script>unaccepted draft' not in text


def test_resource_deferral_does_not_consume_attempts(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    def defer(*args):
        raise s.ProcessingDeferred('synthetic shared resource wait')
    monkeypatch.setattr(s, 'call', defer)
    with pytest.raises(s.ProcessingDeferred):
        s.bounded_call(root, {}, '', '', s.INDEX_SCHEMA, 'index')
    assert load_json(root / 'attempts.json')['index']['attempts'] == 0


def test_retries_are_bounded_and_private_outputs_remain(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); attempts = []
    def fail(*args):
        attempts.append(1); raise ValueError('Synthetic malformed model output')
    monkeypatch.setattr(s, 'call', fail); monkeypatch.setattr(s.time, 'sleep', lambda t: None)
    with pytest.raises(RuntimeError, match='Bounded'):
        s.bounded_call(root, {}, '', '', s.INDEX_SCHEMA, 'index')
    assert len(attempts) == 3
    assert (root / 'review/shift-context.html').exists()


def test_one_failed_episode_does_not_discard_other_results(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    def request(folder, cfg, context, task, schema, key):
        if key == 'index':
            value = index(); value['episodes'].append(copy.deepcopy(value['episodes'][0]))
        elif key == 'episode-001':
            raise RuntimeError('Synthetic exhausted episode')
        else:
            value = detail()
        write_json(folder / 'calls' / (key + '.json'), {'data': value, 'metrics': {'seconds': .1, 'prompt_eval_count': 123}})
        return value
    monkeypatch.setattr(s, 'bounded_call', request)
    s.run(root)
    assert load_json(root / 'experiment.json')['status'] == 'complete-with-failed-episodes'
    assert (root / 'calls/episode-002.json').exists()
    assert 'failed after bounded retries' in (root / 'review/shift-context.html').read_text()


def test_name_retrieval_considers_later_mentions_without_merging_them(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    episode = index()['episodes'][0]; episode['sources'] = ['b0001']
    hints = s.name_hints(episode, sources)
    assert hints['literal_mention_blocks'] == ['b0001', 'b0002']
    assert episode['sources'] == ['b0001']
    assert 'NOT evidence' in hints['warning']
    assert 'HIGH-RECALL SOURCE RETRIEVAL' in s.detail_task(episode, sources)


def test_owner_aliases_are_only_retrieval_hints(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    sources['b0002']['text'] = 'Returning to Example; diagnosis unknown.'
    episode = index()['episodes'][0]
    hints = s.name_hints(episode, sources, {'Sample': ['Example']})
    assert hints['literal_mention_blocks'] == ['b0001', 'b0002']
    assert episode['patient_label'] == 'Sample'


def test_citation_repairs_are_unique_and_never_cross_recordings(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    refs = [{'source': 'b0001', 'quote': 'sample patient'}]
    repairs = s.repair_evidence(refs, sources)
    assert refs[0]['quote'] == 'Sample patient' and repairs
    sources['b0003'] = {**sources['b0001'], 'text': 'Distinct exact supporting quotation.'}
    refs = [{'source': 'b0001', 'quote': sources['b0003']['text']}]
    assert s.repair_evidence(refs, sources)
    assert refs[0]['source'] == 'b0003'
    sources['b0003']['recordingId'] = 'different-recording'
    with pytest.raises(ValueError):
        s.repair_evidence([{'source': 'b0001', 'quote': sources['b0003']['text']}], sources)
    sources['b0003']['recordingId'] = sources['b0001']['recordingId']
    sources['b0004'] = dict(sources['b0003'])
    with pytest.raises(ValueError):
        s.repair_evidence([{'source': 'b0001', 'quote': sources['b0003']['text']}], sources)


def test_reprojection_preserves_raw_response_and_versions_original_checkpoint(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    raw = detail(); raw['summary_evidence'][0]['quote'] = 'sample patient is uncomfortable.'
    write_json(root / 'calls/episode-001.json', {'promptSha256': 'same-request', 'data': detail(), 'metrics': {'seconds': 1}})
    raw_path = root / 'calls/episode-001-raw.json'
    write_json(raw_path, {'promptSha256': 'same-request', 'response': {'message': {'content': json.dumps(raw)}}})
    before_raw = digest_file(raw_path); before_call = digest_file(root / 'calls/episode-001.json')
    assert s.reproject_saved(root) == 1
    assert digest_file(raw_path) == before_raw
    assert (root / 'projection-history' / ('episode-001-' + before_call + '.json')).exists()
    updated = load_json(root / 'calls/episode-001.json')
    assert updated['data']['summary_evidence'][0]['quote'] == 'Sample patient is uncomfortable.'
    assert updated['projection']['version'] == 2
    assert s.reproject_saved(root) == 0
