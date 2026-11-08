"""Normal nightly whole-shift extraction with transactional draft-library saving.

One extraction model; existing call/source validation and recoverable checkpoints.
No publication or clinical-cloud permission is granted by selecting this mode.
"""
from __future__ import annotations
import copy, hashlib, json, re, time
from jsonschema import ValidationError
from datetime import datetime, timezone
from . import shift_context as sc
from .private import private_path
from .util import load_json, write_json, digest_file, lock, now
from .library import current, metadata, fact, unique_add, validate_library, materialize
from .grounded import slug
from .study_policy import MEDICAL_QUESTION_RULES, question_rejection

INDEX_RULES = '''Coverage matters: preserve each clinically or practically meaningful thread, including incomplete/contradictory cases and equipment/technique discussions. Do not compress unrelated patients into a few broad episodes. Do not turn greetings or incidental chatter into teaching. Source coverage is audited separately; omitted text remains in the private archive, never silently discarded.'''
TOPIC_SCHEMA = sc.obj({'key': sc.TEXT, 'title': sc.TEXT, 'summary': sc.TEXT, 'account': sc.TEXT,
                       'evidence': {'type':'array','items':sc.EVIDENCE,'minItems':1}})


def detail_contract(root, task):
    schema = copy.deepcopy(sc.DETAIL_SCHEMA)
    schema['properties']['knowledge_topics'] = {'type':'array','items':TOPIC_SCHEMA}
    schema['required'].append('knowledge_topics')
    topic_index = load_json(root / 'topic-index.json')
    task += '\n' + MEDICAL_QUESTION_RULES + '\n' + sc.SPEAKER_ID_UNCERTAINTY
    task += '\nFor knowledge_topics, extract reusable medical/equipment/practical subjects actually taught. Titles/keys describe the subject, never a patient name/date. A case-only history can have zero topics; retain its details in facts. Reuse an existing key for the SAME topic. Write a detailed source-supported account preserving uncertainties and limitations; no external facts or recommendations. Supply exact evidence for every account. Existing bounded naming index (not clinical evidence):\n' + json.dumps(topic_index, ensure_ascii=False)
    return task, schema


