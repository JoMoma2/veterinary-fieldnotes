"""Synthetic ADPCM fixtures reproduce recorder headers without clinical audio."""
import struct
import wave

import pytest

from vet_pipeline.audio_prepare import inspect_audio, normalize_copy
from vet_pipeline.util import digest_file


def recorder_wav(path, blocks=200, missing_bytes=0, per_block=505, riff_extra=0):
    def chunk(tag, payload):
        return tag + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')

    fmt = struct.pack('<HHIIHHHH', 17, 1, 16000, 8000, 256, 4, 2, per_block)
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
