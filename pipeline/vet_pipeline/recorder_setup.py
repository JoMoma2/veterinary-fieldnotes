"""Owner configuration and desktop registration; never writes recorder media."""
from __future__ import annotations
import getpass, hashlib, json, os, shutil, subprocess
from pathlib import Path
from .automation import inventory
from .config import config
from .private import private_path
from .util import REPO, atomic_write, load_json

LIVE = Path.home() / '.local/share/vet-fieldnotes-live'
CONFIG = Path.home() / '.config/vet-fieldnotes/pipeline.toml'
PROOF = Path.home() / '.local/share/vet-fieldnotes-setup/synthetic-test.json'


def core_fingerprint():
    h = hashlib.sha256()
    for name in ['automation', 'unattended', 'resources', 'ingest', 'audio_prepare', 'audio_filter', 'asr_quality', 'runner', 'morning', 'config', 'backup', 'whisper_cpp', 'grounded', 'github']:
        h.update((REPO / 'pipeline/vet_pipeline' / (name + '.py')).read_bytes())
    return h.hexdigest()


def save_config(path, cfg):
    lines = []
    for section, values in cfg.items():
        lines.append('[' + section + ']')
        for key, value in values.items():
            if value is not None:
                lines.append(key + ' = ' + json.dumps(value, ensure_ascii=False))
        lines.append('')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(path, '\n'.join(lines))
    path.chmod(0o600)


def stage():
    os.umask(0o077)
    private_path(LIVE)
    LIVE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not CONFIG.exists():
        cfg = config(REPO / 'config/benchmarks/local-vulkan.example.toml')
        cfg['github'].update(enabled=True, checkout=str(Path.home() / 'vet-knowledge-master'), allow_clinical=False)
        cfg['usb'].update(roots=[f'/media/{getpass.getuser()}', f'/run/media/{getpass.getuser()}'], automount_read_only=True)
        save_config(CONFIG, cfg)
    units = Path.home() / '.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    for name in ['vet-fieldnotes.service', 'vet-fieldnotes.timer']:
        target = units / name
        source = (REPO / 'automation' / name).read_text()
        if target.exists() and target.read_text() != source:
            raise ValueError('Existing Fieldnotes unit differs; review it rather than overwriting owner settings')
        atomic_write(target, source)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    apps = Path.home() / '.local/share/applications'
    apps.mkdir(parents=True, exist_ok=True)
    python = REPO / 'pipeline/.venv/bin/python'
    register = f'"{python}" "{REPO / "scripts/register-recorder.py"}"'
    atomic_write(apps / 'vet-fieldnotes-register.desktop', '[Desktop Entry]\nType=Application\nName=Fieldnotes — Register Recorder\nComment=Register only your USB recorder and activate safe retained-source processing\nExec=' + register + '\nIcon=audio-input-microphone\nTerminal=false\nCategories=Education;\n')
    # xdg-open remains local; there is no listening web service.
    atomic_write(apps / 'vet-fieldnotes-review.desktop', '[Desktop Entry]\nType=Application\nName=Fieldnotes — Morning Review\nExec=xdg-open ' + str(LIVE / 'review/index.html') + '\nIcon=accessories-text-editor\nTerminal=false\nCategories=Education;\n')
    from .store import Store
    from .morning import report
    from .publication import review_template
    store = Store(LIVE)
    try:
        review_template(store, LIVE / 'review/publication-candidates.json')
        report(store, config(CONFIG), {})
    finally:
        store.close()
    return {'configuration': str(CONFIG), 'workspace': str(LIVE), 'units': 'staged; not enabled by this command'}


