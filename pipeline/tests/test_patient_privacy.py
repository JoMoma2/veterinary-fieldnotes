import copy
import pytest
from vet_pipeline.patient_privacy import label, compile_registry, anonymize, assert_anonymous, validate_entities, replace_names
from vet_pipeline.auto_publication import fields
from vet_pipeline.library import empty_library


@pytest.mark.parametrize('species,sex,expected', [
    ('dog','male','Spot'), ('dog','female','Bella'), ('cat','male','Pickles'),
    ('cat','female','Donut'), ('dog','unknown','Dog X'), ('cat','unknown','Cat X'),
    ('unknown','unknown','Patient X'), ('unknown','male','Patient X'), ('other','female','Patient X')])
def test_exact_owner_selected_labels(species, sex, expected):
    assert label({'kind':'patient','species':species,'sex':sex}) == expected


def registry():
    return {'caseNames': {'c-one':'ConfidentialDog', 'c-two':'ConfidentialCat'}, 'entities': [
        {'name':'ConfidentialDog','kind':'patient','species':'dog','sex':'male'},
        {'name':'ConfidentialCat','kind':'patient','species':'cat','sex':'female'}]}


def test_names_replaced_across_public_fields_without_merging_cases_or_touching_originals():
    lib = empty_library()
    lib['articles'] = [{'id':'a-care','title':'ConfidentialDog care','summary':'confidentialcat care',
                        'body':"ConfidentialDog’s source note; ConfidentialCat's note."}]
    lib['cases'] = [{'id':'c-one','title':'ConfidentialDog','summary':'Notes','species':'Unknown',
        'patientLabel':'ConfidentialDog','facts':[{'text':'ConfidentialDog is stable.'}],
        'uncertainties':['Outcome for ConfidentialDog unknown.'],'linkBasis':'ConfidentialDog'},
        {'id':'c-two','title':'ConfidentialCat','summary':'Notes','species':'Unknown',
        'patientLabel':'ConfidentialCat','facts':[{'text':'ConfidentialCat is stable.'}],
        'uncertainties':[],'linkBasis':'ConfidentialCat'}]
    before = copy.deepcopy(lib); public = anonymize(lib, registry(), fields)
    assert lib == before
    assert public['cases'][0]['patientLabel'] == 'Spot' and public['cases'][1]['patientLabel'] == 'Donut'
    assert [c['id'] for c in public['cases']] == ['c-one','c-two']
    assert public['articles'][0]['body'] == "Spot’s source note; Donut's note."
    assert_anonymous(public, registry(), fields)
    with pytest.raises(ValueError, match='identity'): assert_anonymous(lib, registry(), fields)


def test_reserved_real_names_follow_their_group_and_replacement_does_not_cascade():
    r = {'caseNames':{},'entities':[
        {'name':'Bella','kind':'patient','species':'dog','sex':'male'},
        {'name':'PrivateFemale','kind':'patient','species':'dog','sex':'female'}]}
    assert replace_names('Bella and PrivateFemale', r) == 'Spot and Bella'
    assert not replace_names('Spot and Bella', r, check_only=True)
    assert replace_names('Bella', r, check_only=True, allow_public_labels=False)
    r['entities'][0]['sex'] = 'female'
    assert replace_names('Bella', r) == 'Bella'


def test_medical_blood_sugar_is_preserved_while_the_same_word_as_a_name_is_replaced():
    r={'entities':[{'name':'Sugar','kind':'patient','species':'cat','sex':'unknown'}]}
    assert replace_names('Sugar had a blood sugar check.', r) == 'Cat X had a blood sugar check.'
    assert not replace_names('Blood sugar is measured.', r, check_only=True)


def test_identity_quotes_are_exact_and_conflicting_traits_remain_unknown():
    records=[{'id':'c-one','fields':{'summary':'PrivateName is a cat.'}}]
    entity={'name':'PrivateName','kind':'patient','species':'cat','sex':'male',
            'evidence':[{'record':'c-one','field':'summary','quote':'PrivateName is a cat.'}]}
    validate_entities({'entities':[entity]},records)
    bad=copy.deepcopy(entity);bad['evidence'][0]['quote']='Invented name evidence'
    with pytest.raises(ValueError):validate_entities({'entities':[bad]},records)
    conflicting=copy.deepcopy(entity);conflicting['sex']='female'
    result=compile_registry([{'id':'c-one','patientLabel':'PrivateName'}],
        [{'entities':[entity,conflicting,entity]}])
    assert label(result['entities'][0]) == 'Cat X'


