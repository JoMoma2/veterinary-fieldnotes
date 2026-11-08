"""Real-model synthetic USB/timer/recovery test. No production service activation.

The source manifest MUST be synthetic. --sync-private permits only synthetic
permanent library updates to the existing private master. Never uploads audio.
"""
import argparse, array, json, os, shutil, subprocess, time, wave
from pathlib import Path
from vet_pipeline.config import config
from vet_pipeline.locations import location
from vet_pipeline.recorder_setup import save_config, core_fingerprint, PROOF
from vet_pipeline.private import initialize_private
from vet_pipeline.recovery import recover_library
from vet_pipeline.library import current, read_library
from vet_pipeline.store import Store
from vet_pipeline.util import REPO, load_json, write_json, digest_file

p = argparse.ArgumentParser()
p.add_argument('--audio-directory', type=Path, required=True)
p.add_argument('--directory', type=Path, required=True)
p.add_argument('--master-checkout', type=Path, default=location('repositories', 'master'))
p.add_argument('--sync-private', action='store_true')
a = p.parse_args()
os.umask(0o077)
if load_json(a.audio_directory / 'manifest.json').get('origin') != 'synthetic':
    raise SystemExit('Synthetic audio manifest required')
root = initialize_private(a.directory)
workspace = root / 'workspace'
detached, attached = root / 'USB-DETACHED', root / 'USB-ATTACHED'
detached.mkdir()
source_hashes = {}
for i, name in enumerate(['01-first.wav', '02-followup.wav', '03-workaround.wav', '07-known-outcome.wav']):
    with wave.open(str(a.audio_directory / name), 'rb') as src:
        params = src.getparams(); frames = src.readframes(src.getnframes())
    if params.nchannels != 1 or params.sampwidth != 2:
        raise SystemExit('This synthetic source needs mono PCM16 fixtures')
    if i == 2:
        samples = array.array('h', frames)
        frames = array.array('h', (x for value in samples for x in [value] * 4)).tobytes()
        channels, rate = 2, params.framerate * 2
    else:
        channels, rate = 1, params.framerate
    tail = int(time.time_ns() % 3000) + 500
    frames += b'\0' * tail * channels * 2
    target = detached / name
    with wave.open(str(target), 'wb') as dst:
        dst.setnchannels(channels); dst.setsampwidth(2); dst.setframerate(rate); dst.writeframes(frames)
    stamp = time.time() + 365 * 86400 if i == 2 else time.time() - 100
    os.utime(target, (stamp, stamp))  # A recorder with a wrong future clock must not stall.
    source_hashes[name] = {'sha256': digest_file(target), 'mtimeNs': target.stat().st_mtime_ns}

cfg = config(REPO / 'config/benchmarks/local-vulkan.example.toml')
cfg['usb'].update(origin='synthetic', authorization_ref='synthetic-unattended-timer-test', stable_seconds=1)
cfg['unattended']['simulation_root'] = str(attached)
cfg['github']['enabled'] = False
store = Store(workspace)
try:
    if a.sync_private:
        if (a.master_checkout / 'production-storage.json').exists():
            raise SystemExit('Master reserved for live knowledge; omit --sync-private or select a separate synthetic master checkout')
        remote = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=a.master_checkout, text=True).strip()
        clone = root / 'private-master'
        subprocess.run(['git', 'clone', remote, str(clone)], check=True, capture_output=True)
        if (clone / 'production-storage.json').exists():
            raise SystemExit('This master is reserved for real knowledge; use a separate synthetic private repository or omit --sync-private')
        lib = read_library(clone / 'archive')
        if any(v['origin'] != 'synthetic' for k, values in lib.items() if k != 'topics' for v in values):
            raise SystemExit('Private master is no longer synthetic-only; use a separate authorized synthetic repository')
        recover_library(store, clone / 'archive')
        subprocess.run(['git', 'config', 'user.name', 'Fieldnotes Synthetic Automation'], cwd=clone, check=True)
        subprocess.run(['git', 'config', 'user.email', 'synthetic@example.invalid'], cwd=clone, check=True)
        cfg['github']['checkout'] = str(clone)
    baseline = {k: len(v) for k, v in current(store).items()}
finally:
    store.close()
conf = root / 'synthetic.toml'
save_config(conf, cfg)
unit = 'vet-fieldnotes-synthetic-' + str(os.getpid())
units = Path.home() / '.config/systemd/user'
units.mkdir(parents=True, exist_ok=True)
service, timer = units / (unit + '.service'), units / (unit + '.timer')
python_cli = REPO / 'pipeline/.venv/bin/vet-pipeline'
service.write_text(f'''[Unit]
Description=Isolated synthetic Fieldnotes USB simulation
[Service]
Type=oneshot
UMask=0077
WorkingDirectory={REPO}
ExecStart={python_cli} --workspace {workspace} --config {conf} unattended
TimeoutStartSec=infinity
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={root}
''')
timer.write_text(f'[Timer]\nOnActiveSec=1s\nOnUnitInactiveSec=5s\nAccuracySec=1s\nUnit={unit}.service\n')

