from __future__ import annotations
import copy, hashlib, json, os, re, shutil, uuid
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from .util import REPO,atomic_write,load_json,write_json,now

GROUPS={'topics':'topic','articles':'article','cases':'case','shifts':'shift','discussions':'discussion','questions':'question'}
def empty_library():return {k:[] for k in GROUPS}
def read_library(root:Path):
    if not root.exists():return empty_library()
    lib=empty_library();lib['topics']=load_json(root/'topics.json')
    for group in GROUPS:
        if group=='topics':continue
        for file in sorted((root/group).glob('*.md' if group=='articles' else '*.json')):
            if group=='articles':
                raw=file.read_text();_,meta,body=raw.split('---',2);lib[group].append({**yaml.safe_load(meta),'body':body.strip()})
            else:lib[group].append(load_json(file))
    return lib

def validate_library(lib):
    for group,name in GROUPS.items():
        schema=load_json(REPO/'schemas'/f'{name}.schema.json');validator=Draft202012Validator(schema,format_checker=FormatChecker())
        known=set()
        for entry in lib[group]:
            validator.validate(entry)
            if entry['id'] in known:raise ValueError('Duplicate permanent ID')
            known.add(entry['id'])
    sets={k:{x['id'] for x in v} for k,v in lib.items()}
    def refs(values,group):
        if not set(values)<=sets[group]:raise ValueError(f'Missing {group} reference')
    for group,entries in lib.items():
        for e in entries:
            if group!='topics':refs(e['topics'],'topics')
            if 'sourceDiscussionIds' in e:refs(e['sourceDiscussionIds'],'discussions')
            if 'articleIds' in e:refs(e['articleIds'],'articles')
            if 'caseIds' in e:refs(e['caseIds'],'cases')
            if 'relatedArticleIds' in e:refs(e['relatedArticleIds'],'articles')
            for f in e.get('facts',[]):refs(f['sourceDiscussionIds'],'discussions')
    for shift in lib['shifts']:
        rs=shift['recordings']
        if len({r['id'] for r in rs})!=len(rs) or len({r['sequence'] for r in rs})!=len(rs):raise ValueError('Duplicate recording metadata')
    for d in lib['discussions']:
        shift=next((s for s in lib['shifts'] if s['id']==d['shiftId']),None)
        if not shift:raise ValueError('Missing shift')
        for seg in d['segments']:
            r=next((r for r in shift['recordings'] if r['id']==seg['recordingId']),None)
            if not r or not 0<=seg['startSeconds']<seg['endSeconds']<=r['durationSeconds']:raise ValueError('Invalid source bounds')
            if seg['clockConfidence']=='verified' and (not seg['clockTime'] or r['clockConfidence']!='verified'):raise ValueError('Unestablished clock certainty')
    return lib

def write_library(root,lib):
    root.mkdir(parents=True,exist_ok=True);write_json(root/'topics.json',lib['topics'])
    for group in GROUPS:
        if group=='topics':continue
        (root/group).mkdir(exist_ok=True)
        for entry in lib[group]:
            if group=='articles':
                meta={k:v for k,v in entry.items() if k!='body'}
                atomic_write(root/group/f"{entry['id']}.md",'---\n'+json.dumps(meta,indent=2)+'\n---\n\n'+entry['body']+'\n')
            else:write_json(root/group/f"{entry['id']}.json",entry)

def current_root(store):return store.root/'library/current'
def current(store):
    lib=empty_library()
    for row in store.db.execute('SELECT kind,data FROM library_records ORDER BY kind,id'):lib[row['kind']].append(json.loads(row['data']))
    return lib
