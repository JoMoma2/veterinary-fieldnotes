"""One safe recorder poll. systemd repeats it; existing per-file checkpoints do the work."""
from __future__ import annotations
import contextlib, hashlib, json, os, signal, subprocess, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from . import automation, backup
from .github import sync_pending_master
from .library import current
from .morning import report
from .private import private_path
from .publication import review_template
from .runner import run
from .util import load_json, write_json, now, lock


def validate(cfg):
    r = cfg['retention']
    if r['enabled'] or r['automatic_deletion'] or not r['retain_source_audio'] or not r['retain_transcripts']:
        raise ValueError('Initial unattended deployment requires all audio/transcript preservation locks')
    u = cfg['usb']
    simulation = cfg['unattended']['simulation_root']
    if simulation:
        private_path(simulation)
        if u['origin'] != 'synthetic':
            raise ValueError('Simulated devices accept synthetic origin only')
    elif not (u['device_uuid'] or u['device_serial']):
        raise ValueError('Register an exact USB filesystem UUID/serial before unattended use')
    if not u['authorization_ref']:
        raise ValueError('Recording/local-processing authorization reference is required')
    p = cfg['provider']
    if p['extraction_protocol'] != 'grounded-v2':
        raise ValueError('Use the source-validated grounded-v2 extraction protocol')
    endpoint = urlparse(p['base_url'])
    if p['kind'] != 'ollama' or endpoint.hostname not in ['localhost', '127.0.0.1', '::1'] or endpoint.port != 11434 or endpoint.path not in ['', '/'] or endpoint.username or endpoint.query:
        raise ValueError('Unattended processing requires local Ollama, not a proxy or external inference')
    if cfg['transcription']['kind'] not in ['whisper-cpp', 'parakeet'] or cfg['transcription']['allow_model_download']:
        raise ValueError('Select installed local ASR weights; automatic downloads are forbidden')


def resource_gate(cfg, stage='transcribe'):
    from .resources import check_resources
    check_resources(cfg, stage)


@contextlib.contextmanager
def sleep_inhibitor(enabled):
    proc = None
    active = False
    if enabled:
        try:
            proc = subprocess.Popen(['systemd-inhibit', '--what=idle:sleep', '--mode=block',
                '--who=Veterinary Fieldnotes', '--why=Processing retained recorder copies',
                'sleep', 'infinity'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            time.sleep(0.1)
            active = proc.poll() is None
        except OSError:
            pass
    try:
        yield active
    finally:
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()


def cycle(store, cfg):
    validate(cfg)
    private_path(store.root)
    folder = store.root / 'unattended'
    with lock(folder):
        # The publisher owns this guard for privacy inference AND deployment.
        # Yield before discovery, model calls or report changes when it is busy.
        publication = store.root / 'publication'
        if (publication / 'pipeline.lock').exists():
            try:
                with lock(publication):
                    pass
            except RuntimeError:
                return {'imports': [], 'processing': [{'status': 'deferred',
                    'stage': 'publication', 'reason': 'Automatic publication is running'}],
                    'sourcePreservation': True,
                    'incomplete': sum(j['stage'] != 'done' for j in store.jobs())}
        state_path = folder / 'state.json'
        state = load_json(state_path) if state_path.exists() else {}
        state['lastPoll'] = now()
        before = {a['id']: a['body'] for a in current(store)['articles']}
        result = {'imports': [], 'processing': [], 'sourcePreservation': True}
        started = time.monotonic()
        try:
            sim = cfg['unattended']['simulation_root']
            if sim:
                sources = [Path(sim)] if Path(sim).is_dir() else []
            else:
                try:
                    sources = automation.discover(cfg)
                except Exception as error:
                    sources = []
                    result['discoveryError'] = type(error).__name__
            identity = hashlib.sha256((sim or cfg['usb']['device_uuid'] or cfg['usb']['device_serial']).encode()).hexdigest()[:10]
            local = datetime.now(ZoneInfo(cfg['unattended']['timezone']))
            session = state.get('pendingSession') or state.get('session', {})
            if sources and (not session or time.time() - session['started'] > cfg['unattended']['session_hours'] * 3600):
                session = {'started': time.time(), 'date': local.date().isoformat(),
                           'id': 's-' + local.strftime('%Y-%m-%d-%H%M%S') + '-' + identity}
                session['articlesBefore'] = {key: hashlib.sha256(body.encode()).hexdigest() for key, body in before.items()}
            if sources:
                state['pendingSession'] = session
                write_json(state_path, state)
            for source in sources:
                try:
                    result['imports'] += automation.scan(store, cfg, source, session['date'], session['id'], observed_stability=True)
                except Exception as error:
                    result['imports'].append({'status': 'failed', 'error': type(error).__name__})
            if any(x.get('imported') for x in result['imports']):
                session['recordingIds'] = list(dict.fromkeys(session.get('recordingIds', []) + [x['id'] for x in result['imports'] if x.get('imported')]))
                state['session'] = session
            state.pop('pendingSession', None)
            state['lastDiscovery'] = {'filesSeen': len(result['imports']),
                'waitingStable': sum(x.get('status') == 'waiting-stable' for x in result['imports'])}
            write_json(state_path, state)
            due = any(j['stage'] in ['transcribe', 'extract', 'commit'] and j['attempts'] < cfg['retry']['max_attempts'] and j['retry_after'] <= time.time() for j in store.jobs())
            def stage_gate(job, stage):
                state['activeRun'] = {'at': now(), 'recordingId': job['id'], 'stage': stage}
                write_json(state_path, state)
                report(store, cfg, state)
                resource_gate(cfg, stage=stage)
            with sleep_inhibitor(cfg['unattended']['inhibit_sleep'] and due) as inhibited:
                result['sleepInhibited'] = inhibited
                result['processing'] = run(store, cfg, before_stage=stage_gate)
                if cfg['github']['enabled']:
                    state['masterSync'] = result['master_sync'] = sync_pending_master(store, cfg)
                if cfg['backup']['remote']:
                    try:
                        with lock(store.root):
                            result['uploads'] = backup.upload_backups(store, cfg)
                    except Exception as error:
                        result['backup_error'] = type(error).__name__
            after = current(store)
            result['articlesCreated'] = sum(a['id'] not in before for a in after['articles'])
            result['articlesUpdated'] = sum(a['id'] in before and before[a['id']] != a['body'] for a in after['articles'])
            result['discovered'] = len(result['imports'])
            result['newImports'] = sum(x.get('imported', False) for x in result['imports'])
            result['seconds'] = round(time.monotonic() - started, 3)
            if result['newImports'] or result['processing'] or any(x.get('status') == 'failed' for x in result['imports']) or result.get('discoveryError'):
                state['lastWork'] = {'at': now(), **result}
        except BaseException as error:
            result['seconds'] = round(time.monotonic() - started, 3)
            state['lastWork'] = {'at': now(), 'interrupted': type(error).__name__, **result}
            raise
        finally:
            state.pop('activeRun', None)
            write_json(state_path, state)
            with (folder / 'events.jsonl').open('a') as log:
                log.write(json.dumps({'at': now(), 'seconds': round(time.monotonic() - started, 3),
                                      'imports': len(result['imports']), 'processing': result['processing'],
                                      'masterSync': state.get('masterSync', {})}) + '\n')
                log.flush()
                os.fsync(log.fileno())
            with lock(store.root):
                review_template(store, store.root / 'review/publication-candidates.json')
                result['summary'] = report(store, cfg, state)
        result['report'] = str(store.root / 'review/index.html')
        result['incomplete'] = sum(j['stage'] != 'done' for j in store.jobs())
        return result
