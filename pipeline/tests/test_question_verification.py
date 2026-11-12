from pathlib import Path
import hashlib,json
import pytest
from vet_pipeline.question_verification import materials,validate_result,status,run_checks,safe_url,VERSION
from vet_pipeline.util import write_json,load_json,now
from vet_pipeline.library import current
from vet_pipeline.publication import record_hash,review_template,export


def question():
    return {'schemaVersion':1,'id':'q-test','origin':'authorized-record','publication':{'status':'draft','audience':'private'},'format':'flashcard','topics':['test'],'prompt':'What is the general principle?','answer':'Supported answer.','explanation':'Supported explanation.','articleIds':[],'sourceDiscussionIds':[]}


def refs():
    return {'ref-test:0':{'text':'Supported answer. Supported explanation. Clear question premises.','url':'https://www.fda.gov/test','title':'Synthetic reference fixture','scope':'Synthetic test only','documentId':'ref-test','bodySha256':'placeholder','fetchedAt':now()}}


def verdict(q,reference,status='supported'):
    return {'components':[{'id':key,'verdict':status,'reason':'Synthetic test only.','evidence':[{'source':next(iter(reference)),'quote':'Supported answer.'}]} for key in materials(q)],'suggested_revision':''}


def test_all_components_and_exact_independent_evidence_are_required():
    q=question();r=refs();data=verdict(q,r)
    assert validate_result(data,q,r)['status']=='supported'
    data['components'].pop()
    with pytest.raises(ValueError,match='every'):validate_result(data,q,r)
    data=verdict(q,r);data['components'][1]['evidence'][0]['quote']='Invented evidence'
    with pytest.raises(ValueError,match='quotation'):validate_result(data,q,r)
    data=verdict(q,r);data['components'][1]['evidence']=[]
    with pytest.raises(ValueError,match='no independent'):validate_result(data,q,r)
    data=verdict(q,r);data['components'][1].update(verdict='contradicted',evidence=[])
    with pytest.raises(ValueError):validate_result(data,q,r)


def test_uncertainty_never_becomes_verified_and_all_distractors_are_checked():
    q=question();q.pop('answer');q.update(format='multiple-choice',correct={'id':'correct','text':'Supported answer.'},distractors=[{'id':'wrong','text':'Different answer.'}])
    m=materials(q);assert 'correct' in m and m['option:wrong']['role']=='incorrect-distractor'
    data=verdict(q,refs());data['components'][-1]['verdict']='ambiguous'
    assert validate_result(data,q,refs())['status']=='ambiguous'


def test_missing_references_hold_candidates_without_calling_a_model(store,cfg):
    q=question();store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',q['id'],json.dumps(q)));store.db.commit()
    result=run_checks(store,cfg,judge=lambda *a:pytest.fail('Must not ask model without independent sources'))
    assert result[0]['status']=='pending' and status(store,q)['status']=='pending'
    assert (store.root/'review/question-verification.html').exists()


def test_reference_and_candidate_changes_invalidate_saved_checks(store,cfg,tmp_path):
    directory=tmp_path/'references';directory.mkdir();q=question();r=refs()['ref-test:0'];body=r['text']
    doc={'id':'ref-test','url':r['url'],'title':r['title'],'scope':r['scope'],'body':body,'bodySha256':hashlib.sha256(body.encode()).hexdigest(),'fetchedAt':now()}
    write_json(directory/'ref-test.json',doc);cfg['question_verification']['references_dir']=str(directory)
    store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',q['id'],json.dumps(q)));store.db.commit()
    def judge(q,reference,c):return verdict(q,reference),{'modelDigest':'synthetic-test'}
    assert run_checks(store,cfg,judge=judge)[0]['status']=='supported'
    assert status(store,q)['status']=='supported'
    assert status(store,{**q,'answer':'Changed answer'})['status']=='pending'
    doc['body']='Different reference text';doc['bodySha256']=hashlib.sha256(doc['body'].encode()).hexdigest();write_json(directory/'ref-test.json',doc)
    assert status(store,q)['status']=='pending'


