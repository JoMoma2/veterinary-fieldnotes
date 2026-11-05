"""Synthetic ADPCM fixtures reproduce recorder headers without clinical audio."""
import struct
import wave

import pytest

from vet_pipeline.audio_prepare import inspect_audio, normalize_copy
from vet_pipeline.util import digest_file


def recorder_wav(path, blocks=200, missing_bytes=0, per_block=505, riff_extra=0, rate=16000):
    def chunk(tag, payload):
        return tag + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')

    fmt = struct.pack('<HHIIHHHH', 17, 1, rate, rate // 2, 256, 4, 2, per_block)
    payload = b'\0' * (blocks * 256 - missing_bytes)
    data = b'WAVE' + chunk(b'fmt ', fmt) + chunk(b'fact', struct.pack('<I', blocks)) + chunk(b'data', payload)
    path.write_bytes(b'RIFF' + struct.pack('<I', len(data) + riff_extra) + data)
    return path


def test_recorder_block_count_duration_is_verified_and_source_unchanged(tmp_path):
    pytest.importorskip('av')
    source = recorder_wav(tmp_path / 'recorder.wav')
    before = digest_file(source)
    info = inspect_audio(source)
    assert info['durationSeconds'] == pytest.approx(200 * 505 / 16000)
    assert info['headerDurationSeconds'] != info['durationSeconds']
    assert info['timingWarnings'] and info['clockConfidence'] == 'unknown'
    output = tmp_path / 'normalized.wav'
    manifest = normalize_copy(source, output)
    with wave.open(str(output), 'rb') as wav:
        assert wav.getnframes() == 200 * 505
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
    assert manifest['normalizedDurationSeconds'] == info['durationSeconds']
    assert before == digest_file(source) == manifest['originalSha256']
    assert manifest['normalizedSha256'] == digest_file(output)


@pytest.mark.parametrize('kwargs,message', [
    ({'missing_bytes': 1}, 'Incomplete IMA'),
    ({'per_block': 504}, 'Invalid IMA'),
    ({'riff_extra': 100}, 'RIFF size'),
])
def test_bad_recorder_payloads_still_fail_before_install(tmp_path, kwargs, message):
    pytest.importorskip('av')
    source = recorder_wav(tmp_path / 'bad.wav', **kwargs)
    before = digest_file(source)
    target = tmp_path / 'normalized.wav'
    with pytest.raises(ValueError, match=message):
        normalize_copy(source, target)
    assert not target.exists()
    assert digest_file(source) == before


def test_recorder_decoded_duration_limit_remains_enforced(tmp_path):
    pytest.importorskip('av')
    source = recorder_wav(tmp_path / 'recorder.wav')
    with pytest.raises(ValueError, match='at most 5 seconds'):
        normalize_copy(source, tmp_path / 'normalized.wav', max_seconds=5)


def test_pcm_duration_mismatch_still_rejected(tmp_path, monkeypatch):
    pytest.importorskip('av')
    from vet_pipeline import audio_prepare
    source = tmp_path / 'pcm.wav'
    with wave.open(str(source), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0' * 32000)
    inspect = audio_prepare.inspect_audio
    monkeypatch.setattr(audio_prepare, 'inspect_audio', lambda path: {**inspect(path), 'durationSeconds': 2})
    with pytest.raises(ValueError, match='differs from header'):
        normalize_copy(source, tmp_path / 'normalized.wav')


def test_compressed_recording_commits_and_resumes_without_repeating_ai(store, cfg, tmp_path, monkeypatch):
    pytest.importorskip('av')
    import math
    from vet_pipeline.ingest import ingest
    from vet_pipeline.extraction import Provider
    from vet_pipeline.library import current, validate_library
    from vet_pipeline.runner import run, reset_failed
    from vet_pipeline.util import REPO, load_json, write_json
    transcript = load_json(REPO / 'fixtures/pipeline/transcripts/01-first.json')
    blocks = math.ceil(max(s['end'] for s in transcript['segments']) * 96000 / 505) + 1
    blocks += (4 - blocks) % 6  # Reproduce rounding up to the next 16k sample.
    source = recorder_wav(tmp_path / 'recorder.wav', blocks=blocks, rate=96000)
    before = digest_file(source)
    rid, _ = ingest(store, source, 's-2026-11-05', '2026-11-05', 'synthetic', 'synthetic-test')
    target = store.root / 'normalized' / (rid + '.wav')
    normalized = normalize_copy(source, target)
    write_json(target.with_suffix('.json'), normalized)
    duration = normalized['normalizedDurationSeconds']
    assert duration > blocks * 505 / 96000
    transcript['segments'][-1]['end'] = duration
    write_json(store.root / 'transcripts' / (rid + '.json'), transcript)
    data = Provider(cfg).extract(transcript, [], 'synthetic')
    data['discussions'][-1]['quotes'][-1]['end'] = duration
    write_json(store.root / 'extractions' / (rid + '.json'), data)
    # Reproduce an exhausted commit-only retry with both AI stages checkpointed.
    store.update(rid, stage='commit', attempts=3, error='Error')
    reset_failed(store, rid)
    monkeypatch.setattr('vet_pipeline.runner.transcribe', lambda *a: pytest.fail('repeated ASR'))
    monkeypatch.setattr('vet_pipeline.runner.extract_recording', lambda *a: pytest.fail('repeated extraction'))
    assert run(store, cfg)[0]['status'] == 'done'
    lib = validate_library(current(store))
    assert lib['articles'] and lib['discussions']
    assert lib['shifts'][0]['recordings'][0]['durationSeconds'] == duration
    assert max(s['endSeconds'] for d in lib['discussions'] for s in d['segments']) == duration
    assert digest_file(source) == before
    assert run(store, cfg) == []


def test_morning_report_refreshes_stale_header_estimates(store, cfg, tmp_path):
    pytest.importorskip('av')
    from vet_pipeline.ingest import ingest
    from vet_pipeline.morning import report
    from vet_pipeline.util import load_json, write_json
    source = recorder_wav(tmp_path / 'recorder.wav')
    rid, _ = ingest(store, source, 's-2026-11-05', '2026-11-05', 'synthetic', 'synthetic-test')
    path = store.root / 'source-metadata' / (rid + '.json')
    old = load_json(path)
    write_json(path, {**old, 'durationSeconds': 6.4})
    summary = report(store, cfg, {})
    meta = load_json(path)
    assert summary['audioSeconds'] == pytest.approx(6.312, abs=0.001)
    assert meta['headerDurationSeconds'] == pytest.approx(6.4)
    assert meta['audioMetadataVersion'] == 2 and meta['timingWarnings']
    assert meta['sha256'] == old['sha256'] and meta['originalName'] == old['originalName']


def test_pcm_duration_reading_needs_no_optional_decoder(tmp_path, monkeypatch):
    from vet_pipeline import audio_prepare
    path = tmp_path / 'pcm.wav'
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0' * 32000)
    monkeypatch.setattr(audio_prepare, 'inspect_audio', lambda *a: pytest.fail('unnecessary decoder dependency'))
    assert audio_prepare.duration_seconds(path) == 1
