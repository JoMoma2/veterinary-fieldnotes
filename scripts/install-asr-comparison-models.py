"""Download public, pinned ASR comparison weights outside every Git checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

from vet_pipeline.private import private_path
from vet_pipeline.util import write_json

MODELS = {
    'granite': ('handy-computer/granite-speech-4.1-2b-gguf', 'granite-speech-4.1-2b-F16.gguf'),
    'qwen-asr': ('handy-computer/Qwen3-ASR-1.7B-gguf', 'Qwen3-ASR-1.7B-F16.gguf'),
    'parakeet': ('handy-computer/parakeet-tdt-0.6b-v3-gguf', 'parakeet-tdt-0.6b-v3-F16.gguf'),
    'cohere': ('handy-computer/cohere-transcribe-03-2026-gguf', 'cohere-transcribe-03-2026-F16.gguf'),
    'vad': ('handy-computer/silero-vad-v6.2-gguf', 'silero-vad-v6.2-F32.gguf'),
}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--plan-only',action='store_true')
    a=p.parse_args();root=private_path(a.directory)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    manifest=root/'models.json'
    if manifest.exists():
        plan=json.loads(manifest.read_text())
    else:
        plan={}
        for key,(repo,name) in MODELS.items():
            with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}?blobs=true',timeout=60) as response:
                metadata=json.load(response)
            item=next(f for f in metadata['siblings'] if f['rfilename']==name)
            lfs=item['lfs']
            plan[key]={'repository':repo,'revision':metadata['sha'],'filename':name,
                       'sha256':lfs['sha256'],'bytes':lfs['size'],'path':str(root/name)}
        write_json(manifest,plan)
    required=sum(x['bytes'] for x in plan.values() if not Path(x['path']).exists())
    if shutil.disk_usage(root).free<required+10*1024**3:
        raise RuntimeError('Insufficient disk headroom for the selected models')
    print(json.dumps({'models':list(plan),'downloadGB':round(required/1e9,2)}),flush=True)
    if a.plan_only:return
    for key,x in plan.items():
        target=Path(x['path']);partial=target.with_suffix(target.suffix+'.part')
        if not target.exists():
            start=partial.stat().st_size if partial.exists() else 0
            req=urllib.request.Request(f"https://huggingface.co/{x['repository']}/resolve/{x['revision']}/{x['filename']}",headers={'Range':f'bytes={start}-'} if start else {})
            with urllib.request.urlopen(req,timeout=120) as response:
                if start and (response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-')):
                    start=0
                with partial.open('ab' if start else 'wb') as f:
                    shutil.copyfileobj(response,f,1024*1024)
            checked=partial
        else:checked=target
        digest=hashlib.file_digest(checked.open('rb'),'sha256').hexdigest()
        if checked.stat().st_size!=x['bytes'] or digest!=x['sha256']:
            raise RuntimeError('Downloaded model integrity validation failed: '+key)
        if checked==partial:partial.replace(target)
        print(json.dumps({'model':key,'status':'verified','bytes':x['bytes']}),flush=True)


if __name__=='__main__':main()