def validate_topics(topics, sources, patient_labels=()):
    accepted=[];rejected=[]
    for original in topics:
        item=copy.deepcopy(original)
        try:
            sc.Draft202012Validator(TOPIC_SCHEMA).validate(item)
            if not item['key'].strip() or not item['title'].strip() or not item['account'].strip():raise ValueError('Empty topic')
            if any(n and re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',item['title'],re.I) for n in patient_labels):raise ValueError('Patient-name topic')
            sc.repair_evidence(item['evidence'], sources)
        except (ValueError, ValidationError):
            rejected.append({'section':'knowledge_topics','reason':'Unsupported or case-specific topic','item':original})
        else: accepted.append(item)
    return accepted,rejected


def persist(store, root, cfg):
    """Save each accepted episode independently; replay never appends twice."""
    root=private_path(root);exp=load_json(root/'experiment.json');sources=load_json(root/'sources.json')
    index=load_json(root/'index-map.json') if (root/'index-map.json').exists() else {'episodes':[]}
    jobs=[dict(j) for j in store.jobs() if j['shift_id']==exp['shiftId']];by_id={j['id']:j for j in jobs}
    if not jobs:return
    origin=jobs[0]['origin'];shift_id=exp['shiftId'];date=jobs[0]['shift_date'];lib=current(store)
    store.db.execute('CREATE TABLE IF NOT EXISTS shift_episode_commits (id TEXT PRIMARY KEY)');store.db.commit()
    saved={r[0] for r in store.db.execute('SELECT id FROM shift_episode_commits')}
    topic=lambda key,title: {'id':key,'name':title,'description':'Source-extracted; private pending review.','color':'green'}
    def add_topic(key,title):
        if not any(t['id']==key for t in lib['topics']):lib['topics'].append(topic(key,title))
    def write_records(marker):
        validate_library(lib)
        with store.db:
            for group, entries in lib.items():
                for entry in entries:store.db.execute('INSERT INTO library_records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',(group,entry['id'],json.dumps(entry,ensure_ascii=False,sort_keys=True)))
            store.db.execute('INSERT INTO shift_episode_commits VALUES(?)',(marker,))
    shift=next((x for x in lib['shifts'] if x['id']==shift_id),None)
    if shift is None:
        shift={**metadata(shift_id,origin),'title':'Learning archive · '+date,'date':date,'summary':'Whole-shift source-linked extraction. Private, unreviewed.','topics':[], 'timezone':cfg['archive']['timezone'],'recordings':[],'processing':'partial'};lib['shifts'].append(shift)
    for job in jobs:
        if any(x['id']==job['id'] for x in shift['recordings']):continue
        from .audio_prepare import duration_seconds
        p=store.root/'transcripts'/(job['id']+'.json')
        duration=duration_seconds(store.root/'inputs'/(job['id']+'.wav')) if job['source_kind']=='audio' else max(s['end'] for s in load_json(p)['segments'])
        # Retained normalized resampling may add a sample to the original length.
        if p.exists():duration=max(duration,max(s['end'] for s in load_json(p)['segments']))
        shift['recordings'].append({'id':job['id'],'sequence':job['sequence'],'durationSeconds':duration,'fileModifiedAt':datetime.fromtimestamp(job['source_mtime'],timezone.utc).isoformat(),'sourceSha256':job['sha256'],'capturedAt':None,'clockConfidence':'unknown'})
    def segments(keys):
        return [{'recordingId':sources[k]['recordingId'],'startSeconds':sources[k]['start'],'endSeconds':sources[k]['end'],'clockTime':None,'clockConfidence':'unknown'} for k in dict.fromkeys(keys)]
    used=set();labels=[e['patient_label'] for e in index['episodes'] if e['patient_label']]
    for number,episode in enumerate(index['episodes'],1):
        path=root/'calls'/f'episode-{number:03d}.json'
        if not path.exists():continue
        data=load_json(path)['data'];keys=list(dict.fromkeys(episode['sources']+[ref['source'] for x in data['facts']+data['practical_lessons'] for ref in x['evidence']]))
        keys=[k for k in keys if k in sources and sources[k]['eligible']];used.update(keys)
        if not keys:continue
        marker=hashlib.sha256(json.dumps([exp['sourcesSha256'],number,data],sort_keys=True).encode()).hexdigest()
        if marker in saved:continue
        did='d-'+hashlib.sha256((shift_id+exp['sourcesSha256']+str(number)).encode()).hexdigest()[:24]
        plans=data.get('knowledge_topics',[]);tids=list(dict.fromkeys(slug(t['key']) for t in plans)) or ['clinical-discussions']
        for t in plans:add_topic(slug(t['key']),t['title'])
        if not plans:add_topic('clinical-discussions','Clinical discussions')
        mapped={'owner-report':'owner-report','observation':'direct-observation','suspicion':'clinical-suspicion','confirmed-diagnosis':'confirmed-diagnosis','actual-treatment':'actual-treatment','proposed-treatment':'proposed-treatment','outcome':'outcome','unknown':'unknown'}
        facts=[fact(mapped.get(f['kind'],'direct-observation'), ('['+f['kind']+'] ' if f['kind'] not in mapped else '')+f['text'],[did]) for f in data['facts']]
        account=data['summary']+'\n\n'+ '\n'.join('['+f['kind']+'] '+f['text'] for f in data['facts'])
        account+='\n\n'+'\n'.join(x['text']+' Limitations: '+x['limitations'] for x in data['practical_lessons'])
        account+='\n\nUncertainties: '+'; '.join(data['uncertainties'])+'\n\nRecorded source wording:\n'+'\n\n'.join(sources[k]['text'] for k in keys)
        discussion={**metadata(did,origin),'shiftId':shift_id,'order':min(by_id[sources[k]['recordingId']]['sequence']*100000+list(sources).index(k) for k in keys),'title':data['title'] or episode['title'],'topics':tids,'segments':segments(keys),'account':account,'facts':facts,'questions':[],'conclusions':data['association_note'],'articleIds':[],'caseIds':[]}
        lib['discussions'].append(discussion);shift['topics']=unique_add(shift['topics'],tids)
        for plan in plans:
            aid='a-'+slug(plan['key']);article=next((a for a in lib['articles'] if a['id']==aid),None)
            if article is None:
                article={**metadata(aid,origin),'title':plan['title'],'summary':plan['summary'] or plan['title'],'topics':[],'updated':date,'sourceDiscussionIds':[],'relatedArticleIds':[],'body':'','educationalStatus':'synthetic-demonstration' if origin=='synthetic' else 'unreviewed-extraction'};lib['articles'].append(article)
            article['body']+='\n\n## Source addition · '+date+'\n\n'+plan['account'];article['sourceDiscussionIds']=unique_add(article['sourceDiscussionIds'],[did]);article['topics']=unique_add(article['topics'],tids);article['updated']=max(article['updated'],date);article['publication']={'status':'draft','audience':'private'}
            discussion['articleIds']=unique_add(discussion['articleIds'],[aid])
        if episode['patient_label'] and episode['association']=='explicit' and episode['identity_evidence'] and facts:
            cid='c-'+hashlib.sha256((did+episode['patient_label']).encode()).hexdigest()[:24]
            lib['cases'].append({**metadata(cid,origin),'title':episode['title'],'summary':data['summary'],'topics':tids,'species':'Unknown','patientLabel':episode['patient_label'],'diagnosis':None,'outcome':None,'sourceDiscussionIds':[did],'facts':facts,'linkBasis':episode['association_reason'],'uncertainties':data['uncertainties']+['AI-proposed association; formal species/diagnosis/outcome fields await review of cited findings.']});discussion['caseIds']=[cid]
        for q in data['study_questions']:
            if question_rejection(q,labels):continue
            qid='q-'+hashlib.sha256((did+q['prompt']).encode()).hexdigest()[:24]
            if any(x['id']==qid for x in lib['questions']):continue
            lib['questions'].append({**metadata(qid,origin),'format':'flashcard','prompt':q['prompt'],'answer':q['answer'],'explanation':q['explanation'] or 'Source-grounded educational draft; review required.','topics':tids,'articleIds':discussion['articleIds'],'sourceDiscussionIds':[did]})
        write_records(marker);saved.add(marker)
    # All omitted source blocks remain independently addressable in the shift archive.
    for key,block in sources.items():
        if key in used:
            old_id='d-'+hashlib.sha256((shift_id+exp['sourcesSha256']+key).encode()).hexdigest()[:24]
            prior=next((d for d in lib['discussions'] if d['id']==old_id),None)
            if prior:
                add_topic('source-archive','Retained source archive');prior['topics']=['source-archive'];prior['title']='Retained source excerpt';shift['topics']=unique_add(shift['topics'],['source-archive'])
            continue
        did='d-'+hashlib.sha256((shift_id+exp['sourcesSha256']+key).encode()).hexdigest()[:24]
        if any(d['id']==did for d in lib['discussions']):continue
        add_topic('unclassified-source','Unclassified source');shift['topics']=unique_add(shift['topics'],['unclassified-source'])
        lib['discussions'].append({**metadata(did,origin),'shiftId':shift_id,'order':by_id[block['recordingId']]['sequence']*100000+list(sources).index(key),'title':'Unclassified source excerpt'+(' — ASR review required' if not block['eligible'] else ''),'topics':['unclassified-source'],'segments':segments([key]),'account':block['text'],'facts':[],'questions':[],'conclusions':'Source retained without inferred interpretation.','articleIds':[],'caseIds':[]})
    # Update unclassified visibility as new episodes finish, preserving their source IDs.
    # Do not delete prior archive entries: stable source anchors remain available.
    shift['processing']='complete' if exp['status']=='complete' and all(j['stage']!='review' for j in jobs) else 'partial'
    validate_library(lib)
    with store.db:
        for group,entries in lib.items():
            for entry in entries:store.db.execute('INSERT INTO library_records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',(group,entry['id'],json.dumps(entry,ensure_ascii=False,sort_keys=True)))
        if exp['status']=='complete':
            for job in jobs:
                if job['stage']!='review' and (root/'transcripts'/(job['id']+'.json')).exists():
                    store.db.execute('INSERT OR IGNORE INTO applied_recordings VALUES(?)',(job['id'],));store.db.execute("UPDATE jobs SET stage='done',completed_at=?,error=NULL WHERE id=?",(now(),job['id']))
    materialize(store)
    review_file=root/'review/shift-context.html'
    if review_file.exists():
        from .util import atomic_write
        content=review_file.read_text()
        content=content.replace('</h1>','</h1><p><a href="question-verification.html">Independent medical verification of study candidates</a></p>',1)
        for job in jobs:
            for folder in ['filtered','normalized','inputs']:
                if (store.root/folder/(job['id']+'.wav')).exists():
                    content=content.replace('../inputs/'+job['id']+'.wav','../'+folder+'/'+job['id']+'.wav');break
        atomic_write(store.root/'review/whole-shift.html',content)
    from .publication import review_template
    review_template(store,store.root/'review/publication-candidates.json')
    from .morning import report
    report(store,cfg,load_json(store.root/'unattended/state.json') if (store.root/'unattended/state.json').exists() else {})
    write_json(root/'coverage.json',{'sourceBlocks':len(sources),'classifiedSourceBlocks':len(used),'unclassifiedSourceBlocks':len(sources)-len(used),'note':'Coverage of source blocks, not semantic completeness/accuracy. ASR-warning material remains private review-only.'})


def run(store,cfg,force_retry=False,before_stage=None):
    from .runner import run as recording_run, ProcessingDeferred
    results=recording_run(store,cfg,force_retry,before_stage,transcribe_only=True)
    settings=cfg['shift_context']
    with lock(store.root):
        for sid in dict.fromkeys(j['shift_id'] for j in store.jobs() if j['stage']=='extract'):
            jobs=[dict(j) for j in store.jobs() if j['shift_id']==sid]
            fingerprint=hashlib.sha256(json.dumps([(j['id'],digest_file(store.root/'transcripts'/(j['id']+'.json')) if (store.root/'transcripts'/(j['id']+'.json')).exists() else None) for j in jobs]).encode()).hexdigest()[:16]
            root=store.root/'shift-extraction'/fingerprint
            try:
                if not (root/'experiment.json').exists():
                    if root.exists():
                        root.rename(root.with_name(root.name+'.incomplete-'+str(time.time_ns())))
                    from .recorder_setup import save_config
                    profile=store.root/'shift-profiles'/(fingerprint+'.toml');save_config(profile,cfg)
                    sc.prepare(store.root,sid,root,profile)
                    exp=load_json(root/'experiment.json');exp.update(libraryWorkflow=True,medicalOnlyQuestions=True,speakerIdentityPolicy='uncertain-v2',repetitionExclusionThreshold=5,gpuLayers=settings['gpu_layers'])
                    exp['provider'].update(context_window=settings['context_window'],max_output_tokens=settings['max_output_tokens'],timeout_seconds=settings['timeout_seconds'])
                    write_json(root/'experiment.json',exp)
                    write_json(root/'topic-index.json',([{'key':a['id'].removeprefix('a-'),'title':a['title']} for a in current(store)['articles']]+(load_json(store.root/'topic-seed.json') if (store.root/'topic-seed.json').exists() else []))[:200])
                sc.run(root,on_checkpoint=lambda p:persist(store,p,cfg));persist(store,root,cfg)
                results.append({'shift':sid,'status':'done' if load_json(root/'experiment.json')['status']=='complete' else 'partial','stage':'whole-shift','report':str(root/'review/shift-context.html')})
            except ProcessingDeferred as e:
                results.append({'shift':sid,'status':'deferred','reason':str(e)});break
            except Exception as e:
                # Detailed call checkpoints and bounded attempt ledger remain available.
                results.append({'shift':sid,'status':'failed','error':type(e).__name__,'report':str(root/'review/shift-context.html')})
    return results
