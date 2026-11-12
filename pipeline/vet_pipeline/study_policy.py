"""Study selection policy: transferable medical knowledge, never case memory.

The prompt does semantic selection. This small deterministic screen catches obvious
violations; passing it is NOT a guarantee of medical correctness or relevance.
"""
import re


MEDICAL_QUESTION_RULES = """STUDY QUESTION POLICY:
Generate only self-contained questions about transferable veterinary MEDICAL knowledge.
Think of a question whose subject and answer could be looked up in a veterinary
medical reference, without access to this shift, transcript or patient's record.
The learner must not need to recognize a patient, speaker, date or earlier discussion.
A case may supply a medical concept; the question AND answer must stand independently
of that case. Do not extrapolate a single patient's finding into a general medical fact.
No case studies, clinical vignettes, patient-specific diagnoses/treatments/outcomes,
case-history recall, transcript quotation completion, personal names or shift trivia.
No questions about nonmedical equipment operation, hospital workflows or conversations.
Only ask when the source explicitly supports a general medical principle and enough
context to make the answer fair and unambiguous. Do not add textbook facts from memory.
If the source is unclear, contradictory, anecdotal or only describes what happened
to one patient, keep useful notes but omit the question. Zero questions is acceptable.
Use precise medical language and a useful explanatory answer. Do not generate questions
just to fill a quota. Source grounding is not external medical verification.
"""

QUESTION_FORMAT_RULES = """QUESTION FORMATS:
Choose flashcard, multiple-choice, or multiple-select to suit the learning point.
Use a variety when the material supports it; do not force a format or a quota.
Flashcards have a prompt, answer and explanation. Multiple-choice has one correct
option and at least three plausible but clearly incorrect distractors. Multiple-select
should have several correct options and at least one incorrect option; say "Select
all that apply" in its prompt. Give options distinct lowercase hyphenated IDs.
Correct answers must be grounded in the cited source. Options must be unambiguous
under the stated conditions; explain why the correct choices fit and the others do
not. Do not introduce unsupported clinical assertions to manufacture distractors.
When the source cannot support fair answer choices, use a flashcard or omit the
question. The existing medical-only and source-evidence rules still apply.
"""


def question_options(question):
    if question.get('format') == 'multiple-choice':
        return [question['correct'], *question['distractors']]
    return question.get('choices', [])


def question_answer(question):
    if question.get('format') == 'multiple-choice':
        return question['correct']['text']
    if question.get('format') == 'multiple-select':
        return '; '.join(x['text'] for x in question['choices'] if x['id'] in question['correctIds'])
    return question.get('answer', '')


def question_rejection(question, patient_labels=()):
    """Conservative obvious-violation filter, not a semantic medical classifier."""
    prompt = question.get('prompt', '').strip()
    answer = question_answer(question).strip()
    options = question_options(question)
    if options:
        ids = [x['id'] for x in options]
        words = [x['text'].strip().casefold() for x in options]
        if len(set(ids)) != len(ids) or len(set(words)) != len(words) or not all(words):
            return 'Question options need distinct IDs and nonempty distinct text'
        if question.get('format') == 'multiple-select':
            correct = question['correctIds']
            if not correct or len(set(correct)) != len(correct) or not set(correct) < set(ids):
                return 'Multiple-select needs known correct IDs and an incorrect option'
    text = prompt + ' ' + answer + ' ' + question.get('explanation', '') + ' ' + ' '.join(x['text'] for x in options)
    if not prompt or not answer:
        return 'Question or answer is empty'
    if re.search(r'\b(source recall|complete (?:the |this )?(?:recorded |following )?(?:statement|quote|sentence)|what was (?:said|recorded)|according to (?:the |this )?(?:transcript|recording|shift|discussion)|speaker[_ -]?\d+|case (?:study|scenario|id)|this (?:dog|cat|patient)|that (?:dog|cat|patient)|the (?:patient|dog|cat)\x27s (?:name|diagnosis|outcome))\b', text, re.I):
        return 'Question depends on a source conversation or individual case'
    if re.search(r'\b\d+[ -](?:year|month|week)[ -]old\b', prompt, re.I):
        return 'Question uses a case vignette'
    if re.search(r'\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b', text, re.I):
        return 'Question contains a case date'
    if any(label and re.search(r'(?<!\w)' + re.escape(label) + r'(?!\w)', text, re.I) for label in patient_labels):
        return 'Question contains a known patient label'
    return None
