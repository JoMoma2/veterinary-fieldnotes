import json
import wave
from types import SimpleNamespace

import pytest

from vet_pipeline.asr_quality import assess_segments, assess_whisper, TranscriptionReviewRequired
from vet_pipeline.ingest import ingest
from vet_pipeline.runner import run, reset_failed
from vet_pipeline.util import REPO, write_json, load_json


def repeated():
    return [{'start': i * 2, 'end': i * 2 + 1, 'text': 'A repeated synthetic phrase.'} for i in range(12)]


def test_repetition_flag_retains_source_and_is_not_an_accuracy_score():
    segments = repeated()
    quality = assess_segments(segments)
    assert quality['reviewRequired'] and quality['maximumPhraseRepeats'] == 12
    assert quality['longestConsecutiveRepeat'] == 12
    assert len(segments) == 12 and segments[0]['text'] == 'A repeated synthetic phrase.'
    assert 'Heuristic' in quality['note']


def test_ordinary_dialogue_and_occasional_repeated_words_are_not_flagged():
    segments = [{'start': i, 'end': i + .9, 'text': f'Unique observation number {i}'} for i in range(20)]
    segments += [{'start': 21 + i, 'end': 21 + i + .9, 'text': 'Yes'} for i in range(3)]
    assert not assess_segments(segments)['reviewRequired']


def test_loop_inside_one_segment_requires_review():
    assert assess_segments([{'start': 0, 'end': 30, 'text': 'repeat these four words ' * 20}])['reviewRequired']


@pytest.mark.parametrize('start,end,duration,key', [(1, 1, 2, 'invalidTimestampSegments'), (0, 5, 2, 'outOfBoundsSegments')])
def test_bad_raw_timestamps_are_flagged_without_repair(start, end, duration, key):
    raw = {'transcription': [{'offsets': {'from': start * 1000, 'to': end * 1000}, 'text': 'Uncertain words'}]}
    quality = assess_whisper(raw, duration)
    assert quality[key] == [0] and quality['reviewRequired']
    assert raw['transcription'][0]['offsets']['to'] == end * 1000


def test_suspect_audio_is_held_without_blocking_other_recordings(store, cfg, tmp_path, monkeypatch):
    source = tmp_path / 'synthetic.wav'
    with wave.open(str(source), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\0' * 32000 * 30)
    rid, _ = ingest(store, source, 's-test', '2026-10-22', 'synthetic', 'synthetic-test')
    other, _ = ingest(store, REPO / 'fixtures/pipeline/transcripts/01-first.json', 's-test', '2026-10-22', 'synthetic', 'synthetic-test')
    from vet_pipeline import runner
    transcribe = runner.transcribe
    def fake(s, j, c):
        if j['id'] != rid:
            return transcribe(s, j, c)
        result = {'segments': repeated()}
        write_json(s.root / 'transcripts' / (rid + '.json'), result)
        return result
    monkeypatch.setattr(runner, 'transcribe', fake)
    result = run(store, cfg)
    assert result[0]['status'] == 'review-required' and result[1]['status'] == 'done'
    assert store.get(rid)['stage'] == 'review' and store.get(rid)['attempts'] == 0
    assert store.get(other)['stage'] == 'done'
    assert (store.root / 'transcripts' / (rid + '.json')).is_file()
    assert load_json(store.root / 'transcription-quality' / (rid + '.json'))['reviewRequired']
    assert run(store, cfg) == []  # No repeated inference for a held recording.
    reset_failed(store, rid)
    monkeypatch.setattr(runner, 'transcribe', lambda *a: pytest.fail('checkpoint ASR repeated'))
    assert run(store, cfg)[0]['status'] == 'review-required'  # retry cannot bypass quality.


def test_invalid_whisper_offsets_retain_raw_and_review_report(tmp_path, monkeypatch, store, cfg):
    from vet_pipeline.whisper_cpp import transcribe_cpp
    from vet_pipeline.morning import report
    source = tmp_path / 'synthetic.wav'
    with wave.open(str(source), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\0' * 32000)
    rid, _ = ingest(store, source, 's-test', '2026-10-22', 'synthetic', 'synthetic-test')
    exe = tmp_path / 'placeholder'; exe.touch()
    raw = {'transcription': [{'offsets': {'from': 100, 'to': 100}, 'text': '<script>uncertain</script>'}]}
    def infer(args, **kwargs):
        from pathlib import Path
        Path(args[-1] + '.json').write_text(json.dumps(raw))
        return SimpleNamespace(stderr='')
    monkeypatch.setattr('subprocess.run', infer)
    details = store.root / 'transcription-details' / (rid + '.json')
    quality = store.root / 'transcription-quality' / (rid + '.json')
    with pytest.raises(TranscriptionReviewRequired):
        transcribe_cpp(source, {'executable': str(exe), 'model': str(exe), 'language': 'en', 'threads': 1, 'gpu_device': 0, 'timeout_seconds': 10, 'details_path': str(details), 'quality_path': str(quality)})
    assert load_json(details) == raw
    assert load_json(quality)['invalidTimestampSegments'] == [0]
    store.update(rid, stage='review', error='TranscriptionReviewRequired')
    summary = report(store, cfg, {})
    assert summary['recordingsAwaitingTranscriptReview'] == 1
    assert summary['recordingsWithASRWarnings'] == 1
    html = (store.root / 'review/recordings' / (rid + '.html')).read_text()
    assert 'Full raw Whisper output' in html and '&lt;script&gt;' in html
    assert '<script>' not in html


def test_existing_derived_articles_are_warned_without_erasing_records(store, cfg, first):
    from vet_pipeline.library import current
    from vet_pipeline.morning import report
    run(store, cfg)
    before = current(store)
    write_json(store.root / 'transcription-quality' / (first + '.json'), assess_segments(repeated()))
    summary = report(store, cfg, {})
    assert summary['recordingsWithASRWarnings'] == 1
    assert current(store) == before and store.get(first)['stage'] == 'done'
    article = next(a for a in before['articles'] if a['sourceDiscussionIds'])
    html = (store.root / 'review/articles' / (article['id'] + '.html')).read_text()
    assert 'Unreviewed transcription source' in html
