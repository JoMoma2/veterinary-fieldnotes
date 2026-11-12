from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
from vet_pipeline import parakeet as p
from vet_pipeline.asr_quality import TranscriptionReviewRequired
from vet_pipeline.config import config
from vet_pipeline.ingest import ingest, transcribe
from vet_pipeline.util import digest_file, load_json


@dataclass
class Segment:
    t0_ms: int
    t1_ms: int
    text: str


@dataclass
class Result:
    text: str
    raw_text: str
    timestamp_kind: str
    segments: list


class Context:
    def __enter__(self): return self
    def __exit__(self, *args): pass


class API:
    def __init__(self):
        self.calls = []
        self.vad_calls = 0
        self.fail_short = False
        self.no_speech = False
        self.invalid_time = False
        self.device = SimpleNamespace(kind='vulkan', device_type='gpu', description='Radeon RX 7900 XTX')

    def backends(self): return [SimpleNamespace(kind='vulkan', device_type='integrated', description='Ryzen'), self.device]

    def Model(self, path, **kwargs):
        api = self
        class Model(Context):
            device = api.device
            def vad_session(self, **kwargs):
                class Vad(Context):
                    def cancel(self): pass
                    def run(self, audio, **settings):
                        api.vad_calls += 1
                        assert settings == p.VAD
                        return SimpleNamespace(segments=[] if api.no_speech else [SimpleNamespace(start_sample=32000, end_sample=len(audio))])
                return Vad()
            def session(self, **kwargs):
                class Engine(Context):
                    def cancel(self): pass
                    def run(self, audio, **settings):
                        api.calls.append(len(audio))
                        if len(audio) < 480000 and api.fail_short:
                            raise RuntimeError('Synthetic interruption')
                        if len(audio) == 480000:
                            return Result('Synthetic observation.', 'Synthetic raw observation.', 'segment',
                                          [Segment(1000, 999999 if api.invalid_time else 2000, 'Synthetic observation.')])
                        return Result('Synthetic follow-up.', 'Synthetic raw follow-up.', 'none', [])
                return Engine()
        return Model()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    audio = tmp_path / 'synthetic.wav'
    with wave.open(str(audio), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b'\0\0' * 16000 * 35)
    cfg = config()
    settings = cfg['transcription']
    settings.update(kind='parakeet', runtime=str(tmp_path), runtime_sha256='synthetic-runtime',
                    details_path=str(tmp_path/'details.json'), quality_path=str(tmp_path/'quality.json'))
    for name in ['model', 'vad_model']:
        path = tmp_path / (name + '.gguf'); path.write_bytes(b'synthetic weights')
        settings[name] = str(path); settings[name + '_sha256'] = digest_file(path)
    api = API()
    monkeypatch.setattr(p, 'native', lambda binding: api)
    return audio, settings, api


def test_offsets_raw_output_and_unaligned_window_labels_survive(setup):
    source, settings, api = setup
    before = digest_file(source)
    t = p.transcribe_parakeet(source, settings)
    assert [(s['start'], s['end']) for s in t['segments']] == [(3.0, 4.0), (31.0, 35.0)]
    assert t['segments'][1]['timing'] == 'audio-window'
    raw = load_json(Path(settings['details_path']))
    assert raw['plan']['excludedRanges'] == [[0, 32000]]
    assert raw['windows'][0]['raw']['raw_text'] == 'Synthetic raw observation.'
    assert raw['windows'][0]['device'] == 'Radeon RX 7900 XTX'
    assert digest_file(source) == before


def test_interrupted_window_keeps_completed_work_and_resumes(setup):
    source, settings, api = setup
    api.fail_short = True
    with pytest.raises(RuntimeError): p.transcribe_parakeet(source, settings)
    window = Path(settings['details_path']).with_suffix('.windows') / 'window-0000.json'
    before = digest_file(window)
    api.fail_short = False
    t = p.transcribe_parakeet(source, settings)
    assert len(t['segments']) == 2 and api.calls.count(480000) == 1 and api.vad_calls == 1
    assert digest_file(window) == before
    assert list(window.parent.glob('window-0001-error-*.json'))


def test_no_detected_speech_is_reviewed_and_audio_is_kept(setup):
    source, settings, api = setup
    api.no_speech = True
    with pytest.raises(TranscriptionReviewRequired): p.transcribe_parakeet(source, settings)
    raw = load_json(Path(settings['details_path']))
    assert raw['segments'] == [] and raw['quality']['reviewRequired']
    assert raw['plan']['excludedRanges'] == [[0, 560000]]
    assert source.exists() and not api.calls


def test_changed_input_settings_cannot_reuse_old_checkpoints(setup):
    source, settings, api = setup
    p.transcribe_parakeet(source, settings)
    before = digest_file(Path(settings['details_path']))
    settings['language'] = 'fr'
    with pytest.raises(ValueError, match='input/settings changed'): p.transcribe_parakeet(source, settings)
    assert digest_file(Path(settings['details_path'])) == before


def test_invalid_native_timestamps_are_preserved_and_held(setup):
    source, settings, api = setup
    api.invalid_time = True
    with pytest.raises(TranscriptionReviewRequired): p.transcribe_parakeet(source, settings)
    raw = load_json(Path(settings['details_path']))
    assert raw['segments'][0]['end'] == pytest.approx(1001.999)
    assert raw['quality']['reviewRequired'] and raw['quality']['windowTimestampIssues'] == [0]


def test_normal_ingest_uses_selected_backend_without_altering_originals(setup, store):
    source, settings, api = setup
    cfg = config(); cfg['transcription'].update(settings)
    rid, _ = ingest(store, source, 'synthetic-shift', '2026-01-01', 'synthetic', 'synthetic test')
    t = transcribe(store, store.get(rid), cfg)
    assert t['transcriptionBackend']['kind'] == 'parakeet'
    assert t['transcriptionBackend']['speechDetection'] == 'silero-vad'
    assert digest_file(store.root/'inputs'/(rid+'.wav')) == digest_file(source)
    assert (store.root/'transcription-details'/(rid+'.json')).exists()
    from vet_pipeline.morning import report
    report(store, cfg, {})
    page = (store.root/'review/recordings'/(rid+'.html')).read_text()
    assert rid + '.windows/window-0000.json' in page
    assert 'input-window timing' in page


def test_unattended_accepts_selected_local_backend_and_still_forbids_downloads(setup):
    from vet_pipeline.unattended import validate
    _, settings, _ = setup
    cfg = config(); cfg['transcription'].update(settings)
    cfg['provider']['kind'] = 'ollama'
    cfg['usb'].update(device_uuid='synthetic-test', authorization_ref='synthetic test')
    validate(cfg)
    cfg['transcription']['allow_model_download'] = True
    with pytest.raises(ValueError, match='downloads are forbidden'): validate(cfg)