def test_same_named_cases_keep_their_own_sex_and_never_merge():
    cases=[{'id':'c-first','patientLabel':'SharedPrivateName'}, {'id':'c-second','patientLabel':'SharedPrivateName'}]
    entities=[{'name':'SharedPrivateName','kind':'patient','species':'dog','sex':sex,
        'evidence':[{'record':rid,'field':'title','quote':'SharedPrivateName'}]}
        for rid,sex in [('c-first','male'),('c-second','female')]]
    r=compile_registry(cases,[{'entities':entities}]);lib=empty_library()
    lib['cases']=[{**c,'title':'SharedPrivateName care','summary':'Notes','species':'dog',
        'facts':[],'uncertainties':[],'linkBasis':'Source evidence'} for c in cases]
    result=anonymize(lib,r,fields)
    assert [c['patientLabel'] for c in result['cases']]==['Spot','Bella']
    assert [c['id'] for c in result['cases']]==['c-first','c-second']


def test_named_medical_conditions_are_preserved():
    r={'entities':[{'name':'Rocky','kind':'patient','species':'cat','sex':'female'}]}
    assert replace_names('Rocky was tested for Rocky Mountain spotted fever.',r)=='Donut was tested for Rocky Mountain spotted fever.'


def test_identity_grounding_does_not_invent_sex_or_species_for_a_name():
    from vet_pipeline.patient_privacy import ground_identity_spans
    records=[{'id':'d-one','fields':{'account':'PrivateName was present.'}}]
    raw={'entities':[{'name':'PrivateName','kind':'patient','species':'dog','sex':'male',
        'evidence':[{'record':'d-one','field':'account','quote':'PrivateName was present.'}]}]}
    result,_=ground_identity_spans(raw,records)
    assert result['entities'][0]['sex']=='unknown' and result['entities'][0]['species']=='unknown'


def test_person_matching_animal_alias_stays_private_and_only_generated_animal_alias_is_allowed():
    from vet_pipeline.auto_publication import apply_decision
    r={'caseNames':{},'entities':[
        {'name':'Bella','kind':'person','species':'unknown','sex':'unknown'},
        {'name':'PrivateFemaleDog','kind':'patient','species':'dog','sex':'female'}]}
    lib=empty_library();lib['articles']=[{'id':'a-one','title':'Care','summary':'Notes','body':'Bella treated PrivateFemaleDog.'}]
    proof={};public=anonymize(lib,r,fields,proof)
    assert public['articles'][0]['body']=='Person treated Bella.'
    assert_anonymous(public,r,fields,proof)
    with pytest.raises(ValueError):assert_anonymous(public,r,fields)
    public['articles'][0]=apply_decision(public['articles'][0],'articles',
        {'safe':True,'redactions':[{'field':'body','text':'Person treated '}]},proof)
    assert_anonymous(public,r,fields,proof)
    public['articles'][0]['body']='Bella '+public['articles'][0]['body']
    with pytest.raises(ValueError):assert_anonymous(public,r,fields,proof)


def test_identity_registry_checks_questions_and_reuses_only_unchanged_record_reviews(store,cfg):
    from vet_pipeline.patient_privacy import ensure_registry
    source=empty_library()
    source['questions']=[{'id':'q-private','prompt':'A generic principle?','answer':'An answer.','explanation':'Evidence.'}]
    calls=[]
    def judge(messages,schema,cfg,path):
        import json
        records=json.loads(messages[-1]['content'])['records']
        calls.append([r['id'] for r in records])
        return {'entities':[]}
    first=ensure_registry(store,source,source,cfg,fields,judge)
    assert first['complete'] and calls==[['q-private']]
    ensure_registry(store,source,source,cfg,fields,judge)
    assert len(calls)==1
    source['articles']=[{'id':'a-new','title':'General education','summary':'Notes','body':'No private names.'}]
    second=ensure_registry(store,source,source,cfg,fields,judge)
    assert first['inputSha256']!=second['inputSha256']
    assert calls==[['q-private'],['a-new']]


@pytest.mark.parametrize('species,expected',[('Dog','Dog X'),('Cat','Cat X'),('Unknown','Patient X')])
def test_unnamed_case_with_known_species_uses_exact_species_fallback(species,expected):
    lib=empty_library();lib['cases']=[{'id':'c-unnamed','title':'Unnamed case','summary':'Notes',
        'species':species,'patientLabel':'Unknown','facts':[],'uncertainties':[],'linkBasis':'Source evidence'}]
    registry={'caseNames':{'c-unnamed':'Unknown'},'entities':[]}
    assert anonymize(lib,registry,fields)['cases'][0]['patientLabel']==expected
