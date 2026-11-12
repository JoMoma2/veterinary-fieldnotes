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


@pytest.mark.parametrize('form',['multiple-choice','multiple-select'])
def test_new_question_formats_keep_options_evidence_and_readable_reports(store,tmp_path,monkeypatch,form):
    from vet_pipeline import shift_workflow as w
    root=prepared(store,tmp_path,monkeypatch)
    exp=load_json(root/'experiment.json');exp['studyQuestionFormats']='mixed-v1';write_json(root/'experiment.json',exp)
    write_json(root/'topic-index.json',[])
    task,schema=w.detail_contract(root,'Synthetic task')
    assert 'multiple-choice' in task and 'multiple-select' in task and 'do not force' in task
    q={'format':form,'prompt':'Which general principle is supported?','explanation':'Synthetic explanation.',
       'evidence':[{'source':'b0001','quote':'patient is uncomfortable.'}]}
    if form=='multiple-choice':
        q.update(correct={'id':'a','text':'Preserve uncertainty.'},distractors=[{'id':k,'text':v} for k,v in [('b','Assume a diagnosis.'),('c','Invent outcomes.'),('d','Hide unknowns.')]])
    else:
        q.update(choices=[{'id':k,'text':v} for k,v in [('a','Preserve uncertainty.'),('b','Retain unknowns.'),('c','Invent outcomes.')]],correctIds=['a','b'])
    value=detail();value.update(study_questions=[q],knowledge_topics=[])
    accepted,rejected=s.validate_detail(value,load_json(root/'sources.json'),True,(),schema)
    assert not rejected and accepted['study_questions']==[q]
    write_json(root/'index-map.json',index());write_json(root/'calls/episode-001.json',{'data':accepted,'metrics':{'seconds':.1,'prompt_eval_count':123}})
    s.render(root)
    assert 'Invent outcomes.' in (root/'review/shift-context.html').read_text()
    assert 'A: Preserve uncertainty.' in (root/'readable-notes.md').read_text()
    bad=copy.deepcopy(value)
    if form=='multiple-choice':bad['study_questions'][0]['distractors'][0]['id']='a'
    else:bad['study_questions'][0]['correctIds']=['unknown']
    kept,rejected=s.validate_detail(bad,load_json(root/'sources.json'),True,(),schema)
    assert kept['facts'] and not kept['study_questions'] and rejected


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


def test_focused_variant_reuses_only_identical_global_map(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    value = index(); text = s.prompt(s.full_context(root), s.INDEX_TASK, s.INDEX_SCHEMA)
    fp = s.request_fingerprint(text, load_json(root / 'experiment.json'))
    write_json(root / 'index-map.json', value)
    write_json(root / 'calls/index.json', {'promptSha256': fp, 'data': value, 'metrics': {'seconds': .1}})
    focused = s.prepare_focused(root, root / 'focused')
    assert s.call(focused, {}, s.full_context(focused), s.INDEX_TASK, s.INDEX_SCHEMA, 'index') == value
    assert s.full_context(root) == s.full_context(focused)
    assert not list((focused / 'calls').glob('episode-*.json'))
    assert load_json(focused / 'experiment.json')['status'] == 'waiting-for-reference'


def test_focused_packet_keeps_original_whole_context_and_budgets_extra_copies(store, tmp_path, monkeypatch):
    from tokenizers import Tokenizer, models, pre_tokenizers
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    tokenizer = Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]'))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    path = tmp_path / 'synthetic-tokenizer.json'; tokenizer.save(str(path))
    cfg = {'provider': {'tokenizer_path': str(path), 'context_window': 81920, 'max_output_tokens': 32768}}
    context = s.full_context(root) + '\n' + 'retained-whole-night ' * 1000
    task, copied = s.focused_task(index()['episodes'][0], sources, {}, context, cfg)
    assert copied == ['b0001', 'b0002']
    assert 'Sample patient is uncomfortable.' in task
    serialized = s.prompt(context, task, s.DETAIL_SCHEMA)
    assert 'retained-whole-night ' * 1000 in serialized
    assert len(tokenizer.encode(serialized).ids) + 32768 + 512 <= 81920
    # Limit only the extra duplicate packet; the original night remains intact.
    total = len(tokenizer.encode(s.prompt(context, task, s.DETAIL_SCHEMA, True), add_special_tokens=False).ids)
    cfg['provider']['context_window'] = total + 32768 + 512 - 1
    limited, copied = s.focused_task(index()['episodes'][0], sources, {}, context, cfg)
    assert copied == ['b0001']
    assert 'retained-whole-night ' * 1000 in s.prompt(context, limited, s.DETAIL_SCHEMA)
    assert len(tokenizer.encode(s.prompt(context, limited, s.DETAIL_SCHEMA), add_special_tokens=False).ids) + 32768 + 512 <= cfg['provider']['context_window']


