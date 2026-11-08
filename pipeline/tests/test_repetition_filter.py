from vet_pipeline.repetition_filter import find_runs, extraction_text, quote_allowed


def test_five_consecutive_phrases_are_excluded_but_four_are_retained():
    for count in [4, 5, 12]:
        spans, runs = find_runs([{'text': 'Still unknown.'}] * count)
        assert bool(runs) == (count >= 5)
        if runs:
            assert runs[0]['repeats'] == count and len(spans) == count


def test_case_punctuation_and_single_word_loops_are_detected_across_segments():
    spans, runs = find_runs([{'text': text} for text in ['sniff', 'Sniff.', 'sniff!', 'SNIFF', 'sniff']])
    assert len(runs) == 1 and len(spans) == 5


def test_two_loops_in_one_segment_do_not_remove_useful_intervening_words():
    text = ' '.join(['Repeat this.'] * 5) + ' Useful separate information. ' + ' '.join(['Again now.'] * 5)
    spans, runs = find_runs([{'text': text}])
    assert len(runs) == len(spans[0]) == 2
    block = {'text': text, 'repeatExcludedSpans': spans[0]}
    view = extraction_text(block)
    assert 'Useful separate information.' in view and 'Repeat this' not in view and 'Again now' not in view
    assert quote_allowed(block, 'Useful separate information.')
    assert not quote_allowed(block, 'Repeat this')
    assert block['text'] == text


def test_a_phrase_occurring_outside_a_loop_can_still_support_a_quote():
    text = 'one two one two one two one two one two. Different discussion: one two.'
    spans, _ = find_runs([{'text': text}])
    assert quote_allowed({'text': text, 'repeatExcludedSpans': spans[0]}, 'one two')
