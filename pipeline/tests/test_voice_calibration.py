import pytest

from vet_pipeline.voice_calibration import evaluate, render
from vet_pipeline.util import digest_file, write_json


def pack(tmp_path):
    root = tmp_path / 'private'; folder = root / 'calibration'; folder.mkdir(parents=True)
    cases = []
    for number, score in enumerate([.8, .5], 1):
        name = f'clip-{number:02d}'; path = folder / (name + '.wav'); path.write_bytes(b'RIFF-synthetic-fixture')
        cases.append({'id': name, 'supportedSimilarity': score, 'clipSha256': digest_file(path)})
    write_json(folder / 'pack.json', {'binding': {'synthetic': True}, 'cases': cases})
    labels = tmp_path / 'labels.json'
    write_json(labels, {'version': 1, 'packSha256': digest_file(folder / 'pack.json'), 'answers': {'clip-01': 'owner', 'clip-02': 'other'}})
    return root, labels


def test_local_counts_show_false_matches_without_deploying_thresholds(tmp_path):
    root, labels = pack(tmp_path)
    results = evaluate(root, labels, [.45, .65])
    assert results[0]['trueOwnerMatches'] == results[0]['falseOwnerMatches'] == 1
    assert results[1]['trueOwnerMatches'] == results[1]['correctOther'] == 1
    assert not (root / 'deployed-profile.json').exists()


def test_wrong_pack_or_unknown_labels_are_rejected(tmp_path):
    root, labels = pack(tmp_path)
    write_json(labels, {'version': 1, 'packSha256': 'not-this-pack', 'answers': {}})
    with pytest.raises(ValueError, match='different listening pack'):
        evaluate(root, labels)
    write_json(labels, {'version': 1, 'packSha256': digest_file(root / 'calibration/pack.json'), 'answers': {'invented': 'owner'}})
    with pytest.raises(ValueError, match='Invalid listening labels'):
        evaluate(root, labels)


def test_blinded_report_has_local_audio_and_memory_only_annotation(tmp_path):
    root, labels = pack(tmp_path); path = render(root); text = path.read_text()
    assert 'data:audio/wav;base64,' in text and 'Download my labels' in text
    assert 'localStorage' not in text and 'fetch(' not in text
    assert 'Multiple voices' in text and 'Unsure' in text
    assert 'supportedSimilarity' not in text  # hidden to avoid anchoring judgement
    (root / 'calibration/clip-01.wav').write_bytes(b'changed')
    with pytest.raises(ValueError, match='clip changed'):
        render(root)
