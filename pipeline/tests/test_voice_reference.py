import pytest

from vet_pipeline.voice_reference import score, coverage, render, confirm_owner_only, prepare
from vet_pipeline.util import write_json, load_json, digest_file


def test_match_requires_multiple_supporting_windows_not_one_favorable_example():
    templates = [{'vector': v} for v in [[1, 0], [.8, .6], [0, 1]]]
    result = score([1, 0], templates)
    assert result['bestSimilarity'] == 1 and result['supportedSimilarity'] == 0
    assert score([1, 0], templates[:2])['supportedSimilarity'] is None
    with pytest.raises(ValueError, match='Incompatible'):
        score([1, 0, 0], templates)


def test_reference_coverage_measures_union_and_overlapping_voices():
    assert coverage(0, 10, [{'start': 0, 'end': 8}, {'start': 4, 'end': 10}]) == (1, .4)
    assert coverage(0, 10, []) == (0, 0)


def test_reference_report_is_private_portable_and_requires_explicit_attestation(tmp_path):
    root = tmp_path / 'reference'; root.mkdir(mode=0o700)
    (root / 'reference-16k.wav').write_bytes(b'RIFF-fixture')
    write_json(root / 'candidate-profile.json', {'templates': [{'start': 0, 'end': 8, 'vector': [1, 0]}] * 3,
        'skippedWindows': [], 'durationSeconds': 24})
    render(root)
    html = (root / 'review.html').read_text()
    assert 'Pending confirmation' in html and 'data:audio/wav;base64,' in html
    assert not (root / 'attestation.json').exists()
    confirm_owner_only(root)
    assert load_json(root / 'attestation.json')['ownerOnlySpeechConfirmed']
    assert 'reference enrolled for LOCAL EVALUATION' in (root / 'review.html').read_text()
    assert (root / 'attestation.json').stat().st_mode & 0o077 == 0


def test_fewer_than_three_windows_cannot_be_enrolled(tmp_path):
    root = tmp_path / 'reference'; root.mkdir()
    write_json(root / 'candidate-profile.json', {'templates': []})
    with pytest.raises(ValueError, match='Not enough'):
        confirm_owner_only(root)


def test_reference_prepare_retains_source_and_registers_exact_content_only(store, tmp_path):
    from vet_pipeline.source_purpose import exclusions
    source = tmp_path / 'owner.wav'; source.write_bytes(b'RIFF-reference-fixture')
    before = source.stat(); sha = digest_file(source)
    root = prepare(source, tmp_path / 'private-reference', store.root)
    assert digest_file(root / 'reference-original.wav') == sha == digest_file(source)
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert sha in exclusions(store.root) and not store.jobs()
    assert load_json(root / 'source.json')['originalName'] == source.name
