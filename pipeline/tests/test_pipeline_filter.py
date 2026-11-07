"""Opt-in filtering preserves sources/checkpoints and does not authorize publication."""
import wave

import pytest

pytest.importorskip('av')
from vet_pipeline.config import config
from vet_pipeline.ingest import ingest, transcribe
from vet_pipeline.util import digest_file, load_json, write_json, REPO


def wav(path):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(b'\0\0' * 16037)


def test_filter_timeout_resume_retains_exact_audio_and_transcript(store, cfg, tmp_path, monkeypatch):
    source = tmp_path / 'source.wav'
    wav(source)
    original = digest_file(source)
    rid, _ = ingest(store, source, 's-filter', '2000-01-01', 'synthetic', 'test')
    cfg['transcription'].update(kind='whisper-cpp', audio_filter='denoise')
    def interrupted(path, settings):
        assert path.parent.name == 'filtered'
        raise TimeoutError('synthetic interruption')
    monkeypatch.setattr('vet_pipeline.whisper_cpp.transcribe_cpp', interrupted)
    with pytest.raises(TimeoutError):
        transcribe(store, store.get(rid), cfg)
    filtered = store.root / 'filtered' / (rid + '.wav')
    saved = digest_file(filtered)
    assert not (store.root / 'transcripts' / (rid + '.json')).exists()
    monkeypatch.setattr('vet_pipeline.audio_filter.filter_copy', lambda *a, **k: pytest.fail('filter repeated'))
    def decode(path, settings):
        assert digest_file(path) == saved
        return {'segments': [{'start': 0, 'end': 1, 'text': 'Synthetic outcome unknown.'}]}
    monkeypatch.setattr('vet_pipeline.whisper_cpp.transcribe_cpp', decode)
    result = transcribe(store, store.get(rid), cfg)
    assert result['transcriptionBackend']['audioPreprocessing']['compensatedDelaySamples'] == 400
    assert digest_file(source) == digest_file(store.root / 'inputs' / (rid + '.wav')) == original
    monkeypatch.setattr('vet_pipeline.whisper_cpp.transcribe_cpp', lambda *a: pytest.fail('ASR repeated'))
    assert transcribe(store, store.get(rid), cfg) == result


def test_changed_filtered_checkpoint_is_not_silently_reused(store, cfg, tmp_path, monkeypatch):
    source = tmp_path / 'source.wav'; wav(source)
    rid, _ = ingest(store, source, 's-filter', '2000-01-01', 'synthetic', 'test')
    cfg['transcription'].update(kind='whisper-cpp', audio_filter='denoise')
    monkeypatch.setattr('vet_pipeline.whisper_cpp.transcribe_cpp', lambda *a: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(TimeoutError):
        transcribe(store, store.get(rid), cfg)
    (store.root / 'filtered' / (rid + '.wav')).write_bytes(b'changed')
    with pytest.raises(ValueError, match='Saved filtered audio/profile changed'):
        transcribe(store, store.get(rid), cfg)


def test_full_synthetic_cycle_filters_retains_and_only_prepares_candidates(store, cfg, tmp_path, monkeypatch):
    from vet_pipeline.unattended import cycle
    from test_unattended import setup
    usb, source = setup(cfg, tmp_path, monkeypatch)
    cfg['transcription']['audio_filter'] = 'denoise'
    # Restore real ingestion/normalization/filtering behind the synthetic model stub.
    monkeypatch.setattr('vet_pipeline.runner.transcribe', transcribe)
    monkeypatch.setattr('vet_pipeline.whisper_cpp.transcribe_cpp', lambda path, settings: load_json(REPO / 'fixtures/pipeline/transcripts/01-first.json'))
    before = digest_file(source)
    result = cycle(store, cfg)
    assert result['incomplete'] == 0 and result['articlesCreated'] == 3
    rid = store.jobs()[0]['id']
    assert (store.root / 'filtered' / (rid + '.wav')).exists()
    assert (store.root / 'transcripts' / (rid + '.json')).exists()
    assert before == digest_file(source) == digest_file(store.root / 'inputs' / (rid + '.wav'))
    candidates = load_json(store.root / 'review/publication-candidates.json')['entries']
    assert candidates and all(not item['approved'] for item in candidates)
    assert cycle(store, cfg)['newImports'] == 0


def test_filter_config_is_explicit_and_backend_bound(tmp_path):
    assert config()['transcription']['audio_filter'] == 'none'
    p = tmp_path / 'config.toml'
    p.write_text('[transcription]\naudio_filter="denoise"\n')
    with pytest.raises(ValueError, match='audio filter'):
        config(p)
