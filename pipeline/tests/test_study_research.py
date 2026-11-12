import copy
import hashlib
import json
import sqlite3
import pytest
from vet_pipeline import study_research as research
from vet_pipeline import question_verification as verify
from vet_pipeline.publication import record_hash
from vet_pipeline.util import write_json, now


def question():
    return {'schemaVersion':1,'id':'q-test','origin':'authorized-record',
        'publication':{'status':'draft','audience':'private'},'format':'flashcard',
        'topics':['test'],'prompt':'General medical principle?', 'answer':'Supported answer.',
        'explanation':'Private wording from the recording.', 'articleIds':[], 'sourceDiscussionIds':['d-test']}


def supported_revision(store, tmp_path, original, public_prompt=None):
    candidate={**copy.deepcopy(original),'explanation':'Supported explanation.'}
    if public_prompt is not None:candidate['prompt']=public_prompt
    directory=tmp_path/'public-references';directory.mkdir()
    body='General medical principle. Supported answer. Supported explanation.'
    doc={'id':'ref-test','url':'https://www.fda.gov/test','title':'Fictional reference fixture',
         'scope':'Test only','body':body,'bodySha256':hashlib.sha256(body.encode()).hexdigest(),'fetchedAt':now()}
    write_json(directory/'ref-test.json',doc)
    ref={'text':body,**{k:doc[k] for k in ['url','title','scope','bodySha256','fetchedAt']},'documentId':'ref-test'}
    proof={'version':verify.VERSION,'questionSha256':record_hash(candidate),'status':'supported',
        'references':{'ref-test:0':ref},'referencesDirectory':str(directory),
        'referenceSetSha256':hashlib.sha256(json.dumps([('ref-test',doc['bodySha256'])],sort_keys=True).encode()).hexdigest(),
        'components':[{'id':k,'verdict':'supported','reason':'Fictional test evidence',
            'evidence':[{'source':'ref-test:0','quote':'Supported answer.'}]} for k in verify.materials(candidate)],
        'suggested_revision':''}
    write_json(verify.result_path(store,candidate),proof)
    write_json(research.revision_path(store,original),{'version':research.VERSION,
        'originalSha256':record_hash(original),'publicSha256':record_hash(candidate),'question':candidate})
    return candidate,directory


def test_only_independently_supported_public_revision_is_exposed_and_original_stays_unchanged(store,tmp_path):
    original=question();before=copy.deepcopy(original)
    candidate,directory=supported_revision(store,tmp_path,original)
    assert research.public_question(store,original)==candidate and original==before
    changed={**original,'answer':'Different private answer.'}
    assert research.public_question(store,changed)==changed
    doc=json.loads((directory/'ref-test.json').read_text());doc['body']='Changed source';doc['bodySha256']=hashlib.sha256(doc['body'].encode()).hexdigest();write_json(directory/'ref-test.json',doc)
    assert research.public_question(store,original)==original


def test_missing_proof_or_changed_scope_never_publishes_a_revision(store,tmp_path):
    original=question();candidate={**original,'explanation':'Unverified proposal.'}
    path=research.revision_path(store,original)
    write_json(path,{'version':research.VERSION,'originalSha256':record_hash(original),
        'publicSha256':record_hash(candidate),'question':candidate})
    assert research.public_question(store,original)==original
    candidate,directory=supported_revision(store,tmp_path,original)
    saved=json.loads(path.read_text());saved['question']['sourceDiscussionIds']=['d-different-case'];saved['publicSha256']=record_hash(saved['question']);write_json(path,saved)
    assert research.public_question(store,original)==original


def test_research_view_and_database_connection_cannot_rewrite_private_extraction(store):
    q=question();store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',q['id'],json.dumps(q)));store.db.commit()
    readonly=research.ReadOnlyLibrary(store.root)
    try:
        with pytest.raises(sqlite3.OperationalError):readonly.db.execute("UPDATE library_records SET data='{}'")
        changed={**q,'answer':'Public proposal only.'};view=research.RevisionView(readonly,{q['id']:changed})
        try:
            assert json.loads(view.db.execute("SELECT data FROM library_records").fetchone()[0])['answer']=='Public proposal only.'
            assert json.loads(readonly.db.execute("SELECT data FROM library_records").fetchone()[0])['answer']=='Supported answer.'
        finally:view.close()
    finally:readonly.close()


def test_public_draft_changes_only_question_text_not_private_metadata(store,cfg):
    original=question();before=copy.deepcopy(original)
    def judge(messages,schema,cfg,path):
        return {'prompt':'Source-supported general principle?', 'answer':'Supported answer.',
                'explanation':'Supported explanation.'}
    candidate=research.draft(original,{'ref-test:0':{'text':'Supported answer.'}},cfg,store.root/'raw.json',judge)
    assert original==before
    for key in ['id','topics','sourceDiscussionIds','articleIds','origin','format']:
        assert candidate[key]==original[key]