def metadata(id,origin):return {'schemaVersion':1,'id':id,'origin':origin,'publication':{'status':'draft','audience':'private'}}
def fact(kind,text,ds):return {'kind':kind,'text':text,'sourceDiscussionIds':ds}
def unique_add(values,new):return list(dict.fromkeys([*values,*new]))
def retrieve(store,transcript,limit=12000):
    # Small local SQLite FTS index, rebuilt from the current snapshot. Only targeted matches enter model context.
    lib=current(store);db=store.db
    db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS retrieval USING fts5(id UNINDEXED,kind UNINDEXED,title,body)');db.execute('DELETE FROM retrieval')
    for a in lib['articles']:db.execute('INSERT INTO retrieval VALUES(?,?,?,?)',(a['id'],'article',a['title'],a['body']))
    for c in lib['cases']:db.execute('INSERT INTO retrieval VALUES(?,?,?,?)',(c['id'],'case',c['title'],json.dumps(c['facts'])+' '+c['linkBasis']))
    db.commit()
    words=list(dict.fromkeys(re.findall(r'[a-zA-Z]{4,}', ' '.join(s['text'] for s in transcript['segments']).lower())))[:60]
    if not words:return []
    query=' OR '.join('"'+w+'"' for w in words)
    rows=db.execute('SELECT id,kind,title,substr(body,1,1600) body FROM retrieval WHERE retrieval MATCH ? ORDER BY rank LIMIT 8',(query,)).fetchall()
    out=[];size=0
    for row in rows:
        v=dict(row);v['topicKey']=v['id'].removeprefix('a-');encoded=json.dumps(v)
        if size+len(encoded)>limit:break
        out.append(v);size+=len(encoded)
    return out

