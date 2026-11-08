import pytest
from vet_pipeline.study_policy import MEDICAL_QUESTION_RULES, question_rejection


@pytest.mark.parametrize('prompt,answer', [
    ('What was recorded?', 'Unstated outcome.'),
    ('What was this dog diagnosed with?', 'Unknown.'),
    ('What was Sample diagnosed with?', 'Unknown.'),
    ('What happened on December 13?', 'An observation.'),
    ('Source recall — complete the recorded statement', 'A quote.'),
    ('Which answer did Speaker_003 give?', 'A quote.'),
])
def test_obvious_case_and_conversation_recall_is_rejected(prompt, answer):
    assert question_rejection({'prompt': prompt, 'answer': answer}, ['Sample'])


def test_general_medical_question_is_allowed_without_claiming_semantic_validation():
    assert question_rejection({'prompt': 'What does tachypnea mean?', 'answer': 'An increased respiratory rate.'}) is None
    assert 'Do not extrapolate' in MEDICAL_QUESTION_RULES and 'Zero questions is acceptable' in MEDICAL_QUESTION_RULES
