from vet_pipeline import shift_workflow as w
from vet_pipeline.runner import run
from vet_pipeline.util import load_json,write_json,digest_file
from vet_pipeline.library import current,validate_library
import pytest


@pytest.mark.parametrize('question_format',['legacy','flashcard','multiple-choice','multiple-select'])
def test_shift_projection_saves_sources_articles_cards_and_replays_without_duplicates(store,cfg,first,tmp_path,question_format):
    run(store,cfg,transcribe_only=True)
    job=dict(store.jobs()[0]);t=load_json(store.root/'transcripts'/(first+'.json'))
    root=tmp_path/'shift';root.mkdir();write_json(root/'transcripts'/(first+'.json'),t)
    sources={}
    for i,s in enumerate(t['segments'][:2]):sources[f'b{i+1:04d}']={'recordingId':first,'text':s['text'],'start':s['start'],'end':s['end'],'eligible':True,'segments':[]}
    write_json(root/'sources.json',sources)
    write_json(root/'experiment.json',{'shiftId':job['shift_id'],'sourcesSha256':digest_file(root/'sources.json'),'status':'complete'})
    ev=[{'source':'b0001','quote':sources['b0001']['text']}]
    write_json(root/'index-map.json',{'episodes':[{'title':'Synthetic teaching','patient_label':None,'association':'unassigned','association_reason':'No identity inference','identity_evidence':[],'sources':['b0001']}]})
    data={'title':'Synthetic teaching','summary':'Source-supported synthetic learning.','summary_evidence':ev,'association_note':'No clinical identity inferred.','facts':[{'kind':'observation','text':sources['b0001']['text'],'evidence':ev}], 'practical_lessons':[],'uncertainties':['Outcome not established.'],'study_questions':[{'prompt':'Which general principle was described?','answer':'Preserve uncertainty.','explanation':'Synthetic testing only.','evidence':ev}], 'knowledge_topics':[{'key':'synthetic-teaching','title':'Synthetic teaching','summary':'Synthetic learning.','account':'Preserve the recorded uncertainty.','evidence':ev}]}
    q=data['study_questions'][0]
    if question_format!='legacy':q['format']=question_format
    if question_format=='multiple-choice':
        q.pop('answer');q.update(correct={'id':'a','text':'Preserve uncertainty.'},distractors=[{'id':key,'text':text} for key,text in [('b','Assume certainty.'),('c','Ignore uncertainty.'),('d','Omit the unknowns.')]])
    if question_format=='multiple-select':
        q.pop('answer');q.update(choices=[{'id':key,'text':text} for key,text in [('a','Preserve uncertainty.'),('b','Retain unknowns.'),('c','Invent missing findings.')]],correctIds=['a','b'])
    write_json(root/'calls/episode-001.json',{'data':data})
    w.persist(store,root,cfg);before=current(store)
    w.persist(store,root,cfg);after=current(store)
    assert before==after
    validate_library(after)
    assert len(after['articles'])==1 and len(after['questions'])==1
    saved_question=after['questions'][0]
    assert saved_question['format']==('flashcard' if question_format=='legacy' else question_format)
    from vet_pipeline.question_verification import materials
    parts=materials(saved_question)
    if question_format in ['multiple-choice','multiple-select']:
        assert 'answer' not in saved_question
        assert sum(p['role']=='correct-answer' for p in parts.values())==(1 if question_format=='multiple-choice' else 2)
        assert any(p['role']=='incorrect-distractor' for p in parts.values())
    assert after['articles'][0]['sourceDiscussionIds']
    assert next(d for d in after['discussions'] if d['id']==after['articles'][0]['sourceDiscussionIds'][0])['articleIds']==[after['articles'][0]['id']]
    assert any('unclassified-source' in d['topics'] for d in after['discussions'])
    assert all(x['publication']['status']=='draft' for x in after['articles'])
    assert store.get(first)['stage']=='done'


def test_bad_topic_citation_does_not_discard_good_topic():
    source={'b0001':{'text':'Exact source teaching.','eligible':True,'recordingId':'r-test','segments':[]}}
    good={'key':'topic','title':'Teaching','summary':'Teaching','account':'Teaching account.','evidence':[{'source':'b0001','quote':'Exact source teaching.'}]}
    bad={**good,'evidence':[{'source':'invented','quote':'Invented fact'}]}
    accepted,rejected=w.validate_topics([bad,good],source)
    assert accepted==[good] and len(rejected)==1


