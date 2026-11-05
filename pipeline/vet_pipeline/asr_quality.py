"""Deterministic review screens, not medical accuracy or speech-coverage scores."""
from collections import Counter
import math
import re


class TranscriptionReviewRequired(Exception):
    """Retained ASR needs owner review; identical automatic retries won't help."""


def assess_segments(segments, duration=None):
    normalized = [re.sub(r'\W+', ' ', str(s.get('text', '')).casefold()).strip() for s in segments]
    counts = Counter(t for t in normalized if t)
    biggest = max(counts.values(), default=0)
    nonempty = sum(bool(t) for t in normalized)
    longest = run = 0
    previous = None
    invalid = []
    overrun = []
    internal = []
    last = -1
    for index, (s, text) in enumerate(zip(segments, normalized)):
        run = run + 1 if text and text == previous else int(bool(text))
        longest = max(longest, run)
        previous = text
        a, b = s.get('start'), s.get('end')
        valid = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in [a, b])
        if not valid or a < 0 or b <= a or a < last:
            invalid.append(index)
        if valid:
            if duration is not None and (a >= duration or b > duration + 1):
                overrun.append(index)
            last = a
        tokens = text.split()
        if len(tokens) >= 40:
            grams = Counter(tuple(tokens[i:i + 4]) for i in range(len(tokens) - 3))
            if max(grams.values(), default=0) >= 10 and len(set(tokens)) / len(tokens) < .25:
                internal.append(index)
    reasons = []
    if longest >= 8 or (biggest >= 20 and biggest / max(nonempty, 1) >= .2) or internal:
        reasons.append('Severe repeated-phrase pattern; compare with audio before using as knowledge')
    if invalid:
        reasons.append('Invalid or unordered source timestamps; no offsets were invented or repaired')
    if overrun:
        reasons.append('Source timestamps exceed audio duration; review original Whisper output')
    if not nonempty:
        reasons.append('No nonempty speech text was retained')
    return {'schemaVersion': 1, 'reviewRequired': bool(reasons), 'reasons': reasons,
            'segments': len(segments), 'uniqueNormalizedPhrases': len(counts),
            'maximumPhraseRepeats': biggest, 'longestConsecutiveRepeat': longest,
            'invalidTimestampSegments': invalid, 'outOfBoundsSegments': overrun,
            'withinSegmentLoopIndices': internal,
            'note': 'Heuristic screening only. Repetition can be real; absence of a flag does not establish transcription accuracy.'}


def assess_whisper(raw, duration):
    segments = []
    for entry in raw.get('transcription', []):
        if not str(entry.get('text', '')).strip():
            continue
        offsets = entry.get('offsets', {})
        a, b = offsets.get('from'), offsets.get('to')
        segments.append({'text': entry.get('text', ''),
                         'start': a / 1000 if isinstance(a, (int, float)) else None,
                         'end': b / 1000 if isinstance(b, (int, float)) else None})
    return assess_segments(segments, duration)