@pytest.mark.parametrize('url',['http://www.fda.gov/test','https://localhost/test','https://www.fda.gov.evil.example/test','https://user:password@www.fda.gov/test','file:///private/clinical.json'])
def test_untrusted_private_or_non_https_references_are_refused(url):
    with pytest.raises(ValueError):safe_url(url)


def test_even_owner_approved_real_questions_need_independent_verification(store,cfg,first,tmp_path):
    from vet_pipeline.runner import run
    from vet_pipeline.publication import approve_synthetic
    run(store,cfg);approve_synthetic(store,tmp_path/'approval.json')
    lib=current(store);q=lib['questions'][0];q['origin']='authorized-record'
    store.db.execute('UPDATE library_records SET data=? WHERE kind=? AND id=?',(json.dumps(q),'questions',q['id']));store.db.commit()
    review=load_json(tmp_path/'approval.json')
    for entry in review['entries']:
        if entry['kind']=='questions' and entry['id']==q['id']:entry['sha256']=record_hash(q)
    write_json(tmp_path/'approval.json',review)
    with pytest.raises(ValueError,match='independent external'):export(store,tmp_path/'approval.json',tmp_path/'public',allow_clinical=True)
    assert not (tmp_path/'public').exists()


def test_public_reference_fetch_never_follows_a_redirect_to_a_private_host(tmp_path,monkeypatch):
    import httpx
    from vet_pipeline import question_verification as v
    original=httpx.Client;requests=[]
    def response(request):
        requests.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://localhost/private-clinical-data'})
    monkeypatch.setattr(v.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(response),**kw))
    with pytest.raises(ValueError):v.import_url('https://www.fda.gov/test','Synthetic title','Synthetic test',tmp_path/'refs')
    assert requests==['https://www.fda.gov/test']
    assert not list((tmp_path/'refs').glob('ref-*.json'))


def test_malformed_judge_response_is_bounded_and_keeps_question_held(store,cfg,tmp_path):
    directory=tmp_path/'refs';directory.mkdir();q=question();body='Supported answer. Supported explanation. Clear question premises.'
    write_json(directory/'ref-test.json',{'id':'ref-test','url':'https://www.fda.gov/test','title':'Synthetic reference','scope':'Synthetic test','body':body,'bodySha256':hashlib.sha256(body.encode()).hexdigest(),'fetchedAt':now()})
    cfg['question_verification']['references_dir']=str(directory)
    store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',q['id'],json.dumps(q)));store.db.commit()
    calls=[]
    def bad(*args):calls.append(1);return {'components':[],'suggested_revision':''},{}
    run_checks(store,cfg,judge=bad);run_checks(store,cfg,judge=bad)
    assert len(calls)==cfg['question_verification']['max_attempts'] and status(store,q)['status']=='pending'


def test_retrieval_preserves_rare_comparison_term_and_source_diversity():
    from vet_pipeline.question_verification import retrieve
    q=question();q.update(prompt='Compare buprenorphine with methadone.',answer='Pain control and sedation.',explanation='Pain control and sedation.')
    generic={'id':'ref-general','body':'\n'.join(['Pain control sedation buprenorphine.']*20),'url':'https://www.fda.gov/general','title':'Synthetic generic reference','scope':'test','bodySha256':'a','fetchedAt':now()}
    specific={'id':'ref-comparison','body':'Methadone is the named comparison.\nIts specific context must be retained.','url':'https://www.aaha.org/test','title':'Synthetic comparison reference','scope':'test','bodySha256':'b','fetchedAt':now()}
    result=retrieve(q,[generic,specific],limit=3)
    assert any(x['documentId']=='ref-comparison' for x in result.values())
    assert sum(x['documentId']=='ref-general' for x in result.values())<=2


