"""Isolated local whole-shift ASR comparisons; never extraction or publication."""
from __future__ import annotations
import array
import base64
import dataclasses
import hashlib
import html
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import wave

from .audio_prepare import normalize_copy, duration_seconds
from .audio_filter import filter_copy
from .asr_quality import assess_segments, TranscriptionReviewRequired
from .evaluation import local_config
from .locations import local_path
from .morning import page
from .private import initialize_private, private_path
from .resources import check_resources, gpu_snapshot, ollama_clients, resident_models
from .runner import ProcessingDeferred
from .util import atomic_write, digest_file, load_json, write_json, now, lock
from .whisper_cpp import transcribe_cpp
from .native_asr import native, pcm, split_ranges

COMPARISON_SCRIPT = 'document.querySelectorAll("select[data-pane]").forEach((s,i)=>{s.value=i?"granite-vad":"whisper-continuous";function show(){document.getElementById(s.dataset.pane).replaceChildren(document.getElementById(s.value).content.cloneNode(true))}s.addEventListener("change",show);show()});document.addEventListener("click",e=>{const b=e.target.closest("[data-seek]");if(b){const a=document.getElementById("original");a.currentTime=Number(b.dataset.seek);a.play().catch(()=>{})}})'


def comparison_page(title,body):
    digest=base64.b64encode(hashlib.sha256(COMPARISON_SCRIPT.encode()).digest()).decode()
    return page(title,body).replace("script-src 'none'","script-src 'sha256-"+digest+"'; base-uri 'none'; form-action 'none'")


VOCABULARY=['buprenorphine','methadone','maropitant','ondansetron','dexmedetomidine',
            'gabapentin','enrofloxacin','amoxicillin','clavulanate','cephalexin',
            'urethral','urinalysis','azotemia','hematocrit','thrombocytopenia',
            'auscultation','thoracocentesis','abdominocentesis','cystocentesis','capnography']


def variants():
    result=[]
    for model,title in [('whisper','Whisper Large V3'),('granite','Granite Speech 4.1 2B'),
                        ('qwen-asr','Qwen3-ASR 1.7B'),('parakeet','Parakeet TDT v3'),('cohere','Cohere Transcribe 2B')]:
        for vad in (False,True):
            result.append({'id':model+('-vad' if vad else '-continuous'),'model':model,
                           'title':title+(' · speech detection' if vad else ' · no speech gate'),
                           'filter':'denoise','vad':vad,'vocabulary':[]})
    result.append({'id':'whisper-unfiltered','model':'whisper','title':'Whisper Large V3 · unfiltered · no speech gate',
                   'filter':'none','vad':False,'vocabulary':[]})
    result.append({'id':'granite-vocabulary','model':'granite','title':'Granite · speech detection + medical vocabulary',
                   'filter':'denoise','vad':True,'vocabulary':VOCABULARY})
    return result