def test_relevant_sources_check_original_before_proposing_any_rewrite(store,cfg,monkeypatch):
    from vet_pipeline import auto_publication as ap,patient_privacy as privacy,library
    original=question()
    store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',original['id'],json.dumps(original)));store.db.commit()
    source=library.current(store)
    write_json(store.root/'publication/patient-identities.json',{'complete':True,'version':privacy.VERSION,
        'inputSha256':privacy.identity_fingerprint(source,ap.prepared(source),ap.fields),'entities':[]})
    cfg['question_verification']['research_enabled']=True
    monkeypatch.setattr(research.web,'plan',lambda *a:[{'terms':['thoracentesis'],'species':'dog'}])
    monkeypatch.setattr(research.web,'search',lambda *a,**kw:[])
    monkeypatch.setattr(verify,'documents',lambda *a:[])
    checked=set();calls=[]
    monkeypatch.setattr(verify,'status',lambda store,q:{'status':'supported' if q['id'] in checked else 'pending'})
    def check(view,cfg,question_ids=None):
        calls.append(question_ids)
        if question_ids:checked.update(question_ids)
        return [{'id':original['id'],'status':'supported'}]
    monkeypatch.setattr(verify,'run_checks',check)
    def unnecessary(*args,**kwargs):raise AssertionError('A supported original must not be rewritten')
    monkeypatch.setattr(research,'draft',unnecessary)
    result=research.research(store,cfg)
    assert calls[0]==[original['id']] and result['status']=='checked'
    assert not research.revision_path(store,original).exists()
    assert library.current(store)['questions']==[original]


def test_case_question_alias_gets_its_own_exact_medical_proof_without_private_changes(store,cfg,monkeypatch):
    from vet_pipeline import auto_publication as ap,patient_privacy as privacy,library
    original={**question(),'prompt':'Why does PrivateDog need thoracentesis?'}
    store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',original['id'],json.dumps(original)));store.db.commit()
    source=library.current(store)
    write_json(store.root/'publication/patient-identities.json',{'complete':True,'version':privacy.VERSION,
        'inputSha256':privacy.identity_fingerprint(source,ap.prepared(source),ap.fields), 'caseNames':{},
        'entities':[{'name':'PrivateDog','kind':'patient','species':'dog','sex':'male'}]})
    cfg['question_verification']['research_enabled']=True
    monkeypatch.setattr(research.web,'plan',lambda *a:[{'terms':['thoracentesis'],'species':'dog'}])
    monkeypatch.setattr(research.web,'search',lambda *a,**kw:[])
    monkeypatch.setattr(verify,'documents',lambda *a:[])
    checked=set()
    monkeypatch.setattr(verify,'status',lambda store,q:{'status':'supported' if record_hash(q) in checked else 'pending'})
    def check(view,cfg,question_ids=None):
        candidate=library.current(view)['questions'][0]
        assert candidate['prompt']=='Why does Spot need thoracentesis?'
        checked.add(record_hash(candidate))
        return [{'id':candidate['id'],'status':'supported'}]
    monkeypatch.setattr(verify,'run_checks',check)
    def unnecessary(*a,**kw):raise AssertionError('Name-only changes need proof, not a medical rewrite')
    monkeypatch.setattr(research,'draft',unnecessary)
    result=research.research(store,cfg)
    public=research.public_question(store,original)
    assert public['prompt']=='Why does Spot need thoracentesis?' and result['publicProposals']==1
    assert library.current(store)['questions']==[original]


def test_verified_public_alias_does_not_cascade_when_another_private_pet_has_that_name(store,tmp_path):
    from vet_pipeline import patient_privacy as privacy,auto_publication as ap,library
    original={**question(),'prompt':'Why does PrivateDog need care?'}
    candidate,_=supported_revision(store,tmp_path,original,public_prompt='Why does Spot need care?')
    registry={'caseNames':{},'entities':[
        {'name':'PrivateDog','kind':'patient','species':'dog','sex':'male'},
        {'name':'Spot','kind':'patient','species':'dog','sex':'female'}]}
    source=library.empty_library();source['questions']=[original]
    enriched=privacy.with_public_questions(registry,store,source)
    public=library.empty_library();public['questions']=[candidate]
    assert privacy.anonymize(public,enriched,ap.fields)['questions'][0]==candidate
    # A private original named Spot must still follow its OWN female-dog mapping.
    private=library.empty_library();private['questions']=[{**original,'prompt':'Why does Spot need care?'}]
    assert privacy.anonymize(private,enriched,ap.fields)['questions'][0]['prompt']=='Why does Bella need care?'


def test_medically_supported_public_copy_still_cannot_exempt_a_private_person_name(store,tmp_path):
    from vet_pipeline import patient_privacy as privacy,auto_publication as ap,library
    original=question()
    candidate,_=supported_revision(store,tmp_path,original,public_prompt='What did PrivateClinician say?')
    registry={'caseNames':{},'entities':[{'name':'PrivateClinician','kind':'person','species':'unknown','sex':'unknown'}]}
    source=library.empty_library();source['questions']=[original]
    enriched=privacy.with_public_questions(registry,store,source)
    proposed=library.empty_library();proposed['questions']=[candidate]
    checked=privacy.anonymize(proposed,enriched,ap.fields)['questions'][0]
    assert checked['prompt']=='What did Person say?'
    assert record_hash(checked)!=record_hash(candidate)  # Exact medical proof must be redone; no exemption.
