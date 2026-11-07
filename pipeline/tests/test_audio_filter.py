import math
import struct
import wave

import pytest

pytest.importorskip('av')

from vet_pipeline.audio_filter import filter_copy
from vet_pipeline.util import digest_file


def audio(path, samples=16037, rate=16000):
    # Simultaneous low rumble and speech-band tone; awkward frame count exercises flush.
    values = [int(3000 * math.sin(2 * math.pi * 20 * i / rate) + 3000 * math.sin(2 * math.pi * 1000 * i / rate)) for i in range(samples)]
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
        out.writeframes(struct.pack('<' + 'h' * samples, *values))


@pytest.mark.parametrize('profile', ['highpass', 'denoise'])
def test_filter_preserves_source_frames_origin_and_flush(tmp_path, profile):
    source, target = tmp_path / 'source.wav', tmp_path / 'copy.wav'
    audio(source)
    before = digest_file(source)
    manifest = filter_copy(source, target, profile)
    assert digest_file(source) == before == manifest['sourceSha256']
    assert manifest['samples'] == 16037 and manifest['timeOriginOffsetSeconds'] == 0
    assert manifest['outputSha256'] != before
    assert (target.stat().st_mode & 0o777) == 0o600
    with wave.open(str(target)) as result:
        assert (result.getnframes(), result.getnchannels(), result.getsampwidth(), result.getframerate()) == (16037, 1, 2, 16000)
    assert not list(tmp_path.glob('.filter-*'))


def test_highpass_suppresses_rumble_without_erasing_speech_band(tmp_path):
    source, target = tmp_path / 'source.wav', tmp_path / 'copy.wav'
    audio(source, samples=32000)
    filter_copy(source, target, 'highpass')
    with wave.open(str(target)) as result:
        samples = struct.unpack('<32000h', result.readframes(32000))[16000:]
    def amplitude(hz):
        re = sum(v * math.cos(2 * math.pi * hz * i / 16000) for i, v in enumerate(samples))
        im = sum(v * math.sin(2 * math.pi * hz * i / 16000) for i, v in enumerate(samples))
        return 2 * math.hypot(re, im) / len(samples)
    assert amplitude(20) < 300
    assert 2850 < amplitude(1000) < 3150


@pytest.mark.parametrize('profile', ['highpass', 'denoise'])
@pytest.mark.parametrize('impulse', [200, 8000, 15900])
def test_delay_is_compensated_including_audio_near_end(tmp_path, profile, impulse):
    source, target = tmp_path / 'source.wav', tmp_path / 'copy.wav'
    values = [0] * 16000
    values[impulse] = 15000
    with wave.open(str(source), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
        out.writeframes(struct.pack('<16000h', *values))
    result = filter_copy(source, target, profile)
    with wave.open(str(target)) as out:
        filtered = struct.unpack('<16000h', out.readframes(16000))
    assert max(range(16000), key=lambda i: abs(filtered[i])) == impulse
    assert result['compensatedDelaySamples'] == (400 if profile == 'denoise' else 0)


def test_rejects_overwrite_and_invalid_format_without_output(tmp_path):
    source, target = tmp_path / 'source.wav', tmp_path / 'copy.wav'
    audio(source)
    before = digest_file(source)
    with pytest.raises(ValueError, match='never overwritten'):
        filter_copy(source, source, 'highpass')
    assert digest_file(source) == before
    audio(source, rate=8000)
    with pytest.raises(ValueError, match='mono16k'):
        filter_copy(source, target, 'highpass')
    assert not target.exists() and not list(tmp_path.glob('.filter-*'))


def test_rejects_git_exports_and_unknown_profiles(tmp_path):
    source = tmp_path / 'source.wav'
    audio(source)
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    (repo / '.git/HEAD').write_text('ref: refs/heads/main\n')
    with pytest.raises(ValueError, match='outside every Git'):
        filter_copy(source, repo / 'private.wav', 'highpass')
    with pytest.raises(ValueError, match='Unknown'):
        filter_copy(source, tmp_path / 'new.wav', 'arbitrary filter chain')


def test_explicit_long_recording_limit_preserves_samples(tmp_path):
    source = tmp_path / 'source.wav'; audio(source, samples=32037)
    with pytest.raises(ValueError, match='duration limit'):
        filter_copy(source, tmp_path / 'too-long.wav', 'denoise', max_seconds=2)
    result = filter_copy(source, tmp_path / 'allowed.wav', 'denoise', max_seconds=86400)
    assert result['samples'] == 32037
