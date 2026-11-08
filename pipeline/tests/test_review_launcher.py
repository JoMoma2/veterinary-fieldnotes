import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from vet_pipeline import review_launcher as l
from vet_pipeline.util import write_json


def test_selection_accepts_only_review_units_and_private_workspaces(tmp_path,monkeypatch):
    monkeypatch.setenv('FIELDNOTES_HOME',str(tmp_path/'hub'))
    write_json(tmp_path/'hub/config/active-review.json',{'workspace':str(tmp_path/'private'),'unit':'vet-fieldnotes-full-context-review-20000101.service'})
    assert l.selection()==(tmp_path/'private','vet-fieldnotes-full-context-review-20000101.service')
    write_json(tmp_path/'hub/config/active-review.json',{'workspace':str(tmp_path/'private'),'unit':'vet-fieldnotes.service'})
    with pytest.raises(ValueError):l.selection()


def test_saved_url_is_not_opened_until_http_ready(tmp_path,monkeypatch):
    write_json(tmp_path/'review-server.json',{'url':'http://127.0.0.1:52139/'+'a'*43+'/review/index.html','loopbackOnly':True})
    responses=iter([503,200]);requested=[]
    class Client:
        def __init__(self,**kw):assert kw['trust_env'] is False
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def head(self,url):requested.append(url);return SimpleNamespace(status_code=next(responses),headers={'content-type':'text/html'})
    monkeypatch.setattr(l.httpx,'Client',Client);monkeypatch.setattr(l.time,'sleep',lambda *a:None)
    assert l.ready_url(tmp_path).startswith('http://127.0.0.1:52139/')
    assert len(requested)==2


def test_desktop_dispatch_and_failure_are_observable(tmp_path,monkeypatch):
    monkeypatch.setenv('FIELDNOTES_HOME',str(tmp_path))
    calls=[];notices=[]
    monkeypatch.setattr(l,'selection',lambda:(tmp_path,'vet-fieldnotes-review.service'))
    monkeypatch.setattr(l,'ready_url',lambda p:'http://127.0.0.1:1/private-not-logged')
    monkeypatch.setattr(l.shutil,'which',lambda name:'/usr/bin/'+name)
    monkeypatch.setattr(l.subprocess,'run',lambda args,**kw:calls.append(args))
    assert l.main()==0
    assert calls[0]==['systemctl','--user','start','vet-fieldnotes-review.service']
    assert calls[1][0:2]==['/usr/bin/gio','open']
    log=(tmp_path/'maintenance/launchers/morning-review.log').read_text()
    assert 'browser-requested' in log and 'private-not-logged' not in log
    monkeypatch.setattr(l,'ready_url',lambda p:(_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(l,'notify_failure',lambda:notices.append(1))
    assert l.main()==1 and notices
    assert 'TimeoutError' in (tmp_path/'maintenance/launchers/morning-review.log').read_text()


def test_browser_child_inheriting_output_does_not_delay_dispatch(tmp_path,monkeypatch):
    import os
    import signal
    import time
    pidfile=tmp_path/'child.pid'
    gio=tmp_path/'gio'
    gio.write_text('#!/bin/sh\nsleep 30 &\necho $! > "'+str(pidfile)+'"\nexit 0\n')
    gio.chmod(0o700)
    monkeypatch.setattr(l.shutil,'which',lambda command:str(gio) if command=='gio' else None)
    start=time.monotonic()
    try:
        assert l.open_browser('http://127.0.0.1:1/not-a-real-report')=='gio'
        assert time.monotonic()-start<5
    finally:
        if pidfile.exists():
            try:os.kill(int(pidfile.read_text()),signal.SIGTERM)
            except ProcessLookupError:pass