def register(mount, authorization_ref, activate=False, storage_ref=''):
    mount = Path(mount).resolve()
    matches = [d for d in inventory() if d.get('uuid') and str(mount) in (d.get('mountpoints') or [])]
    if len(matches) != 1 or not authorization_ref.strip():
        raise ValueError('Select one mounted USB filesystem with a UUID and local recording/processing authorization reference')
    device = matches[0]
    cfg = config(CONFIG)
    if cfg['unattended']['simulation_root']:
        raise ValueError('Production registration must not use a simulation configuration')
    cfg['usb'].update(device_uuid=device['uuid'], device_serial=device.get('serial') or '',
                      device_label=device.get('label') or '', origin='authorized-record',
                      authorization_ref=authorization_ref, automount_read_only=True)
    cfg['github']['allow_clinical'] = bool(storage_ref.strip())
    cfg['backup']['allow_clinical_remote'] = bool(storage_ref.strip())
    if storage_ref.strip():
        cfg['github'].update(enabled=True, checkout=cfg['github']['checkout'] or str(Path.home() / 'vet-knowledge-master'))
    if not any(mount == Path(p).resolve() or Path(p).resolve() in mount.parents for p in cfg['usb']['roots']):
        cfg['usb']['roots'].append(str(mount.parent))
    from .unattended import validate
    validate(cfg)
    if activate:
        if not PROOF.exists() or load_json(PROOF).get('status') != 'passed' or load_json(PROOF).get('coreSha256') != core_fingerprint():
            raise ValueError('This code revision needs its synthetic unattended test before activation')
        # Stop our own poll/worker before changing device or storage permission;
        # an existing worker must not keep using the old authorization snapshot.
        subprocess.run(['systemctl', '--user', 'stop', 'vet-fieldnotes.timer', 'vet-fieldnotes.service'], check=True)
    if storage_ref.strip():
        from .util import write_json, now
        write_json(CONFIG.with_name('github-storage-authorization.json'),
                   {'authorizationRef': storage_ref, 'scope': 'private GitHub extracted knowledge only; no audio/transcript files or public publication', 'recordedAt': now()})
    save_config(CONFIG, cfg)
    if activate:
        subprocess.run(['systemctl', '--user', 'enable', '--now', 'vet-fieldnotes.timer'], check=True)
        subprocess.run(['systemctl', '--user', 'start', '--no-block', 'vet-fieldnotes.service'], check=True)
    return {'uuid': device['uuid'], 'serialMatched': bool(device.get('serial')), 'activated': activate,
            'clinicalCloudUpload': cfg['github']['allow_clinical'] and cfg['backup']['allow_clinical_remote']}


def dialog(args):
    p = subprocess.run(['zenity', *args], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(0)
    return p.stdout.strip()


def gui():
    if not shutil.which('zenity'):
        raise ValueError('Zenity is unavailable; use the documented register-recorder.py --mount command')
    devices = [(d, m) for d in inventory() if d.get('uuid') for m in (d.get('mountpoints') or []) if m]
    if not devices:
        dialog(['--info', '--title=Fieldnotes Recorder', '--text=No mounted USB recorder found. Connect it, open it in Files if needed, then launch Register Recorder again. No service has been activated.'])
        return
    rows = []
    for i, (d, m) in enumerate(devices):
        rows += [str(i), d.get('label') or d.get('model') or 'USB filesystem', d['uuid'], str(m)]
    selected = dialog(['--list', '--title=Select your audio recorder', '--column=Number', '--column=Device', '--column=Filesystem UUID', '--column=Mount', '--print-column=1', *rows])
    d, mount = devices[int(selected)]
    dialog(['--question', '--title=Register and activate Fieldnotes?', '--text=Register this USB filesystem only?\nUUID: ' + d['uuid'] + '\nSerial: ' + str(d.get('serial') or 'unavailable') + '\nMount: ' + mount + '\n\nRecordings and transcripts will stay private and retained. Private GitHub storage requires a separate authorization choice. Public publication is not enabled. Processing requires your workplace recording/local-processing authorization.'])
    ref = dialog(['--entry', '--title=Local processing authorization', '--text=Enter your recording/local-processing authorization reference (no patient details or credentials). This does not authorize GitHub storage or public publication.'])
    cloud = subprocess.run(['zenity', '--question', '--default-cancel', '--title=Separate private GitHub storage permission',
        '--ok-label=I have storage authorization', '--cancel-label=Keep local only',
        '--text=Do you have explicit authorization to store extracted knowledge, detailed case accounts and source quotations in the private GitHub repository?\n\nRecording permission alone is insufficient. Choose Keep local only unless this separate storage permission is established. No audio or transcript files are uploaded. Public publication remains separately reviewed.'])
    storage_ref = dialog(['--entry', '--title=Private GitHub storage authorization', '--text=Enter the separate private GitHub storage authorization reference (no patient details).']) if cloud.returncode == 0 else ''
    result = register(mount, ref, activate=True, storage_ref=storage_ref)
    dialog(['--info', '--title=Fieldnotes activated', '--text=Registered and started. Keep Ubuntu signed in (locking the screen is fine). Open Fieldnotes — Morning Review to inspect progress. Originals, transcripts and extraction checkpoints remain retained.\n\nPrivate GitHub storage: ' + ('enabled by your separate authorization.' if result['clinicalCloudUpload'] else 'awaiting separate authorization; local processing continues.')])
    return result