def commit(store,job,t,extracted,timezone_name='Unknown until configured'):
    manifest={'applied':[r['id'] for r in store.db.execute('SELECT id FROM applied_recordings')],'caseKeys':{r['key']:r['id'] for r in store.db.execute('SELECT key,id FROM case_keys')}}
    if job['id'] in manifest['applied']:return current_root(store) # Crash after DB commit, before job checkpoint: no duplicate append.
    lib=current(store);origin=job['origin'];dsmap={d['localId']:f"d-{job['id'][2:]}-{d['localId']}" for d in extracted['discussions']}
    shift=next((s for s in lib['shifts'] if s['id']==job['shift_id']),None)
    if shift is None:
        shift={**metadata(job['shift_id'],origin),'title':f"Learning archive · {job['shift_date']}",'date':job['shift_date'],'summary':'Detailed extracted discussions. Pending authorization and publication review.','topics':[],'timezone':timezone_name,'recordings':[],'processing':'partial'};lib['shifts'].append(shift)
    duration=max(s['end'] for s in t['segments'])
    if job['source_kind']=='audio':
        import wave
        with wave.open(str(store.root/'inputs'/f"{job['id']}.wav"),'rb') as wav:duration=wav.getnframes()/wav.getframerate()
    from datetime import datetime,timezone
    shift['recordings'].append({'id':job['id'],'sequence':job['sequence'],'durationSeconds':duration,'fileModifiedAt':datetime.fromtimestamp(job['source_mtime'],timezone.utc).isoformat(),'sourceSha256':job['sha256'],'capturedAt':t.get('capturedAt'),'clockConfidence':t.get('clockConfidence','unknown')})
    base=job['sequence']*100000
    for index,d in enumerate(extracted['discussions']):
        for topic in d['topics']:
            if not any(x['id']==topic['id'] for x in lib['topics']):lib['topics'].append({**topic,'description':'Suggested during extraction; pending owner curation.','color':'green'})
        topics=[x['id'] for x in d['topics']];shift['topics']=unique_add(shift['topics'],topics)
        entry={**metadata(dsmap[d['localId']],origin),'shiftId':shift['id'],'order':base+index,'title':d['title'],'topics':topics,
          'segments':[{'recordingId':job['id'],'startSeconds':q['start'],'endSeconds':q['end'],'clockTime':next((s.get('clockTime') for s in t['segments'] if s['start']==q['start'] and s['end']==q['end']),None),'clockConfidence':next((s.get('clockConfidence','unknown') for s in t['segments'] if s['start']==q['start'] and s['end']==q['end']),'unknown')} for q in d['quotes']],
          'account':d['account'],'facts':[fact(f['kind'],f['text'],[dsmap[d['localId']]]) for f in d['facts']],
          'questions':d['questions'],'conclusions':d['conclusions'],'articleIds':[],'caseIds':[]};lib['discussions'].append(entry)
    for a in extracted['articles']:
        aid='a-'+a['topicKey'];sources=[dsmap[x] for x in a['discussionIds']]
        topics=list(dict.fromkeys(x for d in lib['discussions'] if d['id'] in sources for x in d['topics']))
        article=next((v for v in lib['articles'] if v['id']==aid),None)
        if article is None:
            article={**metadata(aid,origin),'title':a['title'],'summary':a['summary'],'topics':topics,'updated':job['shift_date'],'sourceDiscussionIds':[],'relatedArticleIds':[],'body':'','educationalStatus':'synthetic-demonstration' if origin=='synthetic' else 'unreviewed-extraction'};lib['articles'].append(article)
        # Append-only additive notes protect earlier useful content. Stable keys prevent exact-topic duplicates.
        block=f"\n\n## Source addition · {job['shift_date']}\n\nAI-extracted educational account; source evidence and uncertainty require review.\n\n{a['bodyAddition']}"
        article['body']=(article['body']+block).strip();article['sourceDiscussionIds']=unique_add(article['sourceDiscussionIds'],sources);article['topics']=unique_add(article['topics'],topics);article['updated']=max(article['updated'],job['shift_date']);article['publication']={'status':'draft','audience':'private'}
        for d in lib['discussions']:
            if d['id'] in sources:d['articleIds']=unique_add(d['articleIds'],[aid])
    for c in extracted['cases']:
        scope=job['shift_id']+':'+c['caseKey'];cid=manifest['caseKeys'].get(scope)
        if cid is not None and not re.search(r'\b(returning|same|earlier|continuing|previous)\b',c['linkEvidence'],re.I):
            # Reused labels alone do not establish continuation; preserve a separate candidate case.
            scope+=':'+job['id'];cid=manifest['caseKeys'].get(scope)
            c=copy.deepcopy(c);c['uncertainties'].append('A repeated case label had no explicit continuation statement; cases remain separate.')
        sources=[dsmap[x] for x in c['discussionIds']]
        evidence=[f for d in lib['discussions'] if d['id'] in sources for f in d['facts']]
        topics=list(dict.fromkeys(x for d in lib['discussions'] if d['id'] in sources for x in d['topics']))
        if cid is None:
            cid='c-'+hashlib.sha256(scope.encode()).hexdigest()[:24];manifest['caseKeys'][scope]=cid
            case={**metadata(cid,origin),'title':c['title'],'summary':'Source-linked extracted case. Unstated facts remain unknown.','topics':topics,'species':c['species'],'patientLabel':'Case '+cid[2:8],'diagnosis':c['diagnosis'],'outcome':c['outcome'],'sourceDiscussionIds':sources,'facts':evidence,'linkBasis':c['linkEvidence'],'uncertainties':c['uncertainties']};lib['cases'].append(case)
        else:
            case=next(v for v in lib['cases'] if v['id']==cid);case['facts']+=evidence;case['sourceDiscussionIds']=unique_add(case['sourceDiscussionIds'],sources);case['topics']=unique_add(case['topics'],topics);case['uncertainties']=unique_add(case['uncertainties'],c['uncertainties']);case['publication']={'status':'draft','audience':'private'}
            for field in ['diagnosis','outcome']:
                if case[field] and c[field] and case[field]!=c[field]:
                    case['uncertainties'].append(f'Conflicting {field} accounts: {case[field]} / {c[field]}. Unresolved.');case[field]=None
                elif not case[field] and c[field] and not any(f'Conflicting {field}' in x for x in case['uncertainties']):case[field]=c[field]
            case['linkBasis']+='\n'+c['linkEvidence']
        for d in lib['discussions']:
            if d['id'] in sources:d['caseIds']=unique_add(d['caseIds'],[cid])
    qschema=Draft202012Validator(load_json(REPO/'schemas/question.schema.json'),format_checker=FormatChecker())
    rejected=[]
    for q in extracted['questions']:
        try:
            q=copy.deepcopy(q);localid=q.pop('id');q={**q,**metadata(f"q-{job['id'][2:]}-{localid}",origin)}
            q['sourceDiscussionIds']=[dsmap[x] for x in q['sourceDiscussionIds']];q['articleIds']=['a-'+x for x in q['articleIds']]
            qschema.validate(q)
            # JSON Schema cannot express all Zod refinements; enforce answer/reference consistency here too.
            if not q['sourceDiscussionIds'] or not set(q['topics'])<={x['id'] for x in lib['topics']}:raise ValueError('Question topic/source mismatch')
            if not set(q['articleIds'])<={x['id'] for x in lib['articles']}:raise ValueError('Question article mismatch')
            if q['format']=='multiple-choice':
                choices=[q['correct'],*q['distractors']]
                if len({v['id'] for v in choices})!=len(choices) or len({v['text'].lower() for v in choices})!=len(choices):raise ValueError('Duplicate answers')
            if q['format']=='multiple-select':
                keys=[v['id'] for v in q['choices']]
                if len(set(keys))!=len(keys) or not set(q['correctIds'])<set(keys) or not q['correctIds']:raise ValueError('Invalid multiple select')
            lib['questions'].append(q)
        except Exception as error:rejected.append({'question':q,'reason':type(error).__name__})
    # Completed files remain available even if a later recording in this shift fails.
    pending=[j for j in store.jobs() if j['shift_id']==shift['id'] and j['id']!=job['id'] and j['stage']!='done']
    shift['processing']='partial' if pending else 'complete';shift['publication']={'status':'draft','audience':'private'}
    validate_library(lib)
    if rejected:write_json(store.root/'quarantine'/f"{job['id']}-questions.json",rejected)
    # The durable per-recording checkpoint is one SQLite transaction. Markdown/JSON projection is
    # generated once per run, so a 100-file shift does not create 100 copies of the entire library.
    with store.db:
        for group,entries in lib.items():
            for entry in entries:
                data=json.dumps(entry,sort_keys=True,ensure_ascii=False)
                store.db.execute('INSERT INTO library_records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data WHERE data<>excluded.data',(group,entry['id'],data))
        for key,cid in manifest['caseKeys'].items():store.db.execute('INSERT OR REPLACE INTO case_keys VALUES(?,?)',(key,cid))
        store.db.execute('INSERT INTO applied_recordings VALUES(?)',(job['id'],))
    return current_root(store)


