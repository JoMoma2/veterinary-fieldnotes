from vet_pipeline import shift_workflow as w
from vet_pipeline.runner import run
from vet_pipeline.util import load_json,write_json,digest_file
from vet_pipeline.library import current,validate_library


def test_shift_projection_saves_sources_articles_cards_and_replays_without_duplicates(store,cfg,first,tmp_path):
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
    write_json(root/'calls/episode-001.json',{'data':data})
    w.persist(store,root,cfg);before=current(store)
    w.persist(store,root,cfg);after=current(store)
    assert before==after
    validate_library(after)
    assert len(after['articles'])==1 and len(after['questions'])==1
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


def test_enabled_mode_dispatches_to_whole_shift_not_per_recording_model(store,cfg,monkeypatch):
    cfg['shift_context']['enabled']=True
    seen=[]
    monkeypatch.setattr(w,'run',lambda *args:seen.append(args) or [{'status':'whole-shift-dispatched'}])
    assert run(store,cfg)[0]['status']=='whole-shift-dispatched' and seen


def test_workflow_contract_preserves_legacy_schema_and_adds_medical_policy(tmp_path):
    from vet_pipeline import shift_context as sc
    write_json(tmp_path/'topic-index.json',[])
    text,schema=w.detail_contract(tmp_path,'Whole-shift task')
    assert 'knowledge_topics' in schema['required'] and 'knowledge_topics' not in sc.DETAIL_SCHEMA['required']
    assert 'MEDICAL knowledge' in text and 'Different speaker labels' in text


def test_normal_full_shift_path_uses_large_context_and_saves_complete_draft(store,cfg,first,monkeypatch):
    from vet_pipeline import shift_context as sc
    from vet_pipeline.config import config
    cfg['shift_context']['enabled']=True
    monkeypatch.setattr(sc,'local_config',config)
    monkeypatch.setattr(sc,'verified_local_model',lambda c:'synthetic-model')
    def model_run(root,on_checkpoint=None):
        exp=load_json(root/'experiment.json')
        assert exp['provider']['context_window']==98304 and exp['provider']['max_output_tokens']==32768
        assert exp['medicalOnlyQuestions'] and exp['libraryWorkflow'] and exp['repetitionExclusionThreshold']==5
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
