import wave
from pathlib import Path

import pytest

from vet_pipeline import asr_comparison as comparison
from vet_pipeline.asr_quality import assess_whisper, TranscriptionReviewRequired
from vet_pipeline.ingest import ingest
from vet_pipeline.runner import ProcessingDeferred
from vet_pipeline.util import digest_file, load_json, write_json


@pytest.fixture
def batch(store, cfg, tmp_path, monkeypatch):
    model = tmp_path / 'model.bin'; model.write_bytes(b'synthetic model placeholder')
    exe = tmp_path / 'exe'; exe.write_bytes(b'synthetic executable placeholder')
    cfg['provider']['kind'] = 'ollama'
    cfg['transcription'].update(kind='whisper-cpp', model=str(model), executable=str(exe), max_text_context=0, temperature_fallback=False)
    ids = []
    for i in range(2):
        source = tmp_path / f'synthetic-{i}.wav'
        with wave.open(str(source), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\0' * 32000 * (i + 1))
        rid, _ = ingest(store, source, 's-test', '2026-11-05', 'synthetic', 'synthetic-test')
        ids.append(rid)
        write_json(store.root / 'transcription-details' / (rid + '.json'), {'transcription': [{'offsets': {'from': 0, 'to': 1000}, 'text': 'Synthetic baseline.'}]})
    calls = []
    def infer(path, settings):
        calls.append(path)
        assert settings['max_text_context'] == 0 and not settings['temperature_fallback']
        raw = {'transcription': [{'offsets': {'from': 0, 'to': 1000}, 'text': 'Synthetic candidate.'}]}
        quality = assess_whisper(raw, 1)
        write_json(Path(settings['details_path']), raw)
        write_json(Path(settings['quality_path']), quality)
        return {'segments': [{'start': 0, 'end': 1, 'text': 'Synthetic candidate.'}], 'transcriptionQuality': quality, 'transcriptionBackend': {'gpuAccelerationConfirmed': True}}
    monkeypatch.setattr(comparison, 'check_resources', lambda *a: None)
    monkeypatch.setattr(comparison, 'transcribe_cpp', infer)
    return {'source': store.root, 'output': tmp_path / 'comparison', 'cfg': cfg, 'ids': ids, 'calls': calls, 'infer': infer}


def execute(b):
    return comparison.run(b['source'], b['output'], b['cfg'], 'synthetic-local-test')


def test_retained_comparison_is_private_and_resumes_without_source_changes(batch, store):
    before = {j['id']: digest_file(store.root / 'inputs' / (j['id'] + '.wav')) for j in store.jobs()}
    result = execute(batch)
    assert result['completed'] == 2 and len(batch['calls']) == 2
    assert all(r['status'] == 'completed-unreviewed' for r in result['results'])
    finished = (batch['output'] / 'progress.json').read_text()
    assert execute(batch)['completed'] == 2 and len(batch['calls']) == 2
    assert (batch['output'] / 'progress.json').read_text() == finished
    assert all(j['stage'] == 'transcribe' for j in store.jobs())
    assert all(digest_file(store.root / 'inputs' / (j['id'] + '.wav')) == before[j['id']] for j in store.jobs())
    html = (batch['output'] / 'index.html').read_text()
    assert 'accuracy' not in html or 'unreviewed' in html
    assert 'Candidate max repeats' in html and 'http://' not in html


def test_bad_timestamp_retains_raw_and_does_not_stop_other_recordings(batch, monkeypatch):
    def infer(path, settings):
        if path.stem == batch['ids'][0]:
            from pathlib import Path
            write_json(Path(settings['details_path']), {'transcription': [{'offsets': {'from': 10, 'to': 10}, 'text': 'Uncertain synthetic words'}]})
            raise TranscriptionReviewRequired()
        return batch['infer'](path, settings)
    monkeypatch.setattr(comparison, 'transcribe_cpp', infer)
    result = execute(batch)
    assert [r['status'] for r in result['results']] == ['review-required', 'completed-unreviewed']
    assert (batch['output'] / 'results' / batch['ids'][0] / 'whisper.json').is_file()


def test_crash_after_raw_output_recovers_without_repeating_that_inference(batch, monkeypatch):
    def interrupted(path, settings):
        batch['infer'](path, settings)
        raise KeyboardInterrupt()
    monkeypatch.setattr(comparison, 'transcribe_cpp', interrupted)
    with pytest.raises(KeyboardInterrupt):
        execute(batch)
    monkeypatch.setattr(comparison, 'transcribe_cpp', batch['infer'])
    result = execute(batch)
    assert result['results'][0]['status'] == 'raw-recovered-review'
    assert len(batch['calls']) == 2


def test_configuration_change_refuses_to_overwrite_previous_comparison(batch):
    execute(batch)
    batch['cfg']['transcription']['temperature_fallback'] = True
    with pytest.raises(ValueError, match='inputs/settings changed'):
        execute(batch)
    assert len(batch['calls']) == 2


def test_modified_candidate_artifact_is_not_silently_reused(batch):
    execute(batch)
    raw = batch['output'] / 'results' / batch['ids'][0] / 'whisper.json'
    raw.write_text('{}')
    with pytest.raises(ValueError, match='artifact changed'):
        execute(batch)
    assert len(batch['calls']) == 2 and raw.read_text() == '{}'


def test_busy_gpu_deferral_is_resumable_and_visible(batch, monkeypatch):
    def busy(*a):
        raise ProcessingDeferred('shared work is active')
    monkeypatch.setattr(comparison, 'check_resources', busy)
    with pytest.raises(ProcessingDeferred):
        execute(batch)
    assert load_json(batch['output'] / 'progress.json')['stage'] == 'waiting-resources'
    assert not batch['calls']
    monkeypatch.setattr(comparison, 'check_resources', lambda *a: None)
    assert execute(batch)['completed'] == 2


def test_external_inference_is_rejected_before_any_audio_use(batch):
    batch['cfg']['provider']['base_url'] = 'https://example.invalid'
    with pytest.raises(ValueError, match='local Whisper'):
        execute(batch)
    assert not batch['calls'] and not batch['output'].exists()
