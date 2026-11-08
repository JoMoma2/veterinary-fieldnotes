import math

import pytest

np = pytest.importorskip('numpy')
from vet_pipeline.global_speakers import cluster
from vet_pipeline.speakers import label_interval


def test_all_shift_groups_reconnect_across_distant_files():
    vectors = [[1, .01, 0], [0, 1, .01], [.99, .02, 0], [0, .99, .02], [0, 0, 1]]
    groups, _ = cluster(vectors, ['clip-1', 'clip-1', 'clip-23', 'clip-76', 'clip-78'])
    assert sorted(sorted(g) for g in groups) == [[0, 2], [1, 3], [4]]


def test_distinct_local_speakers_cannot_merge_even_through_a_third_file():
    groups, _ = cluster([[1, .01], [1, .02], [1, .015], [0, 1]], ['one', 'one', 'two', 'three'])
    assert not any(0 in group and 1 in group for group in groups)


def test_complete_link_prevents_weak_transitive_identity_chain():
    vectors = [[math.cos(math.radians(a)), math.sin(math.radians(a))] for a in [0, 20, 40, 150]]
    groups, _ = cluster(vectors, ['a', 'b', 'c', 'd'], {'rawSimilarity': .9, 'centeredSimilarity': -1})
    assert any(len(g) == 2 for g in groups)
    assert not any(0 in g and 2 in g for g in groups)


def test_detected_speech_alignment_handles_padding_without_labelling_silence():
    turns = [{'start': 1, 'end': 3, 'speaker': 'Speaker_001'}]
    assert label_interval(0, 7, turns)['speaker'] == 'Unknown'  # legacy unchanged
    assert label_interval(0, 7, turns, True)['speaker'] == 'Speaker_001'
    assert label_interval(0, 30, turns, True)['speaker'] == 'Unknown'
    turns += [{'start': 3, 'end': 5, 'speaker': 'Speaker_002'}]
    assert label_interval(0, 7, turns, True)['speaker'] == 'Mixed/uncertain'


def test_owner_seed_links_only_explicitly_annotated_reference_groups():
    vectors = [[1, 0, 0], [.7, .7, 0], [0, 0, 1]]
    conflict = np.zeros((3, 3), dtype=bool)
    settings = {'rawSimilarity': .9, 'centeredSimilarity': -1, 'linkage': 'average', 'minimumPairSimilarity': .25}
    groups, _ = cluster(vectors, ['a', 'b', 'c'], settings, conflict, [[0, 1]])
    assert groups == [[0, 1], [2]]
    conflict[0, 1] = conflict[1, 0] = True
    with pytest.raises(ValueError, match='simultaneous'):
        cluster(vectors, ['a', 'b', 'c'], settings, conflict, [[0, 1]])
