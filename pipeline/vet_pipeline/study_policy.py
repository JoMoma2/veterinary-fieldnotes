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


def question_rejection(question, patient_labels=()):
    """Conservative obvious-violation filter, not a semantic medical classifier."""
    prompt = question.get('prompt', '').strip()
    answer = question.get('answer', '').strip()
    text = prompt + ' ' + answer + ' ' + question.get('explanation', '')
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
