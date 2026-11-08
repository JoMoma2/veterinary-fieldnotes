import json
import sys
import types
import wave

import pytest

from vet_pipeline import speakers
from vet_pipeline.util import load_json, write_json, digest_file


def test_voice_matching_is_shift_scoped_and_does_not_merge_local_speakers():
    roster = {}
    a, _, _ = speakers.assign_cluster([1, 0], roster, set(), speakers.SETTINGS)
    b, _, _ = speakers.assign_cluster([0, 1], roster, {a}, speakers.SETTINGS)
    assert (a, b) == ('Speaker_001', 'Speaker_002')
    assert speakers.assign_cluster([.99, .01], roster, set(), speakers.SETTINGS)[0] == a
    assert speakers.assign_cluster([1, 0], roster, {a}, speakers.SETTINGS)[0] != a
    assert speakers.assign_cluster([1, 0], {}, set(), speakers.SETTINGS)[0] == 'Speaker_001'


def test_close_competing_voices_are_split_and_invalid_vectors_rejected():
    roster = {'Speaker_001': {'vector': speakers.unit([1, .1])}, 'Speaker_002': {'vector': speakers.unit([1, -.1])}}
    assert speakers.assign_cluster([1, 0], roster, set(), speakers.SETTINGS)[0] == 'Speaker_003'
    with pytest.raises(ValueError):
        speakers.unit([float('nan')])


def test_transcript_turns_require_dominant_coverage_and_preserve_uncertainty():
    turns = [{'start': 0, 'end': 2, 'speaker': 'Speaker_001'}, {'start': 2, 'end': 4, 'speaker': 'Speaker_002'}]
    assert speakers.label_interval(0, 2, turns)['speaker'] == 'Speaker_001'
    assert speakers.label_interval(0, 4, turns)['speaker'] == 'Mixed/uncertain'
    assert speakers.label_interval(8, 10, turns)['speaker'] == 'Unknown'
    assert speakers.label_interval(1, 1, turns)['speaker'] == 'Unknown'


def test_checkpoint_resume_reuses_audio_inference_and_preserves_sources(tmp_path, monkeypatch):
    root = tmp_path / 'private'; (root / 'inputs').mkdir(parents=True)
    audio = root / 'inputs/r-synthetic.wav'
    with wave.open(str(audio), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(b'\0\0' * 64000)
    before = digest_file(audio)
    write_json(root / 'recordings.json', [{'id': 'r-synthetic', 'number': 1, 'name': 'synthetic.wav'}])
    write_json(root / 'experiment.json', {'audio': {'r-synthetic': {'sha256': before}}})
    models = tmp_path / 'models.json'; weights = tmp_path / 'synthetic-model'; weights.write_text('fixture')
    write_json(models, {'segmentation': str(weights), 'embedding': str(weights)})
    class Audio:
        samplerate = 16000; channels = 1
        def __init__(self, path): self.audio = wave.open(str(path), 'rb')
        def __enter__(self): return self
        def __exit__(self, *args): self.audio.close()
        def __len__(self): return self.audio.getnframes()
        def seek(self, start): self.audio.setpos(start)
        def read(self, frames, dtype): return self.audio.readframes(frames)
    monkeypatch.setitem(sys.modules, 'soundfile', types.SimpleNamespace(SoundFile=Audio))
    calls = []
    interrupted = [False]
    class Engine:
        def process(self, audio, callback):
            calls.append(True); callback(1, 1)
            if len(calls) == 2 and not interrupted[0]:
                interrupted[0] = True
                raise KeyboardInterrupt('synthetic interrupted chunk')
            return {'turns': [{'start': 0, 'end': 1, 'localSpeaker': 0}], 'embeddings': {'0': [1, 0]}}
    cfg = {**speakers.SETTINGS, 'chunkSeconds': 2}
    with pytest.raises(KeyboardInterrupt):
        speakers.run(root, models, Engine(), cfg)
    assert len(list((root / 'speaker-chunks').glob('*-0000.json'))) == 1
    speakers.run(root, models, Engine(), cfg)
    assert len(calls) == 3
    first = load_json(root / 'speaker-labels.json')
    speakers.run(root, models, Engine(), cfg)
    assert len(calls) == 3 and load_json(root / 'speaker-labels.json') == first
    assert first['speakers'] == ['Speaker_001'] and digest_file(audio) == before
    assert 'Speaker_001' in (root / 'speaker-transcript.md').read_text()
    assert load_json(root / 'speaker-progress.json')['status'] == 'complete'
    with pytest.raises(ValueError, match='Immutable speaker settings'):
        speakers.run(root, models, Engine(), {**cfg, 'matchSimilarity': .9})


def test_missing_recording_does_not_block_other_work_and_never_identifies_people(tmp_path, monkeypatch):
    root = tmp_path / 'private'; root.mkdir()
    write_json(root / 'recordings.json', [{'id': 'missing', 'number': 1, 'name': 'missing.wav'}])
    write_json(root / 'experiment.json', {'audio': {}})
    model = tmp_path / 'weights'; model.write_text('fixture')
    manifest = tmp_path / 'models.json'; write_json(manifest, {'segmentation': str(model), 'embedding': str(model)})
    monkeypatch.setitem(sys.modules, 'soundfile', types.SimpleNamespace())
    speakers.run(root, manifest, object())
    assert load_json(root / 'speaker-progress.json')['status'] == 'complete-with-failures'
    assert load_json(root / 'speaker-labels.json')['speakers'] == []
