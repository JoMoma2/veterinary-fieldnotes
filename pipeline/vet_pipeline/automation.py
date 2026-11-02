from __future__ import annotations
import hashlib,json,os,subprocess,time
from datetime import datetime
from pathlib import Path
from .ingest import ingest
from .util import lock

def discover(cfg):
    u=cfg['usb']
    if not u['roots'] or not (u['device_label'] or u['sentinel']):return []
    result=subprocess.run(['lsblk','--json','--paths','--output','NAME,LABEL,MOUNTPOINTS,TRAN,RM'],check=True,capture_output=True,text=True,timeout=15)
    devices=json.loads(result.stdout)['blockdevices'];mounts=[]
    def walk(items,usb=False):
        for item in items:
            is_usb=usb or item.get('tran')=='usb'
            if is_usb:
                for mount in item.get('mountpoints') or []:
                    if not mount:continue
                    p=Path(mount).resolve()
                    if not any(p==Path(root).resolve() or Path(root).resolve() in p.parents for root in u['roots']):continue
                    if u['device_label'] and item.get('label')!=u['device_label']:continue
                    if u['sentinel'] and not (p/u['sentinel']).is_file():continue
                    mounts.append(p)
            walk(item.get('children',[]),is_usb)
    walk(devices);return sorted(set(mounts))

def scan(store,cfg,source:Path,date:str):
    u=cfg['usb']
    if not u['authorization_ref']:raise ValueError('USB importing requires a recording/processing authorization reference')
    if not source.is_dir():raise ValueError('Recorder directory is unavailable')
    # Deterministic import ordering only; mtimes remain unverified and never establish actual discussion clock time.
    files=sorted((p for p in source.glob(u['glob']) if p.is_file() and not p.is_symlink() and p.suffix.lower()=='.wav'),key=lambda p:(p.stat().st_mtime_ns,str(p.relative_to(source))))
    results=[];device=hashlib.sha256(str(source).encode()).hexdigest()[:8];shift='s-'+date+'-'+device
    with lock(store.root):
        for path in files:
            try:
                if time.time()-path.stat().st_mtime<u['stable_seconds']:continue
                if source.resolve() not in path.resolve().parents:raise ValueError('Path escapes recorder root')
                id,created=ingest(store,path,shift,date,u['origin'],u['authorization_ref']);results.append({'id':id,'imported':created})
            except Exception as e:results.append({'status':'failed','error':type(e).__name__})
    return results
