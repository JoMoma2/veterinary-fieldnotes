"""Isolated transcript-only owner matching. Local CPU; no LLM, ASR or publication.

Reuses whole-shift anonymous groups and detected turns. Owner decisions are made
on individual clean speech windows, never inherited from a whole old cluster.
"""
from __future__ import annotations
import hashlib, html, json, os, shutil, time
from pathlib import Path
from .private import private_path, initialize_private
from .locations import local_path
from .speakers import unit, similarity, label_interval
from .voice_reference import score
from .util import load_json, write_json, digest_file, atomic_write, now, lock

POLICY = {'version': 'owner-transcript-windows-v1', 'minimumSeconds': 3, 'windowSeconds': 8,
          'minimumSimilarity': .55, 'negativeMargin': .08, 'maximumOverlap': .1,
          'referenceRmsQuantile': .5, 'threads': 4}


def decision(vector, templates, negatives, threshold, margin=.08):
    positive = score(vector, templates)['supportedSimilarity']
    negative = max((similarity(unit(vector), unit(v)) for v in negatives), default=-1)
    match = positive is not None and positive >= threshold and positive - negative >= margin
    return {'ownerCandidate': match, 'supportedSimilarity': positive,
            'nearestNegativeSimilarity': round(negative, 5), 'identityVerified': False}


def windows(turns, seconds, policy):
    """Do not identify short or overlapping speech by voice proximity alone."""
    for turn in turns:
        a, end = max(0, turn['start']), min(seconds, turn['end'])
        while a < end:
            b = min(end, a + policy['windowSeconds'])
            overlap = sum(max(0, min(b, o['end']) - max(a, o['start']))
                          for o in turns if o['localSpeaker'] != turn['localSpeaker'])
            yield {**turn, 'start': a, 'end': b, 'eligible': b-a >= policy['minimumSeconds']
                   and overlap / max(b-a, .001) <= policy['maximumOverlap']}
            a = b


def prepare(reference, comparison, labels, manifest, directory, visible, owner_label="Owner"):
    reference, comparison, labels, manifest = map(private_path, [reference, comparison, labels, manifest])
    profile = load_json(reference / 'candidate-profile.json'); attestation = load_json(reference / 'attestation.json')
    if not attestation.get('ownerOnlySpeechConfirmed') or attestation['profileSha256'] != digest_file(reference / 'candidate-profile.json'):
        raise ValueError('Owner-only reference confirmation required')
    pack = load_json(reference / 'calibration/pack.json'); answers = load_json(labels)
    if answers.get('version') != 1 or answers.get('packSha256') != digest_file(reference / 'calibration/pack.json'):
        raise ValueError('Owner labels do not match the calibration pack')
    if any(v not in ['owner', 'other', 'mixed', 'unsure'] for v in answers['answers'].values()):
        raise ValueError('Invalid calibration labels')
    if set(answers['answers']) - {c['id'] for c in pack['cases']}:
        raise ValueError('Unknown calibration clip')
    model = private_path(load_json(manifest)['embedding'])
    if digest_file(model) != profile['binding']['models']['embedding']:
        raise ValueError('Incompatible owner reference model')
    experiment = load_json(comparison / 'experiment.json')
    segmentation = private_path(experiment['referenceExperiment'])
    root = initialize_private(directory); visible = private_path(visible)
    records = load_json(comparison / 'recordings.json')
    for name in ['inputs', 'transcripts', 'transcription-details', 'checkpoints', 'review']:
        (root / name).mkdir(mode=0o700)
    for record in records:
        rid = record['id']
        for folder, suffix in [('inputs', '.wav'), ('transcripts', '.json'), ('transcription-details', '.json')]:
            source = comparison / folder / (rid + suffix)
            if not source.exists(): continue
            target = root / folder / source.name
            if folder == 'inputs':
                if digest_file(source) != experiment['audio'][rid]['sha256']:
                    raise ValueError('Source audio changed')
                try: os.link(source, target)
                except OSError: shutil.copy2(source, target)
            else: shutil.copy2(source, target)
    write_json(root / 'recordings.json', records)
    write_json(root / 'display-settings.json', {'ownerLabel': owner_label})
    session = {'version': POLICY['version'], 'policy': POLICY, 'reference': str(reference),
               'comparison': str(comparison), 'segmentation': str(segmentation), 'labels': str(labels),
               'model': str(model), 'visible': str(visible), 'profileSha256': digest_file(reference / 'candidate-profile.json'),
               'labelsSha256': digest_file(labels), 'packSha256': digest_file(reference / 'calibration/pack.json'),
               'modelSha256': digest_file(model), 'groupsSha256': digest_file(comparison / 'global-speaker-groups.json'),
               'chunkSeconds': load_json(segmentation / 'speaker-session.json')['settings']['chunkSeconds'],
               'audio': experiment['audio'], 'createdAt': now()}
    write_json(root / 'session.json', session)
    write_json(root / 'progress.json', {'status': 'prepared', 'completed': 0, 'recordings': len(records)})
    render(root)
    return root


