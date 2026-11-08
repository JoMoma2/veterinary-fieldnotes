"""Exclude obvious consecutive repetition from AI INPUT, never retained transcripts."""
import re

from .util import load_json, write_json, digest_file
from .private import private_path

MARKER = '[CONSECUTIVE REPETITION EXCLUDED — review original transcript]'


def find_runs(segments, threshold=5):
    """Exact normalized token sequences, across segment boundaries, up to 32 words.

    A heuristic, not proof of hallucination. It may exclude genuine repetition.
    Character ranges refer to the existing stripped segment wording, unchanged.
    """
    if threshold < 2:
        raise ValueError('Repetition threshold must be at least two')
    tokens = []
    for index, segment in enumerate(segments):
        for match in re.finditer(r"\w+(?:['’]\w+)*", segment['text'].strip()):
            tokens.append((match.group().casefold().replace('’', "'"), index, match.start(), match.end()))
    values = [t[0] for t in tokens]; spans = {}; runs = []; i = 0
    while i < len(values):
        best = None
        for width in range(1, min(32, (len(values) - i) // threshold) + 1):
            phrase = values[i:i + width]; count = 1
            while values[i + count * width:i + (count + 1) * width] == phrase:
                count += 1
            if count >= threshold and (best is None or count * width > best[0]):
                best = (count * width, count, width)
        if not best:
            i += 1; continue
        length, count, width = best
        run_spans = {}
        for _, segment, start, end in tokens[i:i + length]:
            if segment in run_spans:
                run_spans[segment][1] = end
            else:
                run_spans[segment] = [start, end]
        for segment, span in run_spans.items():
            spans.setdefault(segment, []).append(span)
        runs.append({'firstSegment': tokens[i][1], 'lastSegment': tokens[i + length - 1][1], 'repeats': count, 'phraseTokens': width})
        i += length
    return spans, runs


def extraction_text(block, start=0, end=None):
    end = len(block['text']) if end is None else end
    parts = []; cursor = start
    for a, b in block.get('repeatExcludedSpans', []):
        left, right = max(start, a), min(end, b)
        if left >= right:
            continue
        parts += [block['text'][cursor:left], MARKER]; cursor = right
    parts.append(block['text'][cursor:end])
    return ''.join(parts)


def quote_allowed(block, quote):
    if not quote:
        return False
    start = 0
    while True:
        pos = block['text'].find(quote, start)
        if pos < 0:
            return False
        if not any(max(pos, a) < min(pos + len(quote), b) for a, b in block.get('repeatExcludedSpans', [])):
            return True
        start = pos + 1


def prepare(root, threshold=5):
    root = private_path(root); experiment = load_json(root / 'experiment.json')
    if experiment.get('repetitionExclusionThreshold') == threshold:
        return
    if (root / 'calls/index.json').exists():
        raise ValueError('Do not change repetition policy on completed inference; use a new experiment')
    sources = load_json(root / 'sources.json'); audit = []
    for record in load_json(root / 'recordings.json'):
        path = root / 'transcripts' / (record['id'] + '.json')
        if not path.exists():
            continue
        transcript = load_json(path); spans, runs = find_runs(transcript['segments'], threshold)
        if runs:
            audit.append({'recordingNumber': record['number'], 'runs': runs})
        for key in record['blocks']:
            block = sources[key]; excluded = []
            for span in block['segments']:
                excluded += [[span['from'] + a, span['from'] + b] for a, b in spans.get(span['segment'], [])]
            if excluded:
                block['repeatExcludedSpans'] = excluded
    write_json(root / 'sources.json', sources)
    write_json(root / 'repetition-filter.json', {'threshold': threshold, 'recordings': audit,
               'runsExcluded': sum(len(r['runs']) for r in audit), 'originalTranscriptsUnchanged': True,
               'note': 'Heuristic AI-input exclusion, not a finding that speech was hallucinated.'})
    experiment.update(repetitionExclusionThreshold=threshold, sourcesSha256=digest_file(root / 'sources.json'))
    write_json(root / 'experiment.json', experiment)
