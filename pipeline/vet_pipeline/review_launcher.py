"""Open a healthy read-only review using the desktop browser; no inference."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import httpx
from .locations import location
from .private import private_path
from .review_server import saved_endpoint
from .util import now


def selection():
    workspace=location('data','library');unit='vet-fieldnotes-review.service'
    config=location('config','active-review.json')
    if config.exists():
        selected=json.loads(config.read_text())
        workspace=private_path(selected['workspace']);unit=selected['unit']
    if not re.fullmatch(r'vet-fieldnotes-[a-z0-9-]*review[a-z0-9-]*[.]service',unit):
        raise ValueError('Expected a FieldNotes read-only review unit')
    return private_path(workspace),unit


def ready_url(workspace,timeout=20):
    """A persistent state file is not evidence that its server is ready."""
    deadline=time.monotonic()+timeout
    with httpx.Client(timeout=1,trust_env=False,follow_redirects=False) as client:
        while True:
            try:
                token,port=saved_endpoint(workspace)
                url=f'http://127.0.0.1:{port}/{token}/review/index.html'
                response=client.head(url)
                if response.status_code==200 and response.headers.get('content-type','').startswith('text/html'):
                    return url
            except (OSError,ValueError,KeyError,httpx.HTTPError):
                pass
            if time.monotonic()>=deadline:raise TimeoutError('Private review did not become ready')
            time.sleep(.2)


def open_browser(url):
    """Use the GNOME/default-browser dispatcher rather than Python browser guesses."""
    for command in [('gio',['open']),('xdg-open',[])]:
        executable=shutil.which(command[0])
        if not executable:continue
        try:
            subprocess.run([executable,*command[1],url],check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            return command[0]
        except (OSError,subprocess.SubprocessError):continue
    raise RuntimeError('Desktop browser could not be opened')


def log(stage,error=None,backend=None):
    path=location('maintenance','launchers','morning-review.log')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open('a') as f:
        f.write(json.dumps({'at':now(),'stage':stage,'errorClass':type(error).__name__ if error else None,'backend':backend})+'\n')
    path.chmod(0o600)  # Never log capability URLs, private report content or browser stderr.


def notify_failure():
    text='FieldNotes could not open Morning Review. Processing has not been stopped. Details: ~/FieldNotes/maintenance/launchers/morning-review.log'
    if shutil.which('zenity'):
        subprocess.Popen(['zenity','--error','--title=FieldNotes Morning Review','--text='+text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    elif shutil.which('notify-send'):
        subprocess.Popen(['notify-send','FieldNotes Morning Review',text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def main():
    os.umask(0o077);stage='selection'
    try:
        log('launch-requested')
        workspace,unit=selection();stage='viewer-start';log(stage)
        subprocess.run(['systemctl','--user','start',unit],check=True,capture_output=True,timeout=20)
        stage='viewer-ready';log(stage);url=ready_url(workspace)
        stage='browser-open';log(stage);backend=open_browser(url)
        log('browser-requested',backend=backend)
        return 0
    except Exception as error:
        try:log(stage,error)
        except OSError:pass
        try:notify_failure()
        except OSError:pass
        return 1
