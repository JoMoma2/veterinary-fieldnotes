import json
import httpx
import pytest
from vet_pipeline import public_research as web
from vet_pipeline.patient_privacy import compile_registry


def registry():
    return {'entities':[{'name':'PrivatePatient','kind':'patient','species':'dog','sex':'male'},
                        {'name':'Bella','kind':'patient','species':'dog','sex':'female'}]}


@pytest.mark.parametrize('term',['PrivatePatient','Bella','case owner','https://private.example',
                                  'recording transcript','2026-11-12','patient age seven','Clinic'])
def test_identifiers_case_context_and_urls_never_leave_in_searches(term):
    with pytest.raises(ValueError):web.validate_query({'terms':[term],'species':'dog'},registry())


def test_search_uses_only_generic_concepts_and_species_in_fixed_public_endpoint(monkeypatch):
    original=httpx.Client;seen=[]
    def respond(request):
        seen.append(request)
        return httpx.Response(200,json={'resultList':{'result':[
            {'id':'123','source':'MED','title':'Public canine study','isRetracted':'N'},
            {'id':'456','source':'MED','title':'Retracted','isRetracted':'Y'}]}})
    monkeypatch.setattr(web.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    result=web.search({'terms':['albuterol toxicity'],'species':'dog'},registry())
    assert len(result)==1 and result[0]['id']=='123'
    assert str(seen[0].url).startswith(web.API+'/search?')
    query=seen[0].url.params['query'];assert 'TITLE_ABS:"albuterol toxicity"' in query and 'TITLE_ABS:(dog' in query
    assert 'PrivatePatient' not in str(seen[0].url) and 'Bella' not in str(seen[0].url)


def test_medical_receptor_numbers_allowed_but_private_measurements_blocked():
    assert 'beta-2' in web.validate_query({'terms':['beta-2 agonist toxicity'],'species':'dog'},registry())
    with pytest.raises(ValueError):web.validate_query({'terms':['weight 23 kg'],'species':'dog'},registry())


def test_article_reader_preserves_real_source_text_and_never_follows_arbitrary_links(tmp_path,monkeypatch):
    original=httpx.Client;seen=[]
    body='The public veterinary study establishes a general medical principle. '*4
    def respond(request):
        seen.append(str(request.url));return httpx.Response(200,text='<article><body><p>'+body+'</p></body></article>')
    monkeypatch.setattr(web.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    doc=web.import_article({'id':'123','source':'MED','pmcid':'PMC123','title':'Public test article',
                            'abstractText':'Abstract only.'},tmp_path)
    assert 'general medical principle' in doc['body'] and doc['researchImport']
    assert seen==[web.API+'/PMC123/fullTextXML']
    with pytest.raises(ValueError):web.import_article({'id':'../../private','source':'MED'},tmp_path)


def test_empty_phrase_search_broadens_only_checked_generic_words(monkeypatch):
    original=httpx.Client;seen=[]
    def respond(request):
        seen.append(request.url.params['query'])
        return httpx.Response(200,json={'resultList':{'result':[] if len(seen)==1 else [
            {'id':'123','source':'MED','title':'Relevant public study'}]}})
    monkeypatch.setattr(web.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    result=web.search({'terms':['albuterol salbutamol','toxicity signs'],'species':'dog'},registry())
    assert result and len(seen)==2
    assert '"albuterol" OR "salbutamol"' in seen[1] and 'TITLE_ABS:(dog' in seen[1]
    assert 'PrivatePatient' not in seen[1] and 'Bella' not in seen[1]