def test_a_reference_about_a_different_comparator_cannot_verify_the_answer():
    q=question();q['answer']='Synthetic agonist alpha is stronger than synthetic-beta.'
    data=verdict(q,refs())
    with pytest.raises(ValueError,match='comparator absent'):validate_result(data,q,refs())


def test_output_exhaustion_is_not_retried_identically(store,cfg,tmp_path):
    from vet_pipeline.question_verification import VerificationOutputLimit
    directory=tmp_path/'refs';directory.mkdir();q=question();body='Supported answer. Supported explanation. General principle.'
    write_json(directory/'ref-test.json',{'id':'ref-test','url':'https://www.fda.gov/test','title':'Synthetic reference','scope':'Synthetic test','body':body,'bodySha256':hashlib.sha256(body.encode()).hexdigest(),'fetchedAt':now()})
    cfg['question_verification']['references_dir']=str(directory)
    store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',q['id'],json.dumps(q)));store.db.commit()
    calls=[]
    def exhausted(*args):calls.append(1);raise VerificationOutputLimit()
    run_checks(store,cfg,judge=exhausted);run_checks(store,cfg,judge=exhausted)
    assert len(calls)==1 and status(store,q)['status']=='pending'
    cfg['question_verification']['max_output_tokens']+=1024
    run_checks(store,cfg,judge=exhausted)
    assert len(calls)==2


def test_document_citation_resolves_only_to_supplied_excerpt_with_an_exact_quote():
    import copy
    q=question();r=refs();data=verdict(q,r)
    for part in data['components']:part['evidence'][0]['source']='ref-test'
    original=copy.deepcopy(data);result=validate_result(data,q,r)
    assert result['status']=='supported' and data==original
    assert all(p['evidence'][0]['source']=='ref-test:0' for p in result['components'])
    assert len(result['citationNormalizations'])==len(data['components'])
    for bad_source,bad_quote in [('ref-unprovided','Supported answer.'),('ref-test:999','Supported answer.'),('ref-test','Invented evidence')]:
        invalid=copy.deepcopy(data);invalid['components'][0]['evidence'][0].update(source=bad_source,quote=bad_quote)
        with pytest.raises(ValueError,match='quotation'):validate_result(invalid,q,r)


def test_model_citation_grammar_allows_only_exact_supplied_excerpt_ids():
    from vet_pipeline.question_verification import verification_schema
    schema=verification_schema(refs())
    source=schema['properties']['components']['items']['properties']['evidence']['items']['properties']['source']
    assert source['enum']==['ref-test:0']


def test_unrelated_new_paper_keeps_exact_proof_but_changed_selected_context_requires_recheck(store,cfg,tmp_path):
    directory=tmp_path/'refs';directory.mkdir();q=question()
    def paper(id,body):
        write_json(directory/(id+'.json'),{'id':id,'url':'https://www.fda.gov/'+id,'title':'Synthetic reference',
            'scope':'Synthetic test','body':body,'bodySha256':hashlib.sha256(body.encode()).hexdigest(),'fetchedAt':now()})
    paper('ref-test','Supported answer. Supported explanation. General principle.')
    cfg['question_verification']['references_dir']=str(directory)
    store.db.execute('INSERT INTO library_records VALUES(?,?,?)',('questions',q['id'],json.dumps(q)));store.db.commit()
    calls=[]
    def judge(q,reference,c):calls.append(1);return verdict(q,reference),{'modelDigest':'synthetic-test'}
    run_checks(store,cfg,judge=judge)
    paper('ref-unrelated','Granite basalt feldspar rhyolite.')
    assert status(store,q)['status']=='supported'
    run_checks(store,cfg,judge=judge);assert calls==[1]
    paper('ref-new-evidence','General principle. Supported answer. Supported explanation. Additional evidence.')
    assert status(store,q)['status']=='pending'