def embed(extractor, samples, rate=16000):
    import numpy as np
    stream = extractor.create_stream()
    stream.accept_waveform(sample_rate=rate, waveform=np.ascontiguousarray(samples)); stream.input_finished()
    return unit(extractor.compute(stream)) if extractor.is_ready(stream) else None


def calibration(root, session, extractor):
    import soundfile as sf
    reference = private_path(session['reference']); profile = load_json(reference / 'candidate-profile.json')
    if digest_file(reference / 'candidate-profile.json') != session['profileSha256'] or digest_file(private_path(session['labels'])) != session['labelsSha256']:
        raise ValueError('Immutable owner inputs changed')
    templates = sorted(profile['templates'], key=lambda t: t['rms'])
    templates = templates[:max(3, int(len(templates) * session['policy']['referenceRmsQuantile']))]
    pack_path = reference / 'calibration/pack.json'
    if digest_file(pack_path) != session['packSha256']:
        raise ValueError('Listening pack changed')
    pack = load_json(pack_path); labels = load_json(private_path(session['labels']))['answers']; vectors = {}; negatives = []
    for case in pack['cases']:
        path = reference / 'calibration' / (case['id'] + '.wav')
        if digest_file(path) != case['clipSha256']: raise ValueError('Calibration audio changed')
        audio, rate = sf.read(path, dtype='float32')
        if rate != 16000 or audio.ndim != 1: raise ValueError('Calibration audio format changed')
        vector = embed(extractor, audio)
        if vector is not None:
            vectors[case['id']] = vector
            if labels.get(case['id']) == 'other': negatives.append(vector)
    if not negatives: raise ValueError('Explicit other-speaker listening labels required for this pilot')
    # Small selected calibration set constrains this experiment; it is not an accuracy test.
    negative_scores = [score(v, templates)['supportedSimilarity'] for v in negatives]
    threshold = max(session['policy']['minimumSimilarity'], max(s for s in negative_scores if s is not None) + .05)
    rows = []
    for case in pack['cases']:
        truth = labels.get(case['id'])
        if case['id'] in vectors:
            rows.append({'id': case['id'], 'truth': truth, **decision(vectors[case['id']], templates, negatives, threshold, session['policy']['negativeMargin'])})
    write_json(root / 'calibration.json', {'threshold': threshold, 'referenceTemplates': len(templates), 'rows': rows,
        'note': 'Selected labels constrain thresholds and negative vetoes: these are NOT independent validation or a population error rate. Low-RMS reference subset is provisional, not a guarantee of clean speech. Mixed/unsure examples never become binary negatives.'})
    return templates, negatives, threshold