def prepare(source,root,config_path,model_dir,runtime,authorization):
    source,root=private_path(source),private_path(root)
    if source==root or source in root.parents or root in source.parents or not authorization.strip():
        raise ValueError('Choose an isolated private workspace with explicit local authorization')
    manifest=root/'session.json'
    if manifest.exists():raise ValueError('Session already exists; use run/report to resume')
    cfg=local_config(config_path)
    db=sqlite3.connect(f'file:{source}/jobs.sqlite3?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:jobs=[dict(j) for j in db.execute("SELECT * FROM jobs WHERE source_kind='audio' ORDER BY sequence,id")]
    finally:db.close()
    if not jobs or len({j['shift_id'] for j in jobs})!=1 or len({j['origin'] for j in jobs})!=1:
        raise ValueError('Select one nonempty unmixed retained shift')
    initialize_private(root)
    write_json(root/'preparation.json',{'status':'preparing','at':now()})
    recordings=[]
    for number,job in enumerate(jobs,1):
        rid=job['id'];original=source/'inputs'/(rid+'.wav')
        if digest_file(original)!=job['sha256']:raise ValueError('Original recording differs from ledger')
        for folder in ('inputs','normalized','filtered'):(root/folder).mkdir(exist_ok=True,mode=0o700)
        os.link(original,root/'inputs'/(rid+'.wav'))
        norm=root/'normalized'/(rid+'.wav');old=source/'normalized'/(rid+'.wav')
        if old.exists():os.link(old,norm)
        else:normalize_copy(original,norm,max_seconds=86400)
        filtered=root/'filtered'/(rid+'.wav')
        filter_copy(norm,filtered,'denoise',max_seconds=86400)
        baseline=root/'baselines'/(rid+'.json');old=source/'transcripts'/(rid+'.json')
        if old.exists():write_json(baseline,load_json(old))
        recordings.append({'id':rid,'number':number,'name':job['source_name'],'originalSha256':job['sha256'],
                           'normalizedSha256':digest_file(norm),'filteredSha256':digest_file(filtered),
                           'durationSeconds':duration_seconds(norm)})
        write_json(root/'preparation.json',{'status':'preparing','recordings':number,'at':now()})
    model_plan=load_json(private_path(model_dir)/'models.json')
    runtime=local_path(runtime).resolve(strict=True)  # Read-only software may live in its own Git checkout.
    data={'version':1,'createdAt':now(),'authorizationRef':authorization,'source':str(source),
          'recordings':recordings,'variants':variants(),'models':model_plan,'configPath':str(config_path),
          'transcription':cfg['transcription'],'runtime':str(runtime),
          'runtimeCommit':subprocess.check_output(['git','-C',str(runtime),'rev-parse','HEAD'],text=True).strip(),
          'librarySha256':digest_file(runtime/'build-vulkan/src/libtranscribe.so'),
          'whisperModelSha256':digest_file(local_path(cfg['transcription']['model'])),
          'whisperExecutableSha256':digest_file(local_path(cfg['transcription']['executable'])),
          'windowSeconds':30,'overlapSeconds':1,
          'vad':{'threshold':.5,'min_speech_ms':250,'min_silence_ms':300,'speech_pad_ms':200}}
    write_json(manifest,data)
    write_json(root/'preparation.json',{'status':'complete','recordings':len(recordings),'at':now()})
    render(root)
    return data


def plans(root,session,rec,variant,api=None):
    folder='filtered' if variant['filter']=='denoise' else 'normalized'
    path=root/folder/(rec['id']+'.wav')
    if digest_file(path)!=rec['filteredSha256' if folder=='filtered' else 'normalizedSha256']:
        raise ValueError('Working audio changed')
    samples=pcm(path)
    ranges=[[0,len(samples)]];excluded=[]
    if variant['vad']:
        target=root/'vad'/(rec['id']+'.json')
        if target.exists():data=load_json(target)
        else:
            api=api or native(session)
            with api.Model(session['models']['vad']['path'],backend='cpu') as m,m.vad_session(n_threads=2) as v:
                result=v.run(samples,**session['vad'])
            ranges=[[int(s.start_sample),int(s.end_sample)] for s in result.segments]
            # VAD can pad beyond the final frame; bound sample intervals, not ASR timestamps.
            ranges=[[max(0,a),min(len(samples),b)] for a,b in ranges if max(0,a)<min(len(samples),b)]
            cursor=0
            for a,b in ranges:
                if a>cursor:excluded.append([cursor,a])
                cursor=max(cursor,b)
            if cursor<len(samples):excluded.append([cursor,len(samples)])
            data={'ranges':ranges,'excluded':excluded,'audioSha256':rec['filteredSha256'],'settings':session['vad']}
            write_json(target,data)
        if data['audioSha256']!=rec['filteredSha256'] or data['settings']!=session['vad']:raise ValueError('VAD binding changed')
        ranges=data['ranges'];excluded=data['excluded']
    return samples,split_ranges(ranges,len(samples)),excluded


def progress(root,**values):write_json(root/'progress.json',{'at':now(),**values})


def quiet(cfg):
    """Between calls: loaded suite model is ours; never evict other GPU work."""
    ollama_clients()
    if resident_models(cfg):raise ProcessingDeferred('An Ollama model appeared; yielding without eviction')
    # DRM busy% includes recent work from our just-finished call. Let that
    # measurement settle before treating it as another application's activity.
    deadline=time.monotonic()+10;clean=0
    while time.monotonic()<deadline:
        ollama_clients()
        if resident_models(cfg):raise ProcessingDeferred('Ollama became resident; yielding without eviction')
        gpu=gpu_snapshot()
        if gpu['free']<1024:raise ProcessingDeferred('Insufficient GPU headroom; yielding')
        clean=clean+1 if gpu['busy']<=cfg['unattended']['gpu_busy_limit'] else 0
        if clean>=2:return
        time.sleep(.5)
    raise ProcessingDeferred('Shared GPU remains active; yielding')


def worker(root,variant_id):
    root=private_path(root);session=load_json(root/'session.json')
    variant=next(x for x in session['variants'] if x['id']==variant_id)
    cfg=local_config(Path(session['configPath']))
    check_resources(cfg,'transcribe')
    if variant['vad'] and digest_file(Path(session['models']['vad']['path']))!=session['models']['vad']['sha256']:
        raise ValueError('VAD model integrity mismatch')
    api=native(session);model=None;engine=None
    try:
        if variant['model']!='whisper':
            item=session['models'][variant['model']]
            if digest_file(Path(item['path']))!=item['sha256']:raise ValueError('Model weight integrity mismatch')
            devices=[d for d in api.backends() if d.kind=='vulkan' and d.device_type=='gpu' and '7900' in d.description]
            if len(devices)!=1:raise ValueError('Expected one Vulkan Radeon RX 7900 device')
            model=api.Model(item['path'],backend='vulkan',device=devices[0])
            if model.device.kind!='vulkan':raise ValueError('Requested GPU acceleration was not selected')
            if variant['vocabulary'] and not model.supports('vocabulary'):raise ValueError('This pinned model has no vocabulary support')
            engine=model.session(n_threads=4,n_ctx=4096)
            write_json(root/'backends'/(variant_id+'.json'),{'backend':model.backend,'device':model.device.description,'model':model.variant,'capabilities':dataclasses.asdict(model.capabilities)})
        else:
            if digest_file(local_path(session['transcription']['model']))!=session['whisperModelSha256'] or digest_file(local_path(session['transcription']['executable']))!=session['whisperExecutableSha256']:
                raise ValueError('Whisper installation changed')
        for rec in session['recordings']:
            destination=root/'results'/variant_id/rec['id'];done=destination/'result.json'
            if done.exists():continue
            progress(root,variant=variant_id,recording=rec['number'],stage='preparing-audio')
            audio,ranges,excluded=plans(root,session,rec,variant,api)
            write_json(destination/'plan.json',{'ranges':ranges,'excluded':excluded,'timing':'Input-window bounds unless explicitly model-timed. Overlapping windows intentionally remain separate.'})
            segments=[];failures=[];started=time.monotonic();seconds=0
            for i,(a,b) in enumerate(ranges):
                for retry in range(2):
                    checkpoint=destination/f'window-{i:04d}.json'
                    if checkpoint.exists() and load_json(checkpoint)['status']=='failed':
                        attempt=destination/f'attempt-{i:04d}.json'
                        if attempt.exists() and load_json(attempt)['attempts']<2:
                            checkpoint.rename(destination/f'failed-window-{i:04d}-{time.time_ns()}.json')
                    if checkpoint.exists():saved=load_json(checkpoint)
                    else:
                        quiet(cfg)
                        progress(root,variant=variant_id,recording=rec['number'],window=i+1,windows=len(ranges),stage='transcribing')
                        attempt_path=destination/f'attempt-{i:04d}.json'
                        attempts=load_json(attempt_path)['attempts'] if attempt_path.exists() else 0
                        if attempts>=2:
                            saved={'status':'failed','start':a/16000,'end':b/16000,'error':'Interrupted or failed twice','seconds':0,'segments':[]}
                        else:
                            write_json(attempt_path,{'attempts':attempts+1})
                            t=time.monotonic();gpu=[];stop=threading.Event()
                            def monitor():
                                while not stop.wait(.5):
                                    try:gpu.append(gpu_snapshot())
                                    except ProcessingDeferred:pass
                            thread=threading.Thread(target=monitor,daemon=True);thread.start()
                            saved={'status':'completed-unreviewed','start':a/16000,'end':b/16000,'segments':[]}
                            timer=None
                            try:
                                if engine:
                                    timer=threading.Timer(600,engine.cancel);timer.start()
                                    result=engine.run(audio[a:b],language='en',timestamps='auto',vocabulary=variant['vocabulary'] or None)
                                    rows=[{'start':a/16000+s.t0_ms/1000,'end':a/16000+s.t1_ms/1000,'text':s.text,'timing':'model'} for s in result.segments if s.text.strip()] if result.timestamp_kind!='none' else []
                                    if not rows:rows=[{'start':a/16000,'end':b/16000,'text':result.text,'timing':'audio-window'}]
                                    saved.update(segments=rows,text=result.text,rawText=result.raw_text,nativeTimings=dataclasses.asdict(result.timings))
                                else:
                                    clip=destination/'working-window.wav';clip.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                                    with wave.open(str(clip),'wb') as w:
                                        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
                                        ints=array.array('h',(max(-32768,min(32767,round(x*32768))) for x in audio[a:b]))
                                        if sys.byteorder=='big':ints.byteswap()
                                        w.writeframes(ints.tobytes())
                                    settings={**session['transcription'],'details_path':str(destination/f'raw-{i:04d}.json'),'timeout_seconds':600}
                                    try:result=transcribe_cpp(clip,settings)
                                    except TranscriptionReviewRequired:
                                        raw=load_json(Path(settings['details_path']))
                                        result={'segments':[{'start':0,'end':(b-a)/16000,'text':' '.join(x['text'] for x in raw.get('transcription',[]))}],'transcriptionBackend':{'gpuAccelerationConfirmed':None}}
                                        saved['status']='timestamp-review-required'
                                    saved.update(segments=[{**s,'start':a/16000+s['start'],'end':a/16000+s['end'],'timing':'model' if saved['status']=='completed-unreviewed' else 'audio-window'} for s in result['segments']],backend=result['transcriptionBackend'])
                            except Exception as error:
                                saved.update(status='failed',error=type(error).__name__)
                            finally:
                                if timer:timer.cancel()
                                stop.set();thread.join(timeout=2)
                                saved.update(seconds=round(time.monotonic()-t,3),peakVramMiB=round(max((x['used'] for x in gpu),default=0),1))
                        write_json(checkpoint,saved)
                    if saved['status']!='failed':break
                    attempt=destination/f'attempt-{i:04d}.json'
                    if attempt.exists() and load_json(attempt)['attempts']>=2:break
                segments.extend(saved['segments']);seconds+=saved['seconds']
                if saved['status']!='completed-unreviewed':failures.append(i)
            out={'variant':variant_id,'number':rec['number'],'status':'partial-review' if failures else 'completed-unreviewed',
                 'segments':segments,'failedWindows':failures,'speechWindows':len(ranges),'excludedRanges':excluded,
                 'seconds':round(seconds,3),'quality':assess_segments([s for s in segments if s['text'].strip()]),'wordCount':sum(len(s['text'].split()) for s in segments)}
            write_json(done,out);render(root,rec['id'])
            print(json.dumps({'variant':variant_id,'recording':rec['number'],'status':out['status']}),flush=True)
    finally:
        if engine:engine.close()
        if model:model.close()


def run(root):
    root=private_path(root);session=load_json(root/'session.json')
    with lock(root):
        for variant in session['variants']:
            if all((root/'results'/variant['id']/r['id']/'result.json').exists() for r in session['recordings']):continue
            needed=[session['models'][k] for k in ([variant['model']] if variant['model']!='whisper' else [])+(['vad'] if variant['vad'] else [])]
            if any(not Path(m['path']).exists() or Path(m['path']).stat().st_size!=m['bytes'] for m in needed):
                progress(root,stage='waiting-model-downloads',variant=variant['id']);render(root)
                raise ProcessingDeferred('Public model downloads are not finished')
            meta=root/'variant-status'/(variant['id']+'.json')
            state=load_json(meta) if meta.exists() else {'attempts':0}
            if state.get('attempts',0)>=2:continue
            state.update(status='running',attempts=state['attempts']+1);write_json(meta,state)
            diagnostics=root/'diagnostics';diagnostics.mkdir(exist_ok=True,mode=0o700)
            with (diagnostics/(variant['id']+'.log')).open('a') as log:
                p=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[2]/'scripts/compare-shift-asr.py'),'worker','--workspace',str(root),'--variant',variant['id']],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                last=time.monotonic();old=None
                while p.poll() is None:
                    time.sleep(2)
                    marker=(root/'progress.json').stat().st_mtime_ns if (root/'progress.json').exists() else 0
                    if marker!=old:old=marker;last=time.monotonic()
                    if time.monotonic()-last>900:
                        os.killpg(p.pid,signal.SIGTERM)
                        try:p.wait(timeout=5)
                        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                        break
                code=p.returncode
            if code==75:
                state.update(status='waiting-resources',attempts=state['attempts']-1);write_json(meta,state)
                progress(root,stage='waiting-resources',variant=variant['id'])
                render(root);raise ProcessingDeferred('Comparison yielded to shared GPU use')
            state.update(status='completed' if code==0 else 'failed',exitCode=code,at=now());write_json(meta,state)
            render(root)
        statuses=[load_json(p) for p in (root/'variant-status').glob('*.json')]
        if any(x['status']=='failed' and x['attempts']<2 for x in statuses):
            progress(root,stage='retry-pending');render(root)
            raise RuntimeError('One bounded variant retry remains')
        progress(root,stage='finished-with-failures' if any(x['status']=='failed' for x in statuses) else 'finished');render(root)


