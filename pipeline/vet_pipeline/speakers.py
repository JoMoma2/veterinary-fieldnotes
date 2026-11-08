"""Private, opt-in CPU speaker diarization with shift-scoped anonymous labels.

No identification of real people, role inference, network calls or source writes.
Vectors are recovery data within ONE private experiment, never a cross-shift roster.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import time

from .private import private_path
from .util import digest_file, load_json, write_json, now

SETTINGS = {'chunkSeconds': 600, 'threads': 4, 'localThreshold': .5,
            'matchSimilarity': .75, 'matchMargin': .08, 'version': 'shift-speakers-v1'}


def unit(vector):
    norm = math.sqrt(sum(x * x for x in vector))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError('Invalid speaker embedding')
    return [float(x / norm) for x in vector]


def similarity(left, right):
    if len(left) != len(right):
        raise ValueError('Incompatible speaker embeddings')
    return sum(a * b for a, b in zip(left, right))


def assign_cluster(vector, roster, excluded, settings):
    """A score is similarity, NOT a calibrated identity probability.

    Never merge distinct local speakers from one chunk. An ambiguous match gets a
    fresh anonymous label, preferring a split over a falsely confident identity.
    """
    vector = unit(vector)
    ranked = sorted(((similarity(vector, row['vector']), name) for name, row in roster.items()
                     if name not in excluded), reverse=True)
    if ranked and ranked[0][0] >= settings['matchSimilarity'] and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= settings['matchMargin']):
        score, name = ranked[0]
        # Keep the first reference fixed; avoid progressive centroid/identity drift.
        return name, round(score, 5), 'similarity match; unverified'
    name = f'Speaker_{len(roster) + 1:03d}'
    roster[name] = {'vector': vector}
    return name, None, 'new or ambiguous voice cluster; unverified'


def label_interval(start, end, turns, speech_relative=False):
    """Assign only a clearly dominant voice; do not pretend word-level alignment."""
    if end <= start:
        return {'speaker': 'Unknown', 'candidates': [], 'reason': 'invalid interval'}
    scores = {}
    for turn in turns:
        overlap = max(0, min(end, turn['end']) - max(start, turn['start']))
        if overlap:
            scores[turn['speaker']] = scores.get(turn['speaker'], 0) + overlap
    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    duration = end - start
    if speech_relative:
        # Whisper intervals can contain padding/silence. Judge dominance over
        # detected speech, but retain a minimum coverage floor so a tiny sound
        # cannot label a long, potentially hallucinated transcript passage.
        total = sum(scores.values())
        sufficient = total >= min(.5, duration * .7) and total / duration >= .2
        if sufficient and ranked and ranked[0][0] != 'Unknown' and ranked[0][1] / total >= .85:
            return {'speaker': ranked[0][0], 'candidates': [name for name, _ in ranked],
                    'reason': 'dominant detected speech; padding excluded; unverified',
                    'detectedSpeechFraction': round(min(total / duration, 1), 3)}
        return {'speaker': 'Mixed/uncertain' if len(ranked) > 1 else 'Unknown',
                'candidates': [name for name, _ in ranked], 'reason': 'insufficient or competing detected speech',
                'detectedSpeechFraction': round(min(total / duration, 1), 3)}
    if ranked and ranked[0][0] != 'Unknown' and ranked[0][1] / duration >= .75 and (len(ranked) == 1 or ranked[1][1] / duration <= .15):
        return {'speaker': ranked[0][0], 'candidates': [name for name, _ in ranked], 'reason': 'dominant diarized voice; unverified'}
    return {'speaker': 'Mixed/uncertain' if len(ranked) > 1 else 'Unknown',
            'candidates': [name for name, _ in ranked], 'reason': 'insufficient or competing speaker coverage'}


class CpuDiarizer:
    def __init__(self, models, settings):
        import sherpa_onnx as so
        config = so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=models['segmentation'], window_shift_ratio=.1),
                num_threads=settings['threads'], provider='cpu'),
            embedding=so.SpeakerEmbeddingExtractorConfig(model=models['embedding'], num_threads=settings['threads'], provider='cpu'),
            clustering=so.FastClusteringConfig(num_clusters=-1, threshold=settings['localThreshold']),
            min_duration_on=.3, min_duration_off=.5)
        if not config.validate():
            raise ValueError('Invalid local speaker model configuration')
        self.diarizer = so.OfflineSpeakerDiarization(config)
        self.extractor = so.SpeakerEmbeddingExtractor(config.embedding)
        if self.diarizer.sample_rate != 16000:
            raise ValueError('Speaker backend requires 16 kHz')

    def process(self, samples, callback):
        import numpy as np
        turns = [{'start': float(row.start), 'end': float(row.end), 'localSpeaker': int(row.speaker)}
                 for row in self.diarizer.process(samples, callback=callback).sort_by_start_time()]
        embeddings = {}
        for speaker in sorted({row['localSpeaker'] for row in turns}):
            clean = [row for row in turns if row['localSpeaker'] == speaker and row['end'] - row['start'] >= 1.5
                     and not any(other['localSpeaker'] != speaker and max(row['start'], other['start']) < min(row['end'], other['end']) for other in turns)]
            vectors = []
            for row in sorted(clean, key=lambda row: row['end'] - row['start'], reverse=True)[:3]:
                start = int(row['start'] * 16000); end = min(len(samples), int(min(row['end'], row['start'] + 12) * 16000))
                if end - start < 16000:
                    continue
                stream = self.extractor.create_stream()
                stream.accept_waveform(sample_rate=16000, waveform=np.ascontiguousarray(samples[start:end]))
                stream.input_finished()
                if self.extractor.is_ready(stream):
                    vectors.append(unit(self.extractor.compute(stream)))
            if vectors:
                embeddings[str(speaker)] = unit(np.mean(vectors, axis=0).tolist())
        return {'turns': turns, 'embeddings': embeddings}


def run(root, model_manifest, engine=None, settings=None):
    """Checkpoint independent ten-minute chunks; deterministic relabeling on resume."""
    import soundfile as sf
    root = private_path(root); settings = dict(settings or SETTINGS)
    manifest = private_path(model_manifest); models = load_json(manifest)
    hashes = {name: digest_file(Path(models[name])) for name in ['segmentation', 'embedding']}
    identity = {'settings': settings, 'modelHashes': hashes}
    binding = root / 'speaker-session.json'
    if binding.exists() and load_json(binding) != identity:
        raise ValueError('Immutable speaker settings/models changed; use a new experiment')
    write_json(binding, identity)
    roster = {}; all_turns = {}; failed = []; completed = 0; total_seconds = 0
    engine = engine or CpuDiarizer(models, settings)
    records = load_json(root / 'recordings.json'); experiment = load_json(root / 'experiment.json')
    progress = {'status': 'running', 'recordings': len(records), 'completedChunks': 0, 'startedAt': now()}
    write_json(root / 'speaker-progress.json', progress)
    for number, record in enumerate(records, 1):
        rid = record['id']; path = root / 'inputs' / (rid + '.wav'); assigned = []
        try:
            expected = experiment['audio'][rid]['sha256']
            if digest_file(path) != expected:
                raise ValueError('Retained speaker input changed')
            with sf.SoundFile(path) as audio:
                if audio.samplerate != 16000 or audio.channels != 1:
                    raise ValueError('Use retained mono 16 kHz workspace audio, never alter the recorder')
                frames = settings['chunkSeconds'] * 16000
                total_seconds += len(audio) / 16000
                for part, start in enumerate(range(0, len(audio), frames)):
                    key = f'{rid}-{part:04d}'
                    fingerprint = hashlib.sha256(json.dumps([identity, expected, start, min(frames, len(audio) - start)], sort_keys=True).encode()).hexdigest()
                    target = root / 'speaker-chunks' / (key + '.json')
                    progress.update(recordingNumber=number, chunk=part + 1, completedChunks=completed)
                    if target.exists():
                        cached = load_json(target)
                        if cached['fingerprint'] != fingerprint:
                            raise ValueError('Immutable speaker checkpoint mismatch')
                    else:
                        audio.seek(start); samples = audio.read(min(frames, len(audio) - start), dtype='float32')
                        last_progress = [0.0]
                        def callback(done, total):
                            if time.monotonic() - last_progress[0] > 5:
                                progress.update(chunkProgress=round(done / max(total, 1), 3), updatedAt=now())
                                write_json(root / 'speaker-progress.json', progress); last_progress[0] = time.monotonic()
                            return 0
                        attempt_file = root / 'speaker-chunks' / (key + '-attempts.json')
                        attempts = load_json(attempt_file).get('attempts', 0) if attempt_file.exists() else 0
                        last_error = None
                        for attempt in range(attempts, 3):
                            write_json(attempt_file, {'attempts': attempt + 1})
                            begun = time.monotonic()
                            try:
                                cached = {'fingerprint': fingerprint, **engine.process(samples, callback), 'seconds': round(time.monotonic() - begun, 3)}
                                write_json(target, cached); last_error = None; break
                            except Exception as error:
                                last_error = type(error).__name__
                                write_json(attempt_file, {'attempts': attempt + 1, 'errorClass': last_error})
                        if last_error or not target.exists():
                            failed.append({'recordingNumber': number, 'chunk': part + 1, 'errorClass': last_error or 'exhausted attempts'})
                            continue
                    used = set(); mapping = {}
                    local_order = list(dict.fromkeys(row['localSpeaker'] for row in cached['turns']))
                    for local in local_order:
                        vector = cached['embeddings'].get(str(local))
                        if vector:
                            speaker, score, reason = assign_cluster(vector, roster, used, settings)
                            used.add(speaker)
                        else:
                            speaker, score, reason = 'Unknown', None, 'no sufficiently long clean voice sample'
                        mapping[local] = (speaker, score, reason)
                    for turn in cached['turns']:
                        speaker, score, reason = mapping[turn['localSpeaker']]
                        assigned.append({'start': turn['start'] + start / 16000, 'end': turn['end'] + start / 16000,
                                         'speaker': speaker, 'similarity': score, 'basis': reason})
                    completed += 1
        except Exception as error:
            failed.append({'recordingNumber': number, 'errorClass': type(error).__name__})
        all_turns[rid] = assigned
        write_json(root / 'speaker-labels.json', {'scope': 'this shift only; unverified voice clusters', 'speakers': list(roster),
                                                'turns': all_turns, 'failed': failed})
        progress.update(recordingsCompleted=number, completedChunks=completed, speakers=len(roster), updatedAt=now())
        write_json(root / 'speaker-progress.json', progress)
        render(root)
    progress.update(status='complete-with-failures' if failed else 'complete', completedChunks=completed,
                    audioSeconds=round(total_seconds, 3), failed=failed, finishedAt=now())
    write_json(root / 'speaker-progress.json', progress)
    render(root)


def annotate(root):
    """Add reversible voice metadata without changing original words or offsets."""
    root = private_path(root); labels = load_json(root / 'speaker-labels.json')
    sources = load_json(root / 'sources.json'); experiment = load_json(root / 'experiment.json')
    relative = experiment.get('speakerAlignment') == 'detected-speech-v2'
    for block in sources.values():
        turns = labels['turns'].get(block['recordingId'], [])
        block['speakerSegments'] = [{**span, **label_interval(span['startSeconds'], span['endSeconds'], turns, relative)} for span in block['segments']]
    write_json(root / 'sources.json', sources)
    experiment.update(sourcesSha256=digest_file(root / 'sources.json'), speakerLabels=True, medicalOnlyQuestions=True)
    write_json(root / 'experiment.json', experiment)


def render(root):
    import html
    from .shift_context_report import SCRIPT
    import base64
    root = private_path(root); e = lambda text: html.escape(str(text), quote=True)
    labels = load_json(root / 'speaker-labels.json') if (root / 'speaker-labels.json').exists() else {'speakers': [], 'turns': {}}
    progress = load_json(root / 'speaker-progress.json')
    body = '<h1>Shift speaker review</h1><p>Private, unverified anonymous voice clusters. Labels are not confirmed identities, roles or patient relationships. No permanent client/coworker roster was created.</p>'
    body += '<p>Status: ' + e(progress['status']) + '; completed recordings: ' + e(progress.get('recordingsCompleted', 0)) + '/' + e(progress['recordings']) + '; anonymous clusters: ' + e(len(labels['speakers'])) + '.</p><p><a href="shift-context.html">Medical notes and study questions</a></p>'
    body += '<audio id="player" controls preload="none"></audio><p id="player-label"></p><p id="player-status"></p>'
    markdown = ['# Private shift speaker review', '', 'Unverified voice clusters, not identified people. No cross-shift roster.', '']
    if (root / 'global-speaker-groups.json').exists():
        audit = load_json(root / 'global-speaker-groups.json')
        body += '<p><strong>Whole-shift grouping:</strong> ' + str(audit['localVoiceGroups']) + ' local voice groups compared together; ' + str(audit['globalGroups']) + ' resulting clusters; ' + str(audit['groupsSpanningRecordings']) + ' clusters span multiple recordings. Counts are not verified people or accuracy.</p>'
        markdown += [f"Whole-shift groups: {audit['globalGroups']}; groups spanning recordings: {audit['groupsSpanningRecordings']}. Not verified people or accuracy.", '']
    if (root / 'owner-reference-checks.json').exists():
        checks = load_json(root / 'owner-reference-checks.json')
        body += '<h2>Owner-confirmed reference checks</h2><p>' + e(checks['note']) + '</p>'
        markdown += ['## Owner-confirmed reference checks', checks['note'], '']
        for check in checks['checks']:
            line = f"Recording {check['recording']} {check['start']:.2f}–{check['end']:.2f}s: " + (', '.join(check['detectedVoiceGroups']) or 'No detected voice') + f"; {check['detectedSpeechSeconds']:.2f}s detected speech."
            body += '<p>' + e(line) + '</p>'; markdown += [line]
        line = 'Clear references across files agree: ' + ('yes' if checks['clearReferencesAgree'] else 'not established — review needed')
        body += '<p><strong>' + e(line) + '</strong></p>'; markdown += [line, '']
    for record in load_json(root / 'recordings.json'):
        rid = record['id']; turns = labels['turns'].get(rid)
        if turns is None:
            continue
        body += '<details><summary>Recording ' + str(record['number']) + ' — ' + e(record['name']) + '</summary>'
        markdown += ['## Recording ' + str(record['number']), '']
        transcript = root / 'transcripts' / (rid + '.json')
        segments = load_json(transcript)['segments'] if transcript.exists() else []
        relative = load_json(root / 'experiment.json').get('speakerAlignment') == 'detected-speech-v2'
        rows = [dict(segment, **label_interval(segment['start'], segment['end'], turns, relative)) for segment in segments]
        if not rows:
            rows = [dict(turn, text='No valid parsed transcript; listen to this audio interval.') for turn in turns]
        for row in rows:
            label = row['speaker']; start = row['start']; end = row['end']
            body += '<p><strong>' + e(f'{start:.2f}–{end:.2f}s · {label}') + '</strong> ' + e(row['text']) + ' <button data-audio="../inputs/' + e(rid) + '.wav" data-start="' + str(start) + '" data-label="Recording ' + str(record['number']) + '">Listen</button></p>'
            markdown += [f"{start:.2f}–{end:.2f}s [{label}] {row['text']}", '']
        body += '</details>'
    sha = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = "default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; script-src 'sha256-" + sha + "'; base-uri 'none'; form-action 'none'"
    document = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="' + e(csp) + '"><title>Private speaker review</title><style>body{max-width:1100px;margin:auto;padding:24px;font:17px/1.6 system-ui;background:#faf8f2;overflow-wrap:anywhere}audio{width:100%}details{padding:12px;margin:12px 0;background:white}button{cursor:pointer;font:inherit}summary{cursor:pointer}</style></head><body>' + body + '<script>' + SCRIPT + '</script></body></html>'
    from .util import atomic_write
    atomic_write(root / 'review/speakers.html', document)
    atomic_write(root / 'speaker-transcript.md', '\n'.join(markdown))
    from .review_export import export
    export(root)
