import os
import time
import wave

import pytest

from vet_pipeline.automation import scan
from vet_pipeline.ingest import ingest
from vet_pipeline.source_purpose import register_reference, ReferenceOnlySource
from vet_pipeline.util import digest_file, write_json


def wav(path, value=0):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(bytes([value, 0]) * 16000)
    os.utime(path, (time.time() - 100, time.time() - 100))


def test_voice_reference_exclusion_survives_rename_but_not_different_content(store, cfg, tmp_path):
    device = tmp_path / 'device'; device.mkdir()
    original = device / 'reference.wav'; wav(original)
    sha = digest_file(original)
    register_reference(store.root, tmp_path / 'voice-reference', sha)
    original.rename(device / 'renamed.wav')
    cfg['usb'].update(origin='synthetic', authorization_ref='test')
    result = scan(store, cfg, device, '2000-01-01')
    assert result == [{'status': 'reference-only-skipped', 'imported': False}]
    assert not store.jobs() and digest_file(device / 'renamed.wav') == sha
    wav(device / 'reference.wav', value=1)
    result = scan(store, cfg, device, '2000-01-01')
    assert sum(bool(row.get('imported')) for row in result) == 1
    assert len(store.jobs()) == 1


def test_direct_ingest_also_respects_purpose_and_invalid_registry_fails_closed(store, tmp_path):
    source = tmp_path / 'voice.wav'; wav(source)
    register_reference(store.root, tmp_path / 'reference', digest_file(source))
    with pytest.raises(ReferenceOnlySource):
        ingest(store, source, 's-test', '2000-01-01', 'synthetic', 'test')
    write_json(store.root / 'source-exclusions.json', {'version': 1, 'entries': {'bad': {}}})
    with pytest.raises(ValueError, match='Invalid source-purpose'):
        ingest(store, source, 's-test', '2000-01-01', 'synthetic', 'test')
    assert not store.jobs()
