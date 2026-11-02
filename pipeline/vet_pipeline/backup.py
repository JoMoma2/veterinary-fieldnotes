from __future__ import annotations
import hashlib,io,json,os,shutil,subprocess,tarfile,tempfile,time,uuid
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from .library import current_root,read_library,validate_library,materialize
from .util import atomic_write,digest_file,load_json,write_json,now,lock

def create_key(path:Path):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key());f.flush();os.fsync(f.fileno())

def cipher(keyfile):
    if keyfile.stat().st_mode & 0o077:raise ValueError('Backup key must be readable only by its owner: chmod 600')
    return Fernet(keyfile.read_bytes().strip())

def create_backup(store,keyfile:Path,destination:Path):
    with lock(store.root):
        materialize(store)
        root=current_root(store)
        if not root.exists():raise ValueError('No completed library snapshot')
        validate_library(read_library(root))
        entries={}
        for file in root.rglob('*'):
            if file.is_symlink():raise ValueError('Snapshot contains a symlink')
            if file.is_file():
                if file.suffix not in ['.json','.md']:raise ValueError('Unexpected file in library snapshot')
                entries[str(file.relative_to(root))]=file.read_bytes()
        manifest={name:hashlib.sha256(value).hexdigest() for name,value in entries.items()}
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
            for name,value in {**entries,'BACKUP-MANIFEST.json':json.dumps(manifest).encode()}.items():
                info=tarfile.TarInfo(name);info.size=len(value);info.mode=0o600;archive.addfile(info,io.BytesIO(value))
        encrypted=cipher(keyfile).encrypt(buffer.getvalue());sha=hashlib.sha256(encrypted).hexdigest()
        destination.mkdir(parents=True,exist_ok=True);artifact='backup-'+now().replace(':','').replace('.','-')+'-'+uuid.uuid4().hex[:8]
        file=destination/f'{artifact}.vkb';atomic_write(file,encrypted)
        # Verify decryption, every hash, and data integrity before registering a valid backup.
        inspect_backup(file,keyfile)
        applied=load_json(root/'manifest.json')['applied']
        with store.db:store.db.execute('INSERT INTO artifacts(id,path,sha256,created_at,applied_ids,snapshot_hash) VALUES(?,?,?,?,?,?)',(artifact,str(file.resolve()),sha,now(),json.dumps(applied),load_json(root/'manifest.json')['contentHash']))
        return file