def system(*args):
    return subprocess.run(['systemctl', '--user', *args], check=True, capture_output=True, text=True)

def wait(predicate, seconds=600):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.2)
    raise TimeoutError('Synthetic unit did not reach expected state; retained artifacts and journal explain why')

def jobs():
    s = Store(workspace)
    try:
        return [dict(j) for j in s.jobs() if j['source_kind'] == 'audio']
    finally:
        s.close()

def state():
    path = workspace / 'unattended/state.json'
    return load_json(path) if path.exists() else {}

def idle():
    return system('show', unit + '.service', '-p', 'ActiveState', '--value').stdout.strip() in ['inactive', 'failed']

started = time.monotonic()
try:
    system('daemon-reload')
    system('start', unit + '.timer')
    wait(lambda: bool(state().get('lastPoll')), 30)
    if jobs():
        raise RuntimeError('Device was imported before simulated attachment')
    detached.rename(attached)  # Simulated plug, no direct pipeline command.
    wait(lambda: len(jobs()) == 4 and sum(j['stage'] == 'done' for j in jobs()) >= 1 and any(j['stage'] != 'done' and (workspace / 'transcripts' / (j['id'] + '.json')).exists() for j in jobs()))
    retained = {}
    for j in jobs():
        for f in [workspace / 'transcripts' / (j['id'] + '.json'), workspace / 'extractions' / (j['id'] + '.json')]:
            if f.exists(): retained[str(f.relative_to(workspace))] = digest_file(f)
    system('kill', '--signal=SIGINT', '--kill-whom=all', unit + '.service')
    wait(lambda: len(jobs()) == 4 and all(j['stage'] == 'done' for j in jobs()))
    system('stop', unit + '.timer')
    wait(idle, 30)
    if any(digest_file(workspace / f) != sha for f, sha in retained.items()):
        raise RuntimeError('Completed checkpoint changed across interruption')
    count = len(jobs())
    attached.rename(detached)
    previous = state()['lastPoll']
    system('start', unit + '.timer')
    wait(lambda: state().get('lastPoll') != previous, 30)
    attached_before = state()['lastPoll']
    detached.rename(attached)
    wait(lambda: state().get('lastPoll') != attached_before, 30)
    system('stop', unit + '.timer')
    wait(idle, 30)
    if len(jobs()) != count:
        raise RuntimeError('Reconnection duplicated jobs')
    if a.sync_private:
        cfg['github']['enabled'] = True
        save_config(conf, cfg)
        system('start', unit + '.timer')
        wait(lambda: bool(state().get('masterSync')), 150)
        system('stop', unit + '.timer')
        wait(idle, 30)
    for name, expected in source_hashes.items():
        if digest_file(attached / name) != expected['sha256'] or (attached / name).stat().st_mtime_ns != expected['mtimeNs']:
            raise RuntimeError('Simulated source was modified')
    for j in jobs():
        if digest_file(workspace / 'inputs' / (j['id'] + '.wav')) != j['sha256']:
            raise RuntimeError('Imported original changed')
        if not (workspace / 'transcripts' / (j['id'] + '.json')).exists():
            raise RuntimeError('Transcript not retained')
    s = Store(workspace)
    try: library = current(s)
    finally: s.close()
    summary = load_json(workspace / 'review/summary.json')
    candidates = load_json(workspace / 'review/publication-candidates.json')
    if any(e['approved'] for e in candidates['entries']):
        raise RuntimeError('Candidates were automatically approved')
    result = {'status': 'passed', 'coreSha256': core_fingerprint(), 'origin': 'synthetic',
              'systemdTimer': True, 'simulatedUSBOnly': True, 'recordings': 4,
              'interruptedAndResumed': True, 'savedCheckpointHashesUnchanged': len(retained),
              'reconnectionDeduplicated': True, 'originalsAndTranscriptsRetained': True,
              'normalizedStereoCopy': bool(list((workspace / 'normalized').glob('*.wav'))),
              'futureRecorderTimestampHandled': True,
              'newRecordCounts': {k: len(v) - baseline[k] for k, v in library.items()},
              'masterSync': summary['masterSync'], 'secondsIncludingTimerWaits': round(time.monotonic() - started, 3),
              'morningReport': str(workspace / 'review/index.html')}
    write_json(root / 'result.json', result)
    write_json(PROOF, result)
    print(json.dumps(result, indent=2))
finally:
    subprocess.run(['systemctl', '--user', 'stop', unit + '.timer', unit + '.service'], capture_output=True)
    subprocess.run(['journalctl', '--user', '-u', unit + '.service', '--no-pager', '-n', '1000', '-o', 'cat'], stdout=(root / 'systemd-journal.log').open('w'))
    service.unlink(missing_ok=True); timer.unlink(missing_ok=True)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
