import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace
import wave

import pytest
from vet_pipeline import asr_suite as s
from vet_pipeline.util import write_json,load_json,digest_file
from vet_pipeline.runner import ProcessingDeferred


def make_session(tmp_path):
    root=tmp_path/'private';root.mkdir()
    for folder in ('normalized','filtered','inputs'):
        (root/folder).mkdir()
        with wave.open(str(root/folder/'r-test.wav'),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
    exe=tmp_path/'whisper-cli';exe.write_text('synthetic fake executable')
    model=tmp_path/'whisper.bin';model.write_text('synthetic fake model')
    v=s.variants()[0]
    data={'recordings':[{'id':'r-test','number':1,'name':'synthetic.wav','durationSeconds':1,
          'normalizedSha256':digest_file(root/'normalized/r-test.wav'),'filteredSha256':digest_file(root/'filtered/r-test.wav')}],
          'variants':[v], 'configPath':str(tmp_path/'config.toml'),
          'transcription':{'model':str(model),'executable':str(exe)},
          'whisperModelSha256':digest_file(model),'whisperExecutableSha256':digest_file(exe),
          'models':{},'vad':{}}
    write_json(root/'session.json',data)
    return root,data


def test_window_coverage_preserves_absolute_offsets_and_overlap():
    assert s.split_ranges([],200)==[]
    assert s.split_ranges([[10,100]],100,maximum=40,overlap=5)==[[10,50],[45,85],[80,100]]
    with pytest.raises(ValueError):s.split_ranges([[0,101]],100)


def test_failed_window_retries_then_resume_reuses_saved_words(tmp_path,monkeypatch):
    root,data=make_session(tmp_path);calls=[]
    before=digest_file(root/'inputs/r-test.wav')
    monkeypatch.setattr(s,'local_config',lambda p:{})
    monkeypatch.setattr(s,'check_resources',lambda *a:None)
    monkeypatch.setattr(s,'quiet',lambda *a:None)
    monkeypatch.setattr(s,'native',lambda *a:None)
    def infer(*a):
        calls.append(1)
        if len(calls)==1:raise TimeoutError()
        return {'segments':[{'start':0,'end':1,'text':'Synthetic medical discussion'}],
                'transcriptionBackend':{'gpuAccelerationConfirmed':True}}
    monkeypatch.setattr(s,'transcribe_cpp',infer)
    s.worker(root,'whisper-continuous')
    saved=load_json(root/'results/whisper-continuous/r-test/result.json')
    assert len(calls)==2 and saved['failedWindows']==[]
    assert saved['segments'][0]['text']=='Synthetic medical discussion'
    assert list((root/'results/whisper-continuous/r-test').glob('failed-window-*.json'))
    s.worker(root,'whisper-continuous')
    assert len(calls)==2 and digest_file(root/'inputs/r-test.wav')==before


def test_report_escapes_transcript_and_authorizes_only_its_static_script(tmp_path):
    import base64
    root,data=make_session(tmp_path)
    write_json(root/'results/whisper-continuous/r-test/result.json',{
        'status':'completed-unreviewed','seconds':1,'failedWindows':[],
        'segments':[{'start':0,'end':1,'text':'<script>BAD()</script>','timing':'audio-window'}]})
    s.render(root)
    document=(root/'review/recording-001.html').read_text()
    assert '<script>BAD()</script>' not in document and '&lt;script&gt;BAD()' in document
    digest=base64.b64encode(hashlib.sha256(s.COMPARISON_SCRIPT.encode()).digest()).decode()
    assert "script-src 'sha256-"+digest+"'" in document
    assert 'src="../normalized/r-test.wav"' in document and 'data-seek="0"' in document
    assert 'audio-window' in document
    assert (root/'review/asr-comparison.html').exists()


def test_incomplete_model_download_defers_without_spending_attempts(tmp_path):
    root,data=make_session(tmp_path)
    data['variants']=[s.variants()[3]]
    data['models']={'granite':{'path':str(tmp_path/'not-yet-downloaded'),'bytes':4},
                    'vad':{'path':str(tmp_path/'also-pending'),'bytes':4}}
    write_json(root/'session.json',data)
    with pytest.raises(ProcessingDeferred):s.run(root)
    assert not list((root/'variant-status').glob('*.json'))
    assert load_json(root/'progress.json')['stage']=='waiting-model-downloads'


def test_own_recent_gpu_activity_can_settle_without_restart(monkeypatch):
    shots=iter([80,50,0,0]);sleeps=[]
    monkeypatch.setattr(s,'ollama_clients',lambda:None)
    monkeypatch.setattr(s,'resident_models',lambda c:[])
    monkeypatch.setattr(s,'gpu_snapshot',lambda:{'busy':next(shots),'free':8000})
    monkeypatch.setattr(s.time,'sleep',lambda n:sleeps.append(n))
    s.quiet({'unattended':{'gpu_busy_limit':20}})
    assert len(sleeps)==3


def test_prepare_reads_software_checkout_without_putting_clinical_data_in_git(tmp_path,monkeypatch):
    import sqlite3
    source=tmp_path/'source';(source/'inputs').mkdir(parents=True);(source/'normalized').mkdir()
    audio=source/'inputs/r-test.wav'
    with wave.open(str(audio),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
    shutil.copy2(audio,source/'normalized/r-test.wav')
    db=sqlite3.connect(source/'jobs.sqlite3')
    db.execute('CREATE TABLE jobs(id,sha256,sequence,source_name,source_kind,shift_id,origin)')
    db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('r-test',digest_file(audio),1,'synthetic.wav','audio','s-test','synthetic'));db.commit();db.close()
    models=tmp_path/'models';models.mkdir();write_json(models/'models.json',{})
    runtime=tmp_path/'software';(runtime/'.git').mkdir(parents=True);(runtime/'.git/HEAD').write_text('ref: refs/heads/main')
    (runtime/'build-vulkan/src').mkdir(parents=True);(runtime/'build-vulkan/src/libtranscribe.so').touch()
    exe=tmp_path/'exe';exe.touch();model=tmp_path/'model';model.touch()
    monkeypatch.setattr(s,'local_config',lambda p:{'transcription':{'model':str(model),'executable':str(exe)}})
    monkeypatch.setattr(s,'filter_copy',lambda a,b,*args,**kw:shutil.copy2(a,b))
    monkeypatch.setattr(s.subprocess,'check_output',lambda *a,**kw:'synthetic-commit\n')
    root=tmp_path/'comparison';before=digest_file(audio)
    data=s.prepare(source,root,tmp_path/'config.toml',models,runtime,'synthetic-test')
    assert len(data['recordings'])==1 and digest_file(audio)==before
    assert (root/'review/recording-001.html').exists()
    with pytest.raises(ValueError):s.prepare(source,runtime/'private',tmp_path/'config.toml',models,runtime,'test')