def test_medical_question_policy_filters_case_recall_without_losing_notes(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); value = detail()
    value['study_questions'] = [{'prompt': 'What was Sample diagnosed with?', 'answer': 'Unknown.',
                                'explanation': 'Case recall.', 'evidence': [{'source': 'b0002', 'quote': 'diagnosis unknown.'}]}]
    accepted, rejected = s.validate_detail(value, load_json(root / 'sources.json'), True, ['Sample'])
    assert not accepted['study_questions'] and accepted['facts']
    assert rejected[0]['section'] == 'study_questions'
    assert 'STUDY QUESTION POLICY' in s.detail_task(index()['episodes'][0], load_json(root / 'sources.json'), medical_only=True)
    assert 'STUDY QUESTION POLICY' not in s.detail_task(index()['episodes'][0], load_json(root / 'sources.json'))


def test_explicit_speaker_uncertainty_note_is_versioned_without_changing_old_requests(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    prior = s.detail_task(index()['episodes'][0], sources)
    assert 'SPEAKER ID UNCERTAINTY' not in prior
    revised = s.detail_task(index()['episodes'][0], sources, extra_instructions=s.SPEAKER_ID_UNCERTAINTY)
    assert revised.startswith(prior) and 'Different speaker labels do NOT prove different people' in revised
    assert 'The same label does NOT prove one person' in revised


def test_speaker_metadata_preserves_all_original_words_and_roles_need_real_ids(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    sources['b0001']['speakerSegments'] = [{**sources['b0001']['segments'][0], 'speaker': 'Speaker_001'}]
    write_json(root / 'sources.json', sources)
    context = s.full_context(root)
    assert '{S001} Sample patient is uncomfortable.' in context
    assert 'Returning to Sample; diagnosis unknown.' in context
    value = index(); value['speaker_annotations'] = [{
        'speaker': 'Speaker_099', 'role': 'veterinarian', 'relationship': '', 'confidence': .9,
        'reason': 'Unsupported synthetic proposal.', 'alternatives': [],
        'evidence': [{'source': 'b0001', 'quote': 'Sample patient'}]}]
    accepted, rejected = s.project_index(value, sources, ['Speaker_001'])
    assert accepted['speaker_annotations'] == [] and rejected
    value['speaker_annotations'][0]['speaker'] = 'Speaker_001'
    accepted, rejected = s.project_index(value, sources, ['Speaker_001'])
    assert len(accepted['speaker_annotations']) == 1
    # Validation checks speaker/source provenance, not whether a role is true.


def test_owner_visible_review_is_standalone_escaped_and_outside_git(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch)
    owner = tmp_path / 'owner-results'
    experiment = load_json(root / 'experiment.json'); experiment['ownerResultsDirectory'] = str(owner)
    write_json(root / 'experiment.json', experiment)
    write_json(root / 'index-map.json', index())
    data = detail(); data['summary'] = '<script>untrusted source</script>'
    write_json(root / 'calls/episode-001.json', {'data': data, 'metrics': {'seconds': 1}})
    s.render(root)
    html = (owner / 'Results.html').read_text()
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert 'untrusted source' in (owner / 'Medical-notes.md').read_text()
    assert (owner / 'Results.html').stat().st_mode & 0o077 == 0


def test_excluded_repetition_is_not_reintroduced_as_context_or_citable_evidence(store, tmp_path, monkeypatch):
    from vet_pipeline.repetition_filter import MARKER
    root = prepared(store, tmp_path, monkeypatch); sources = load_json(root / 'sources.json')
    original = sources['b0001']['text']
    sources['b0001']['repeatExcludedSpans'] = [[0, len(original)]]
    write_json(root / 'sources.json', sources)
    assert MARKER in s.full_context(root) and original not in s.full_context(root)
    assert 'Returning to Sample' in s.full_context(root)
    with pytest.raises(ValueError, match='exact eligible'):
        s.validate_evidence([{'source': 'b0001', 'quote': original}], sources)
    assert sources['b0001']['text'] == original


def test_raw_chatml_thinking_keeps_native_reply_and_separate_reasoning(store, tmp_path, monkeypatch):
    import httpx
    from tokenizers import Tokenizer, models
    root = prepared(store, tmp_path, monkeypatch)
    tokenizer = tmp_path / 'tokenizer.json'
    Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(tokenizer))
    exp = load_json(root / 'experiment.json')
    original = s.request_fingerprint('same input', exp)
    exp['requestFormat'] = 'raw-chatml'
    assert s.request_fingerprint('same input', exp) != original
    write_json(root / 'experiment.json', exp)
    cfg = {'provider': {**exp['provider'], 'kind': 'ollama',
                       'base_url': 'http://127.0.0.1:11434', 'tokenizer_path': str(tokenizer)}}
    monkeypatch.setattr(s, 'check_resources', lambda *a: None)
    requests = []
    def reply(request):
        body = json.loads(request.content); requests.append(body)
        assert request.url.path == '/api/generate'
        assert body['raw'] is True and body['think'] is True and 'format' not in body
        assert body['prompt'].endswith('<|im_start|>assistant\n<think>\n')
        assert 'messages' not in body and 'Sample patient' in body['prompt']
        return httpx.Response(200, json={'response': 'synthetic reasoning</think>\n' + json.dumps(index()),
                                        'done_reason': 'stop', 'prompt_eval_count': 100})
    client = httpx.Client
    monkeypatch.setattr(s.httpx, 'Client', lambda **kw: client(transport=httpx.MockTransport(reply), **kw))
    result = s.call(root, cfg, s.full_context(root), s.INDEX_TASK, s.INDEX_SCHEMA, 'index')
    assert result['episodes'][0]['patient_label'] == 'Sample'
    saved = load_json(root / 'calls/index-raw.json')
    assert saved['response']['response'].startswith('synthetic reasoning</think>')
    assert saved['metrics']['reasoningCharacters'] == len('synthetic reasoning')
    assert s.call(root, cfg, s.full_context(root), s.INDEX_TASK, s.INDEX_SCHEMA, 'index') == result
    assert len(requests) == 1


def test_raw_thinking_delimiter_is_required_and_reasoning_is_not_json_evidence():
    exp = {'thinking': True, 'requestFormat': 'raw-chatml'}
    with pytest.raises(ValueError, match='delimiter'):
        s.response_content({'response': '{"plausible": true}'}, exp)
    raw = {'response': 'Do not treat {"invented": true} as evidence.</think>\n```json\n{"final": true}\n```'}
    assert json.loads(s.response_content(raw, exp)) == {'final': True}


def test_native_template_budget_preserves_source_and_binds_template_hash(tmp_path):
    path = tmp_path / 'template.jinja'
    path.write_text('{% for m in messages %}{{m.role}}:{{m.content}}\n{% endfor %}assistant:')
    exp = {'thinking': True, 'chatTemplatePath': str(path), 'chatTemplateSha256': digest_file(path),
           'systemPrefix': '<|think|>', 'reasoningEffort': 'high', 'modelDigest': 'fixture',
           'provider': {}, 'gpuLayers': 0, 'version': 'fixture'}
    text = s.experiment_prompt('ALL SOURCE WORDS', 'Extract evidence.', s.INDEX_SCHEMA, exp)
    assert 'ALL SOURCE WORDS' in text and 'system:<|think|>' in text and 'Extract evidence.' in text
    first = s.request_fingerprint(text, exp)
    assert s.request_fingerprint(text, {**exp, 'reasoningEffort': 'low'}) != first
    path.write_text('Changed template')
    with pytest.raises(ValueError, match='template changed'):
        s.experiment_prompt('ALL SOURCE WORDS', 'Extract evidence.', s.INDEX_SCHEMA, exp)


def test_stream_retains_partial_reply_and_assembles_separate_thoughts(tmp_path):
    import httpx
    root = tmp_path / 'run'; (root / 'calls').mkdir(parents=True)
    events = [{'message': {'thinking': 'Private reasoning.'}},
              {'message': {'content': '{"value":'}}, {'message': {'content': 'null}'}},
              {'message': {'content': ''}, 'done': True, 'done_reason': 'stop', 'eval_count': 12}]
    def response(request):
        return httpx.Response(200, text='\n'.join(json.dumps(x) for x in events))
    with httpx.Client(transport=httpx.MockTransport(response), base_url='http://localhost') as client:
        raw = s.streamed_reply(client, '/api/chat', {}, root, 'index')
    assert raw['message']['thinking'] == 'Private reasoning.'
    assert json.loads(raw['message']['content']) == {'value': None}
    assert load_json(root / 'calls/index-live.json')['done'] is True
    assert len(next((root / 'calls').glob('*-stream-*.jsonl')).read_text().splitlines()) == 4
    events.pop()
    with httpx.Client(transport=httpx.MockTransport(response), base_url='http://localhost') as client:
        with pytest.raises(ValueError, match='without completion'):
            s.streamed_reply(client, '/api/chat', {}, root, 'interrupted')
    assert next((root / 'calls').glob('interrupted-stream-*.jsonl')).exists()


def test_output_exhaustion_does_not_repeat_identical_expensive_request(store, tmp_path, monkeypatch):
    root = prepared(store, tmp_path, monkeypatch); calls = []
    def exhausted(*args):
        calls.append(1); raise s.OutputBudgetError('Retained output budget exhaustion')
    monkeypatch.setattr(s, 'call', exhausted)
    with pytest.raises(s.OutputBudgetError):
        s.bounded_call(root, {}, '', '', s.INDEX_SCHEMA, 'index')
    assert len(calls) == 1