def test_all_transcription_finishes_before_isolated_shift_extraction(store,cfg,first,monkeypatch):
    from vet_pipeline import runner,shift_context as sc
    from vet_pipeline.config import config
    from vet_pipeline.ingest import ingest
    from vet_pipeline.util import REPO
    other,_=ingest(store,REPO/'fixtures/pipeline/transcripts/02-followup.json',
                   's-other-shift','2026-10-23','synthetic','test')
    runner.run(store,cfg,transcribe_only=True)
    original=dict(store.get(first))
    pending={**original,'id':'r-pending','sha256':'f'*64,'shift_id':'s-pending-shift','stage':'transcribe'}
    with store.db:
        store.db.execute('INSERT INTO jobs ('+','.join(pending)+') VALUES ('+','.join('?' for _ in pending)+')',tuple(pending.values()))
    monkeypatch.setattr(runner,'run',lambda *a,**kw:[])
    monkeypatch.setattr(sc,'local_config',config)
    monkeypatch.setattr(sc,'verified_local_model',lambda c:'synthetic-model')
    seen=[];expected={original['shift_id']:{first},'s-other-shift':{other}}
    def model_run(root,on_checkpoint=None):
        exp=load_json(root/'experiment.json');seen.append(exp['shiftId'])
        assert {s['recordingId'] for s in load_json(root/'sources.json').values()}==expected[exp['shiftId']]
        exp['status']='complete';write_json(root/'experiment.json',exp)
    monkeypatch.setattr(sc,'run',model_run)
    monkeypatch.setattr(w,'persist',lambda *a:None)
    waiting=w.run(store,cfg)
    assert seen==[] and any(x.get('pendingRecordings')==1 and x['status']=='deferred' for x in waiting)
    assert not (store.root/'shift-extraction').exists()
    store.update('r-pending',stage='review')
    completed=w.run(store,cfg)
    assert set(seen)==set(expected) and len(seen)==2
    assert sum(x.get('status')=='done' for x in completed)==2


def test_enabled_mode_dispatches_to_whole_shift_not_per_recording_model(store,cfg,monkeypatch):
    cfg['shift_context']['enabled']=True
    seen=[]
    monkeypatch.setattr(w,'run',lambda *args:seen.append(args) or [{'status':'whole-shift-dispatched'}])
    assert run(store,cfg)[0]['status']=='whole-shift-dispatched' and seen


def test_question_checking_cannot_occupy_gpu_before_transcription_finishes(store,cfg,first,monkeypatch):
    from vet_pipeline import question_verification
    cfg['shift_context']['enabled']=True;cfg['question_verification']['enabled']=True
    store.update(first,stage='transcribe')
    monkeypatch.setattr(w,'run',lambda *args:[{'status':'deferred'}])
    checked=[];monkeypatch.setattr(question_verification,'run_checks',lambda *args:checked.append(True))
    run(store,cfg)
    assert checked==[]
    store.update(first,stage='review')
    run(store,cfg)
    assert checked==[True]


def test_workflow_contract_preserves_legacy_schema_and_adds_medical_policy(tmp_path):
    from vet_pipeline import shift_context as sc
    write_json(tmp_path/'topic-index.json',[])
    text,schema=w.detail_contract(tmp_path,'Whole-shift task')
    assert 'knowledge_topics' in schema['required'] and 'knowledge_topics' not in sc.DETAIL_SCHEMA['required']
    assert 'MEDICAL knowledge' in text and 'Different speaker labels' in text
    assert schema['properties']['study_questions']['items']==sc.QUESTION


def test_normal_full_shift_path_uses_large_context_and_saves_complete_draft(store,cfg,first,monkeypatch):
    from vet_pipeline import shift_context as sc
    from vet_pipeline.config import config
    cfg['shift_context']['enabled']=True
    template=store.root/'synthetic-chat.jinja';template.write_text('Synthetic template')
    cfg['shift_context'].update(chat_template_path=str(template),chat_template_sha256=digest_file(template),native_reasoning_effort='xhigh',stream_responses=True,temperature=1.0)
    monkeypatch.setattr(sc,'local_config',config)
    monkeypatch.setattr(sc,'verified_local_model',lambda c:'synthetic-model')
    def model_run(root,on_checkpoint=None):
        exp=load_json(root/'experiment.json')
        assert exp['provider']['context_window']==98304 and exp['provider']['max_output_tokens']==32768
        assert exp['medicalOnlyQuestions'] and exp['libraryWorkflow'] and exp['repetitionExclusionThreshold']==5
        assert exp['chatTemplatePath']==str(template) and exp['chatTemplateSha256']==digest_file(template)
        assert exp['nativeReasoningEffort']=='xhigh' and exp['streamResponses'] and exp['provider']['temperature']==1.0
        sources=load_json(root/'sources.json');key=next(iter(sources));ev=[{'source':key,'quote':sources[key]['text']}]
        write_json(root/'index-map.json',{'episodes':[{'title':'Synthetic learning','patient_label':None,'association':'unassigned','association_reason':'Unknown','identity_evidence':[],'sources':[key]}]})
        data={'title':'Synthetic learning','summary':'A source-linked discussion.','summary_evidence':ev,'association_note':'Unknown identity.','facts':[{'kind':'observation','text':sources[key]['text'],'evidence':ev}],'practical_lessons':[],'uncertainties':['Outcome unknown.'],'study_questions':[],'knowledge_topics':[]}
        write_json(root/'calls/episode-001.json',{'data':data})
        on_checkpoint(root)
        exp['status']='complete';write_json(root/'experiment.json',exp)
    monkeypatch.setattr(sc,'run',model_run)
    result=run(store,cfg)
    assert any(x.get('stage')=='whole-shift' and x['status']=='done' for x in result)
    assert store.get(first)['stage']=='done'
    assert current(store)['discussions']
    validate_library(current(store))
