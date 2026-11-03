import json, os, time, types, wave
from pathlib import Path
import pytest
from vet_pipeline.config import config
from vet_pipeline.ingest import ingest
from vet_pipeline.util import REPO, digest_file, load_json
from vet_pipeline.unattended import cycle
from vet_pipeline.runner import ProcessingDeferred


def setup(cfg, tmp_path, monkeypatch):
    pytest.importorskip('av')
    usb = tmp_path / 'recorder'
    usb.mkdir()
    wav = usb / 'Original recording.WAV'
    with wave.open(str(wav), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(b'\0' * 16000 * 2 * 60)
    os.utime(wav, (time.time() - 100, time.time() - 100))
    # The mocked model returns a complete fixture; keep it in one source chunk.
    cfg['provider'].update(kind='ollama', model='qwen3:30b', context_window=32768)
    cfg['transcription']['kind'] = 'whisper-cpp'
    cfg['usb'].update(origin='synthetic', authorization_ref='synthetic-test')
    cfg['unattended'].update(simulation_root=str(usb), inhibit_sleep=False)
    # Timer tests below advance the observation clock instead of sleeping30s.
    from vet_pipeline.util import write_json
    write_json(tmp_path / 'private/usb-observations.json',
               {str(wav.resolve()): {'signature': [wav.stat().st_size, wav.stat().st_mtime_ns], 'since': time.time() - 100}})
    monkeypatch.setattr('vet_pipeline.unattended.resource_gate', lambda c: None)
    monkeypatch.setattr('vet_pipeline.runner.transcribe', fake_transcribe)
    monkeypatch.setattr('vet_pipeline.extraction.planned_chunks', lambda store, job, t, cfg, context: [t])
    monkeypatch.setattr('vet_pipeline.extraction.Provider.extract', lambda *a: load_json(REPO / 'fixtures/pipeline/responses/first.json'))
    return usb, wav


def fake_transcribe(store, job, cfg):
    from vet_pipeline.util import write_json
    t = load_json(REPO / 'fixtures/pipeline/transcripts/01-first.json')
    write_json(store.root / 'transcripts' / (job['id'] + '.json'), t)
    return t


def test_timer_cycle_retains_media_and_reports_then_deduplicates_reconnection(store, cfg, tmp_path, monkeypatch):
    usb, wav = setup(cfg, tmp_path, monkeypatch)
    before = digest_file(wav)
    result = cycle(store, cfg)
    assert result['newImports'] == 1 and result['incomplete'] == 0
    j = store.jobs()[0]
    assert digest_file(store.root / 'inputs' / (j['id'] + '.wav')) == before == digest_file(wav)
    assert (store.root / 'transcripts' / (j['id'] + '.json')).exists()
    assert (store.root / 'retained' / j['shift_id'] / (j['id'] + '-' + wav.name)).exists()
    assert result['summary']['audioSeconds'] == 60
    assert result['articlesCreated'] == 3
    assert '<audio controls' in (store.root / 'review/recordings' / (j['id'] + '.html')).read_text()
    candidates = load_json(store.root / 'review/publication-candidates.json')
    assert candidates['entries'] and all(not e['approved'] for e in candidates['entries'])
    usb.rename(tmp_path / 'removed')
    assert not cycle(store, cfg)['imports']
    (tmp_path / 'removed').rename(usb)
    monkeypatch.setattr('vet_pipeline.runner.transcribe', lambda *a: pytest.fail('retranscribed'))
    resumed = cycle(store, cfg)
    assert resumed['newImports'] == 0 and len(store.jobs()) == 1
    assert digest_file(wav) == before
    old_state = load_json(store.root / 'unattended/state.json')
    old_id = old_state['session']['id']
    old_state['session']['started'] = time.time() - 25 * 3600
    from vet_pipeline.util import write_json
    write_json(store.root / 'unattended/state.json', old_state)
    idle = cycle(store, cfg)
    assert load_json(store.root / 'unattended/state.json')['session']['id'] == old_id
    assert idle['summary']['batchRecordingsImported'] == 1
    assert idle['summary']['batchArticlesCreated'] == 3


def test_busy_gpu_defers_without_consuming_retry_or_losing_audio(store, cfg, tmp_path, monkeypatch):
    usb, wav = setup(cfg, tmp_path, monkeypatch)
    def busy(c):
        assert (store.root / 'review/index.html').exists()
        assert load_json(store.root / 'review/summary.json')['lastObservedStage']['stage'] == 'transcribe'
        raise ProcessingDeferred('shared GPU busy')
    monkeypatch.setattr('vet_pipeline.unattended.resource_gate', busy)
    first = cycle(store, cfg)
    assert first['processing'][0]['status'] == 'deferred'
    assert store.jobs()[0]['attempts'] == 0 and store.jobs()[0]['stage'] == 'transcribe'
    monkeypatch.setattr('vet_pipeline.unattended.resource_gate', lambda c: None)
    assert cycle(store, cfg)['incomplete'] == 0


def test_unclassified_accounts_are_visible_in_private_recording_report(store, cfg, tmp_path, monkeypatch):
    setup(cfg, tmp_path, monkeypatch)
    from vet_pipeline.grounded import project
    from vet_pipeline.extraction import KIND
    t = load_json(REPO / 'fixtures/pipeline/transcripts/01-first.json')
    data, _ = project({'discussions': []}, t, [], KIND)
    monkeypatch.setattr('vet_pipeline.extraction.Provider.extract', lambda *a: data)
    out = cycle(store, cfg)
    assert out['summary']['unclassifiedDiscussions'] == 3
    rid = store.jobs()[0]['id']
    text = (store.root / 'review/recordings' / (rid + '.html')).read_text()
    assert 'class="flag"' in text and 'Preserved verbatim' in text


def test_preservation_lock_cannot_be_bypassed_by_legacy_retention_enable(store, cfg):
    from vet_pipeline.backup import cleanup
    cfg['retention']['enabled'] = True
    with pytest.raises(ValueError, match='preservation lock'):
        cleanup(store, cfg, apply=True)
    assert cleanup(store, cfg) == []


def test_uuid_and_inherited_serial_match_only_registered_device(cfg, tmp_path, monkeypatch):
    from vet_pipeline.automation import discover
    cfg['usb'].update(roots=[str(tmp_path)], device_uuid='abc', device_serial='right')
    data = {'blockdevices': [
        {'tran': 'usb', 'serial': 'wrong', 'children': [{'uuid': 'abc', 'mountpoints': [str(tmp_path)]}]},
        {'tran': 'usb', 'serial': 'right', 'children': [{'uuid': 'other', 'mountpoints': [str(tmp_path)]}]},
        {'tran': 'usb', 'serial': 'right', 'children': [{'uuid': 'abc', 'mountpoints': [str(tmp_path)]}]}]}
    monkeypatch.setattr('subprocess.run', lambda *a, **k: types.SimpleNamespace(stdout=json.dumps(data)))
    assert discover(cfg) == [tmp_path]
    cfg['usb']['device_serial'] = 'absent'
    assert discover(cfg) == []


def test_matching_unmounted_volume_is_mounted_read_only(cfg, tmp_path, monkeypatch):
    from vet_pipeline import automation
    cfg['usb'].update(roots=[str(tmp_path)], device_uuid='abc', automount_read_only=True)
    mounted = [False]
    monkeypatch.setattr(automation, 'inventory', lambda: [{'uuid': 'abc', 'name': '/dev/test', 'mountpoints': [str(tmp_path)] if mounted[0] else []}])
    def mount(args, **kw):
        assert args == ['udisksctl', 'mount', '--block-device', '/dev/test', '--options', 'ro', '--no-user-interaction']
        mounted[0] = True
    monkeypatch.setattr('subprocess.run', mount)
    assert automation.discover(cfg) == [tmp_path]


def test_registration_changes_only_private_config_and_cannot_activate_without_test(tmp_path, monkeypatch):
    from vet_pipeline import recorder_setup as r
    p = tmp_path / 'pipeline.toml'
    cfg = config(REPO / 'config/benchmarks/local-vulkan.example.toml')
    r.save_config(p, cfg)
    usb = tmp_path / 'usb'; usb.mkdir()
    monkeypatch.setattr(r, 'CONFIG', p)
    monkeypatch.setattr(r, 'PROOF', tmp_path / 'missing-proof.json')
    monkeypatch.setattr(r, 'inventory', lambda: [{'uuid': 'abc', 'serial': 'serial', 'label': 'REC', 'mountpoints': [str(usb)]}])
    with pytest.raises(ValueError, match='synthetic unattended test'):
        r.register(usb, 'owner-local-processing-authorization', activate=True)
    out = r.register(usb, 'owner-local-processing-authorization')
    updated = config(p)
    assert out['uuid'] == 'abc' and not out['activated']
    assert not list(usb.iterdir())
    assert updated['retention']['retain_source_audio'] and not updated['retention']['automatic_deletion']
    assert not updated['github']['allow_clinical'] and not updated['backup']['allow_clinical_remote']
    r.register(usb, 'local-processing-ref', storage_ref='separately-authorized-github-storage')
    authorized = config(p)
    assert authorized['github']['allow_clinical'] and authorized['backup']['allow_clinical_remote']
    assert not list(usb.iterdir())
    assert (p.parent / 'github-storage-authorization.json').is_file()


def test_nonstandard_wav_uses_separate_verified_copy_and_keeps_full_transcript(store, cfg, tmp_path, monkeypatch):
    pytest.importorskip('av')
    source = tmp_path / 'stereo.WAV'
    with wave.open(str(source), 'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(48000); f.writeframes(b'\0' * 48000 * 4)
    before = digest_file(source)
    rid, _ = ingest(store, source, 's-format', '2000-01-01', 'synthetic', 'test')
    cfg['transcription']['kind'] = 'whisper-cpp'
    from vet_pipeline.ingest import transcribe
    def decode(path, settings):
        assert path.parent.name == 'normalized'
        with wave.open(str(path), 'rb') as f:
            assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (16000, 1, 2)
        return {'segments': [{'start': 0, 'end': 1, 'text': 'Outcome unknown.'}]}
    monkeypatch.setattr('vet_pipeline.whisper_cpp.transcribe_cpp', decode)
    transcribe(store, store.get(rid), cfg)
    assert digest_file(source) == before == digest_file(store.root / 'inputs' / (rid + '.wav'))
    assert (store.root / 'normalized' / (rid + '.wav')).exists()
    assert (store.root / 'transcripts' / (rid + '.json')).exists()


def test_observed_stability_uses_computer_observations_not_recorder_clock(store, cfg, tmp_path, monkeypatch):
    from vet_pipeline.automation import scan
    source = tmp_path / 'future-clock'; source.mkdir()
    wav = source / 'REC.WAV'
    with wave.open(str(wav), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000); f.writeframes(b'\0' * 16000)
    os.utime(wav, (time.time() + 365 * 86400, time.time() + 365 * 86400))
    cfg['usb'].update(origin='synthetic', authorization_ref='test', stable_seconds=30)
    assert scan(store, cfg, source, '2000-01-01', observed_stability=True)[0]['status'] == 'waiting-stable'
    original = time.time()
    monkeypatch.setattr('vet_pipeline.automation.time.time', lambda: original + 31)
    imported = scan(store, cfg, source, '2000-01-01', observed_stability=True)
    assert imported[0]['imported'] and store.jobs()[0]['source_mtime'] > original + 31


def test_registration_stops_only_its_worker_before_updating_storage_permission(tmp_path, monkeypatch):
    from vet_pipeline import recorder_setup as r
    from vet_pipeline.util import write_json
    private_config, proof = tmp_path / 'pipeline.toml', tmp_path / 'proof.json'
    cfg = config(REPO / 'config/benchmarks/local-vulkan.example.toml')
    cfg['github'].update(checkout='/private/master', allow_clinical=True)
    cfg['backup']['allow_clinical_remote'] = True
    r.save_config(private_config, cfg)
    write_json(proof, {'status': 'passed', 'coreSha256': r.core_fingerprint()})
    usb = tmp_path / 'usb'; usb.mkdir()
    monkeypatch.setattr(r, 'CONFIG', private_config)
    monkeypatch.setattr(r, 'PROOF', proof)
    monkeypatch.setattr(r, 'inventory', lambda: [{'uuid': 'abc', 'mountpoints': [str(usb)]}])
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[2] == 'stop':
            assert config(private_config)['github']['allow_clinical']
        else:
            assert not config(private_config)['github']['allow_clinical']
            assert not config(private_config)['backup']['allow_clinical_remote']
    monkeypatch.setattr(r.subprocess, 'run', command)
    result = r.register(usb, 'local-permission', activate=True)
    assert result['activated'] and not result['clinicalCloudUpload']
    assert calls == [
        ['systemctl', '--user', 'stop', 'vet-fieldnotes.timer', 'vet-fieldnotes.service'],
        ['systemctl', '--user', 'enable', '--now', 'vet-fieldnotes.timer'],
        ['systemctl', '--user', 'start', '--no-block', 'vet-fieldnotes.service'],
    ]
