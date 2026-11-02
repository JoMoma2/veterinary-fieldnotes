from __future__ import annotations
import json, time
from .util import load_json,now,write_json,lock
from .ingest import transcribe
from .extraction import extract_recording
from .library import retrieve,commit,materialize

def run(store,cfg,force_retry=False):
    results=[]
    with lock(store.root):
        for old in store.jobs():
            job=store.get(old['id'])
            if job['stage']=='done':continue
            if job['attempts']>=cfg['retry']['max_attempts'] or (not force_retry and job['retry_after']>time.time()):continue
            try:
                if job['stage']=='transcribe':
                    transcribe(store,job,cfg);store.update(job['id'],stage='extract',attempts=0,error=None,retry_after=0);job=store.get(job['id'])
                t=load_json(store.root/'transcripts'/f"{job['id']}.json")
                if job['stage']=='extract':
                    data=extract_recording(store,job,t,cfg,retrieve(store,t,cfg['provider']['context_char_limit']))
                    write_json(store.root/'extractions'/f"{job['id']}.json",data);store.update(job['id'],stage='commit',attempts=0,error=None,retry_after=0);job=store.get(job['id'])
                if job['stage']=='commit':
                    data=load_json(store.root/'extractions'/f"{job['id']}.json");commit(store,job,t,data,cfg['archive']['timezone'])
                    store.update(job['id'],stage='done',attempts=0,error=None,retry_after=0,completed_at=now())
                result={'job':job['id'],'status':'done'}
            except Exception as error:
                attempts=job['attempts']+1
                # Exception class only in durable logs: model/server error text may contain clinical data.
                store.update(job['id'],attempts=attempts,error=type(error).__name__,retry_after=time.time()+cfg['retry']['base_delay_seconds']*2**(attempts-1))
                result={'job':job['id'],'status':'failed','stage':job['stage'],'attempt':attempts,'error':type(error).__name__}
                if type(error) is ValueError:result['reason']=str(error)
                elif isinstance(error,TimeoutError):result['reason']='Operation timed out; retry is bounded and completed stages are preserved.'
            results.append(result)
            logfile=store.root/'events.jsonl'
            with logfile.open('a') as f:f.write(json.dumps({'at':now(),**result})+'\n');f.flush()
        try:materialize(store)
        except Exception as error:results.append({'status':'failed','stage':'file-projection','error':type(error).__name__,'reason':'Durable recording commits remain saved. Run again to regenerate portable files.'})
    return results

def reset_failed(store,id):
    if not store.get(id):raise ValueError('Unknown job ID')
    store.update(id,attempts=0,retry_after=0,error=None)