def render(root,only_recording=None):
    root=private_path(root);session=load_json(root/'session.json');e=lambda x:html.escape(str(x),quote=True)
    review=root/'review';review.mkdir(exist_ok=True,mode=0o700)
    progress_data=load_json(root/'progress.json') if (root/'progress.json').exists() else {'stage':'queued'}
    summaries={v['id']:{'completed':0,'failed':0,'seconds':0} for v in session['variants']};links=[]
    for rec in session['recordings']:
        items=[]
        for variant in session['variants']:
            path=root/'results'/variant['id']/rec['id']/'result.json'
            value=load_json(path) if path.exists() else {'status':'pending','segments':[]}
            if path.exists():
                summaries[variant['id']]['completed']+=1;summaries[variant['id']]['seconds']+=value['seconds']
                summaries[variant['id']]['failed']+=bool(value['failedWindows'])
            items.append((variant,value))
        links.append('<li><a href="recording-'+str(rec['number']).zfill(3)+'.html">Recording '+str(rec['number'])+'</a> · '+str(round(rec['durationSeconds'],1))+' seconds</li>')
        if only_recording and only_recording!=rec['id']:continue
        body='<p><a href="asr-comparison.html">All recordings and model status</a></p><p>PRIVATE, unreviewed transcription comparison. No quality winner has been selected. Windows overlap by one second; boundary repetitions are not automatically merged. Some timestamps are input-window bounds, not word alignment.</p>'
        body+='<p>Original, unfiltered audio (normalized playback copy)</p><audio id="original" controls preload="none" src="../normalized/'+e(rec['id'])+'.wav"></audio><p>Denoised audio</p><audio id="filtered" controls preload="none" src="../filtered/'+e(rec['id'])+'.wav"></audio>'
        options=''.join('<option value="'+e(v['id'])+'">'+e(v['title'])+'</option>' for v,_ in items)
        body+='<p>Change either model below. Listen before judging; fewer words or fewer repetitions do not prove greater accuracy.</p><div class="columns">'+''.join('<section><select aria-label="'+side+' transcription" data-pane="'+side+'">'+options+'</select><div id="'+side+'"></div></section>' for side in ('left','right'))+'</div>'
        for v,value in items:
            content='<p>Status: '+e(value['status'])+'</p>'
            for s in value['segments']:
                content+='<p><button data-seek="'+e(s['start'])+'">'+e(round(s['start'],2))+'–'+e(round(s['end'],2))+'s</button> <small>'+e(s.get('timing','audio-window'))+'</small><br>'+e(s['text'] or '[No words returned]')+'</p>'
            if value.get('excludedRanges'):
                content+='<details><summary>Audio excluded by speech detection — not confirmed silence</summary>'+''.join('<p><button data-seek="'+str(a/16000)+'">'+str(round(a/16000,2))+'–'+str(round(b/16000,2))+'s</button> Speech not detected; listen to check for omissions.</p>' for a,b in value['excludedRanges'])+'</details>'
            content+='<p>Windows needing review: '+e(value.get('failedWindows',[]))+'. Raw outputs/checkpoints remain private for inspection.</p>'
            body+='<template id="'+e(v['id'])+'">'+content+'</template>'
            if value['segments']:
                text='# '+v['title']+' · recording '+str(rec['number'])+'\n\nPrivate, unreviewed ASR. Windows can overlap; window bounds are not exact word timestamps.\n\n'
                text+='\n\n'.join(f"[{r['start']:.2f}–{r['end']:.2f}s; {r.get('timing','audio-window')}] {r['text']}" for r in value['segments'])
                atomic_write(root/'readable'/v['id']/('recording-'+str(rec['number']).zfill(3)+'.md'),text+'\n')
        baseline=root/'baselines'/(rec['id']+'.json')
        if baseline.exists():
            body+='<details><summary>Earlier saved Whisper transcript (unchanged reference for comparison)</summary>'
            for s in load_json(baseline)['segments']:
                body+='<p><button data-seek="'+e(s['start'])+'">'+e(s['start'])+'s</button> '+e(s['text'])+'</p>'
            body+='</details>'
        body+='<style>.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}select{max-width:100%;padding:10px}audio{width:100%}button{cursor:pointer}section{min-width:0} @media(max-width:750px){.columns{grid-template-columns:1fr}}</style><script>'+COMPARISON_SCRIPT+'</script>'
        atomic_write(review/('recording-'+str(rec['number']).zfill(3)+'.html'),comparison_page('Recording '+str(rec['number'])+' · ASR comparison',body))
    body='<p>PRIVATE · local ASR only · originals and earlier transcripts retained · no extraction, uploads or publication.</p><p>Quality is the selection criterion. Runtime is shown only for eventual overnight-capacity planning. No reference transcript has been supplied, so no word-accuracy score or quality ranking is claimed.</p><pre>'+e(json.dumps(progress_data,indent=2))+'</pre><table><thead><tr><th>Variant</th><th>Saved recordings</th><th>With failed/review windows</th><th>Inference minutes</th></tr></thead><tbody>'
    for v in session['variants']:
        s=summaries[v['id']];status=root/'variant-status'/(v['id']+'.json')
        label=load_json(status).get('status','queued') if status.exists() else 'queued'
        body+='<tr><td>'+e(v['title'])+' · '+e(label)+'</td><td>'+str(s['completed'])+'/'+str(len(session['recordings']))+'</td><td>'+str(s['failed'])+'</td><td>'+str(round(s['seconds']/60,1))+'</td></tr>'
    body+='</tbody></table><p>Refresh for saved progress. Compare any two models within each recording. Noise-only intervals and difficult speech need listening review.</p><ol>'+''.join(links)+'</ol>'
    document=page('Last shift · transcription model comparison',body)
    atomic_write(review/'index.html',document)
    atomic_write(review/'asr-comparison.html',document)
    write_json(root/'summary.json',{'updatedAt':now(),'variants':summaries,'recordings':len(session['recordings']),'progress':progress_data})