def run(root):
    import soundfile as sf
    import sherpa_onnx as so
    root = private_path(root); started = time.monotonic()
    with lock(root):
        owner_label = load_json(root / 'display-settings.json').get('ownerLabel', 'Owner') if (root / 'display-settings.json').exists() else 'Owner'
        session = load_json(root / 'session.json'); comparison = private_path(session['comparison']); segmentation = private_path(session['segmentation'])
        if digest_file(private_path(session['model'])) != session['modelSha256'] or digest_file(comparison / 'global-speaker-groups.json') != session['groupsSha256']:
            raise ValueError('Frozen model/grouping changed')
        extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=str(private_path(session['model'])), num_threads=4, provider='cpu'))
        templates, negatives, threshold = calibration(root, session, extractor)
        groups = load_json(comparison / 'global-speaker-groups.json')['groups']
        mapping = {(m['chunk'], m['localSpeaker']): g['speaker'] for g in groups for m in g['members']}
        records = load_json(root / 'recordings.json'); progress = {'status': 'running', 'recordings': len(records), 'completed': 0, 'startedAt': now(), 'failed': []}
        write_json(root / 'progress.json', progress)
        for record in records:
            rid = record['id']; target = root / 'checkpoints' / (rid + '.json')
            caches = sorted((segmentation / 'speaker-chunks').glob(rid + '-[0-9][0-9][0-9][0-9].json'))
            binding = {'sessionSha256': digest_file(root / 'session.json'), 'chunks': {p.name: digest_file(p) for p in caches},
                       'transcriptSha256': digest_file(root / 'transcripts' / (rid + '.json')) if (root / 'transcripts' / (rid + '.json')).exists() else None}
            if target.exists():
                if load_json(target)['binding'] != binding: raise ValueError('Saved transcript-only checkpoint changed')
                progress['completed'] += 1; continue
            attempts_file = target.with_suffix('.attempts.json'); attempts = load_json(attempts_file).get('attempts', 0) if attempts_file.exists() else 0
            last_error = None
            for attempt in range(attempts, 3):
                write_json(attempts_file, {'attempts': attempt + 1})
                try:
                    audio = root / 'inputs' / (rid + '.wav')
                    if digest_file(audio) != session['audio'][rid]['sha256']: raise ValueError('Retained audio changed')
                    turns = []
                    with sf.SoundFile(audio) as source:
                        if source.samplerate != 16000 or source.channels != 1: raise ValueError('Use retained mono16k audio')
                        for cache in caches:
                            offset = int(cache.stem.rsplit('-', 1)[1]) * session['chunkSeconds']
                            detected = load_json(cache)['turns']; duration = min(session['chunkSeconds'], len(source)/16000-offset)
                            for w in windows(detected, duration, session['policy']):
                                a, b = w['start'] + offset, w['end'] + offset
                                row = {'start': a, 'end': b, 'speaker': mapping.get((cache.stem, w['localSpeaker']), 'Unknown'),
                                       'ownerCandidate': False, 'basis': 'Previous unverified whole-shift voice group; not proof of another person'}
                                if w['eligible']:
                                    source.seek(round(a*16000)); samples = source.read(round((b-a)*16000), dtype='float32')
                                    vector = embed(extractor, samples)
                                    if vector is not None:
                                        row.update(decision(vector, templates, negatives, threshold, session['policy']['negativeMargin']))
                                        if row['ownerCandidate']: row.update(speaker=owner_label + ' (voice match — unverified)', basis='Multiple enrolled-reference window matches with labelled-other voice veto; not a probability')
                                turns.append(row)
                    write_json(target, {'binding': binding, 'recordingNumber': record['number'], 'turns': turns,
                        'note': 'No identity propagation from old whole-chunk/whole-cluster labels; no transcript wording changed.'})
                    last_error = None; break
                except Exception as error:
                    last_error = type(error).__name__; write_json(attempts_file, {'attempts': attempt + 1, 'errorClass': last_error})
            if last_error or not target.exists():progress['failed'].append({'recordingNumber': record['number'], 'errorClass': last_error or 'ExhaustedAttempts'})
            else: progress['completed'] += 1
            progress.update(recordingNumber=record['number'], elapsedSeconds=round(time.monotonic()-started, 2), updatedAt=now())
            write_json(root / 'progress.json', progress); render(root)
        progress.update(status='complete-with-failures' if progress['failed'] else 'complete', finishedAt=now(), elapsedSeconds=round(time.monotonic()-started, 2))
        write_json(root / 'progress.json', progress); render(root)