def materialize(store):
    lib=current(store)
    if not any(lib.values()):return None
    validate_library(lib);ptr=current_root(store)
    # Only two replaceable local file projections are retained. Independent encrypted backups and
    # authorized Git history preserve versions; the durable database and source checkpoints survive.
    applied=[r['id'] for r in store.db.execute('SELECT id FROM applied_recordings ORDER BY id')]
    content_hash=hashlib.sha256(json.dumps(lib,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if ptr.exists() and load_json(ptr/'manifest.json').get('contentHash')==content_hash:
        try:
            if read_library(ptr)==lib:return ptr.resolve()
        except (ValueError,KeyError,OSError,yaml.YAMLError):pass # Rebuild a damaged portable view from the durable canonical transaction.
    snapshot=store.root/'library/snapshots'/uuid.uuid4().hex
    write_library(snapshot,lib)
    write_json(snapshot/'manifest.json',{'applied':applied,'caseKeys':{r['key']:r['id'] for r in store.db.execute('SELECT key,id FROM case_keys')},'contentHash':content_hash,'createdAt':now()})
    previous=ptr.resolve() if ptr.exists() else None
    ptr.parent.mkdir(parents=True,exist_ok=True);temp=ptr.with_name('current-next');temp.unlink(missing_ok=True);temp.symlink_to(snapshot.relative_to(ptr.parent));os.replace(temp,ptr)
    directory=os.open(ptr.parent,os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    for candidate in (store.root/'library/snapshots').iterdir():
        if candidate.is_dir() and candidate not in [snapshot,previous]:shutil.rmtree(candidate)
    return snapshot