def inspect_backup(file:Path,keyfile:Path):
    raw=cipher(keyfile).decrypt(file.read_bytes());entries={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        total=0
        for member in archive.getmembers():
            path=Path(member.name)
            allowed_root=member.name in ['BACKUP-MANIFEST.json','topics.json','manifest.json']
            allowed_record=len(path.parts)==2 and path.parts[0] in ['articles','cases','shifts','discussions','questions'] and path.suffix==('.md' if path.parts[0]=='articles' else '.json')
            if not (allowed_root or allowed_record):raise ValueError('Unexpected archive content')
            if not member.isfile() or path.is_absolute() or '..' in path.parts or member.name in entries:raise ValueError('Unsafe archive member')
            total+=member.size
            if total>512*1024*1024:raise ValueError('Backup exceeds configured safe library restore size')
            entries[member.name]=archive.extractfile(member).read()
    manifest=json.loads(entries.pop('BACKUP-MANIFEST.json'))
    if set(manifest)!=set(entries) or any(hashlib.sha256(value).hexdigest()!=manifest[name] for name,value in entries.items()):raise ValueError('Backup integrity failure')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,value in entries.items():atomic_write(root/name,value)
        validate_library(read_library(root))
    return entries

def restore(file,keyfile,target):
    if target.exists():raise ValueError('Restore destination must not exist; never overwrite a working library')
    entries=inspect_backup(file,keyfile);target.parent.mkdir(parents=True,exist_ok=True)
    staged=target.with_name(target.name+'.restore-'+uuid.uuid4().hex)
    try:
        for name,value in entries.items():atomic_write(staged/name,value)
        os.rename(staged,target)
    finally:
        if staged.exists():shutil.rmtree(staged)
    return target

def upload_backups(store,cfg):
    p=cfg['backup'];remote=p['remote']
    if not remote:raise ValueError('Configure an rclone remote first')
    if any(j['origin']!='synthetic' for j in store.jobs()) and not p['allow_clinical_remote']:raise ValueError('Clinical cloud storage is not authorized')
    results=[]
    for a in store.db.execute('SELECT * FROM artifacts WHERE uploaded=0 ORDER BY created_at').fetchall():
        if a['attempts']>=cfg['retry']['max_attempts']:continue
        try:
            file=Path(a['path'])
            if digest_file(file)!=a['sha256']:raise ValueError('Local backup was corrupted')
            dest=remote.rstrip('/')+'/'+file.name
            subprocess.run(['rclone','copyto','--immutable',str(file),dest],check=True,timeout=p['timeout_seconds'],capture_output=True)
            # Download encrypted bytes and verify SHA256. This also works for remotes without hash support.
            r=subprocess.run(['rclone','cat',dest],check=True,timeout=p['timeout_seconds'],capture_output=True)
            if hashlib.sha256(r.stdout).hexdigest()!=a['sha256']:raise ValueError('Remote upload verification failed')
            with store.db:store.db.execute('UPDATE artifacts SET uploaded=1,error=NULL WHERE id=?',(a['id'],))
            results.append({'artifact':a['id'],'status':'verified'})
        except Exception as e:
            with store.db:store.db.execute('UPDATE artifacts SET attempts=attempts+1,error=? WHERE id=?',(type(e).__name__,a['id']))
            results.append({'artifact':a['id'],'status':'failed','error':type(e).__name__})
    return results

def cleanup(store,cfg,apply=False):
    p=cfg['retention']
    if apply and not p['enabled']:raise ValueError('Retention deletion is disabled in configuration')
    results=[]
    with lock(store.root):
        backups=store.db.execute('SELECT * FROM artifacts WHERE uploaded=1' if p['require_remote'] else 'SELECT * FROM artifacts').fetchall()
        for j in store.jobs():
            if j['stage']!='done' or j['cleaned']:continue
            from datetime import datetime,timezone
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(j['completed_at'].replace('Z','+00:00'))).total_seconds()/86400
            if age<p['days']:continue
            if not any(j['id'] in json.loads(a['applied_ids']) and Path(a['path']).is_file() and digest_file(Path(a['path']))==a['sha256'] for a in backups):continue
            if (store.root/'quarantine'/f"{j['id']}-questions.json").exists():continue
            paths=[store.root/'inputs'/f"{j['id']}{'.wav' if j['source_kind']=='audio' else '.json'}",store.root/'transcripts'/f"{j['id']}.json",store.root/'extractions'/f"{j['id']}.json",store.root/'extractions'/j['id']]
            if any(path.is_symlink() or store.root not in path.resolve().parents for path in paths):raise ValueError('Unsafe retention target')
            results.append(j['id'])
            if apply:
                for path in paths:
                    if path.is_dir():shutil.rmtree(path)
                    else:path.unlink(missing_ok=True)
                store.update(j['id'],cleaned=1)
    return results


def backup_if_changed(store,keyfile,destination):
    # Timer polling must not produce another full backup every two minutes when nothing changed.
    with lock(store.root):
        root=materialize(store)
        if root is None:return None
        content_hash=load_json(root/'manifest.json')['contentHash']
        for a in store.db.execute('SELECT * FROM artifacts WHERE snapshot_hash=? ORDER BY created_at DESC',(content_hash,)):
            if Path(a['path']).is_file() and digest_file(Path(a['path']))==a['sha256']:return Path(a['path'])
    return create_backup(store,keyfile,destination)


def retry_upload(store,id):
    if not store.db.execute('SELECT 1 FROM artifacts WHERE id=?',(id,)).fetchone():raise ValueError('Unknown backup artifact')
    with store.db:store.db.execute('UPDATE artifacts SET attempts=0,error=NULL WHERE id=?',(id,))