def render(root):
    root = private_path(root); session = load_json(root / 'session.json'); progress = load_json(root / 'progress.json')
    e = lambda x: html.escape(str(x), quote=True)
    notice = 'Private transcript-only pilot. Saved Whisper wording/timestamps reused unchanged. Owner voice matches and anonymous groups remain uncertain; different labels can be one person and one old group can contain multiple people. No knowledge extraction, questions, uploads or publication.'
    body = '<h1>Last shift — calibrated speaker transcripts</h1><p>' + e(notice) + '</p><p><strong>Status: ' + e(progress['status']) + '</strong> · speaker matching completed for ' + str(progress['completed']) + '/' + str(progress['recordings']) + ' recordings. Refresh for progress.</p><audio id="player" controls preload="none"></audio><p id="listening"></p>'
    text = ['# Last shift — calibrated speaker transcripts', '', notice, '', 'Status: ' + progress['status'], '']
    for record in load_json(root / 'recordings.json'):
        rid = record['id']; checkpoint = root / 'checkpoints' / (rid + '.json')
        turns = load_json(checkpoint)['turns'] if checkpoint.exists() else []
        owner_label = load_json(root / 'display-settings.json').get('ownerLabel', 'Owner') if (root / 'display-settings.json').exists() else 'Owner'
        turns = [dict(t, speaker=owner_label + ' (voice match — unverified)') if t.get('ownerCandidate') else t for t in turns]
        title = 'Recording ' + str(record['number'])
        audio = root / 'inputs' / (rid + '.wav')
        body += '<section><h2>' + title + '</h2><p>' + e(record['name']) + ' · ' + ('Speaker matching saved' if checkpoint.exists() else 'Speaker matching pending or failed') + '</p>'
        text += ['## ' + title, '']
        parsed = root / 'transcripts' / (rid + '.json')
        if not parsed.exists():
            message = 'No usable saved parsed transcript. Original audio remains available; this speaker-only run does not rerun Whisper or invent missing text.'
            body += '<p class="warn">' + message + '</p>'; text += [message, '']
            raw = root / 'transcription-details' / (rid + '.json')
            if raw.exists():
                body += '<h3>Unvalidated raw Whisper text — timing and speakers unassigned</h3>'
                text += ['### Unvalidated raw Whisper text — timing and speakers unassigned', '']
                for span in load_json(raw).get('transcription', []):
                    wording = span.get('text', '')
                    if isinstance(wording, str):
                        body += '<p>' + e(wording) + '</p>'; text += [wording, '']
        else:
            transcript = load_json(parsed)
            if record.get('status') == 'context-only-ASR-warning' or transcript.get('transcriptionQuality', {}).get('reviewRequired'):
                body += '<p class="warn">Original ASR warning: compare with audio. Repetitions/uncertain words remain preserved.</p>'
            for segment in transcript['segments']:
                info = label_interval(segment['start'], segment['end'], turns, True)
                line = f"{segment['start']:.2f}–{segment['end']:.2f}s [{info['speaker']}] "
                body += '<p><button data-audio="' + e(audio.as_uri()) + '" data-start="' + str(segment['start']) + '">' + e(line) + '</button> ' + e(segment['text']) + '</p>'
                text += [line + segment['text'], '']
        if audio.exists():body += '<p><a href="' + e(audio.as_uri()) + '">Open retained audio</a></p>'
        body += '</section>'
    script = "document.addEventListener('click',e=>{const b=e.target.closest('button[data-audio]');if(!b)return;const a=document.getElementById('player');if(a.getAttribute('src')!==b.dataset.audio){a.preload='metadata';a.src=b.dataset.audio;a.load();}const seek=()=>{a.currentTime=Number(b.dataset.start);a.play().catch(()=>{document.getElementById('listening').textContent='Press Play to listen.';});};if(a.readyState)seek();else a.addEventListener('loadedmetadata',seek,{once:true});a.scrollIntoView({block:'center'});});"
    sha = __import__('base64').b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = "default-src 'none'; style-src 'unsafe-inline'; media-src file:; script-src 'sha256-" + sha + "'; base-uri 'none'; form-action 'none'"
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="' + e(csp) + '"><title>Private speaker transcripts</title><style>body{max-width:1080px;margin:auto;padding:24px;font:17px/1.7 system-ui;background:#faf8f2;color:#18332f}section{padding:18px;background:white;border:1px solid #c6d4cc;border-radius:12px;margin:20px 0}button{font:inherit;color:#12634d;cursor:pointer;text-align:left}audio{width:100%}.warn{border-left:4px solid #a75b24;padding:12px}p{overflow-wrap:anywhere;white-space:pre-wrap}</style>' + body + '<script>' + script + '</script></html>'
    atomic_write(root / 'review/index.html', document); atomic_write(root / 'Transcript.md', '\n'.join(text))
    visible = private_path(session['visible']); visible.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(visible / 'Results.html', document); atomic_write(visible / 'Transcript.md', '\n'.join(text))
