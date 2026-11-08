"""Owner-only voice-reference candidates and model-free comparison.

No clinical ingestion/extraction, network calls, global voice registry or changes
to existing shift speaker labels. Only an explicit attestation enrolls candidates.
"""
from __future__ import annotations
import base64
import hashlib
import html
import json
import os
from pathlib import Path
from .locations import local_path
import shutil
import time

from .private import private_path
from .speakers import CpuDiarizer, SETTINGS, unit, similarity
from .util import load_json, write_json, digest_file, atomic_write, now, lock

VERSION = 'private-owner-reference-v1'


def prepare(source, directory, library_workspace):
    """Copy a reference without device writes, then prevent ordinary ingestion.

    Pause ordinary importing BEFORE connecting/calling this. If a knowledge job
    already exists registration stops safely, preserving the copied reference.
    """
    from .private import initialize_private
    from .source_purpose import register_reference
    source = local_path(source).expanduser().resolve()
    if source.suffix.lower() != '.wav' or not source.is_file():
        raise ValueError('Expected an existing owner-reference WAV')
    root = initialize_private(directory); before = source.stat()
    temporary = root / 'reference-original.wav.copying'
    shutil.copy2(source, temporary); temporary.chmod(0o600)
    sha = digest_file(temporary)
    if digest_file(source) != sha or (source.stat().st_size, source.stat().st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise ValueError('Recorder source changed while copying; copies retained for review')
    with temporary.open('rb') as retained:
        os.fsync(retained.fileno())
    temporary.replace(root / 'reference-original.wav')
    write_json(root / 'source.json', {'path': str(source), 'sha256': sha, 'originalName': source.name,
        'mtimeNs': before.st_mtime_ns, 'bytes': before.st_size,
        'use': 'Owner voice reference ONLY; not clinical knowledge', 'sourcePreserved': True})
    register_reference(library_workspace, root, sha)
    return root


def score(vector, templates, support=3):
    """Third-best separate window match, not a calibrated identity probability.

    Requiring several non-overlapping reference windows avoids treating a single
    favorable/outlier template as proof. Threshold selection still needs negatives.
    """
    vector = unit(vector)
    ranked = sorted((similarity(vector, unit(t['vector'])) for t in templates), reverse=True)
    if len(ranked) < support:
        return {'supportedSimilarity': None, 'bestSimilarity': ranked[0] if ranked else None, 'windowsAvailable': len(ranked)}
    return {'supportedSimilarity': round(ranked[support - 1], 5), 'bestSimilarity': round(ranked[0], 5), 'windowsAvailable': len(ranked)}


def coverage(start, end, turns):
    events = []
    for turn in turns:
        a, b = max(start, turn['start']), min(end, turn['end'])
        if a < b:
            events += [(a, 1), (b, -1)]
    active = 0; previous = start; speech = overlap = 0
    for point, change in sorted(events):
        if active:
            speech += point - previous
        if active > 1:
            overlap += point - previous
        active += change; previous = point
    return speech / (end - start), overlap / (end - start)


def inspect(root, manifest, comparison=None, engine=None):
    import numpy as np
    import soundfile as sf
    from .audio_prepare import normalize_copy
    root = private_path(root); root.chmod(0o700)
    atomic_write(root / '.gitignore', '*\n')
    source = load_json(root / 'source.json'); original = root / 'reference-original.wav'
    if digest_file(original) != source['sha256']:
        raise ValueError('Retained reference original changed')
    original.chmod(0o600)
    normalized = root / 'reference-16k.wav'
    if not normalized.exists():
        normalize_copy(original, normalized, max_seconds=1800)
    normalized.chmod(0o600)
    models = load_json(private_path(manifest))
    settings = {**SETTINGS, 'chunkSeconds': 600}
    identity = {'version': VERSION, 'sourceSha256': source['sha256'], 'normalizedSha256': digest_file(normalized),
                'models': {k: digest_file(local_path(models[k])) for k in ['segmentation', 'embedding']},
                'windowSeconds': 8, 'minimumSpeechFraction': .65, 'maximumOverlapFraction': .1,
                'maximumClippingFraction': .01, 'minimumRms': .002, 'settings': settings}
    session_path = root / 'session.json'
    if session_path.exists() and load_json(session_path) != identity:
        raise ValueError('Immutable reference audio/models/settings changed; choose a new workspace')
    write_json(session_path, identity)
    with lock(root):
        if not (root / 'candidate-profile.json').exists():
            samples, rate = sf.read(normalized, dtype='float32')
            if rate != 16000 or samples.ndim != 1:
                raise ValueError('Reference requires mono16k workspace audio')
            engine = engine or CpuDiarizer(models, settings)
            raw = root / 'speech-analysis.json'
            if not raw.exists():
                started = time.monotonic()
                analysis = engine.process(samples, lambda done, total: 0)
                write_json(raw, {**analysis, 'seconds': round(time.monotonic() - started, 3), 'binding': identity})
            analysis = load_json(raw)
            if analysis['binding'] != identity:
                raise ValueError('Speech analysis binding changed')
            templates = []; skipped = []
            for frame in range(0, len(samples), 8 * rate):
                audio = samples[frame:frame + 8 * rate]; start = frame / rate; end = start + len(audio) / rate
                if end - start < 4:
                    continue
                spoken, overlap = coverage(start, end, analysis['turns'])
                rms = float(np.sqrt(np.mean(audio.astype(float) ** 2)))
                clipped = float(np.mean(np.abs(audio) >= .99))
                if spoken < .65 or overlap > .1 or clipped > .01 or rms < .002:
                    skipped.append({'start': start, 'end': end, 'speechFraction': spoken, 'overlapFraction': overlap, 'rms': rms, 'clippingFraction': clipped})
                    continue
                stream = engine.extractor.create_stream()
                stream.accept_waveform(sample_rate=rate, waveform=np.ascontiguousarray(audio)); stream.input_finished()
                if engine.extractor.is_ready(stream):
                    vector = unit(engine.extractor.compute(stream))
                    templates.append({'start': start, 'end': end, 'vector': vector, 'speechFraction': round(spoken, 3),
                                      'rms': round(rms, 5), 'clippingFraction': round(clipped, 5)})
            write_json(root / 'candidate-profile.json', {'version': VERSION, 'binding': identity, 'templates': templates,
                'skippedWindows': skipped, 'durationSeconds': len(samples) / rate,
                'use': 'CANDIDATES ONLY until explicit owner-only speech confirmation; no production label changes'})
        profile = load_json(root / 'candidate-profile.json')
        if profile['binding'] != identity:
            raise ValueError('Reference profile binding changed')
        if comparison:
            compare(root, comparison)
        render(root)


def confirm_owner_only(root):
    root = private_path(root); profile = load_json(root / 'candidate-profile.json')
    if len(profile['templates']) < 3:
        raise ValueError('Not enough eligible speech windows to enroll; retain candidates for review')
    write_json(root / 'attestation.json', {'ownerOnlySpeechConfirmed': True, 'confirmedAt': now(),
               'profileSha256': digest_file(root / 'candidate-profile.json'),
               'scope': 'Owner confirmed their prepared reference recording. Not independent identity matching validation.'})
    render(root)


def compare(root, comparison):
    root = private_path(root); comparison = private_path(comparison)
    profile = load_json(root / 'candidate-profile.json'); templates = profile['templates']
    target_session = load_json(comparison / 'global-embedding-session.json')
    if profile['binding']['models']['embedding'] != target_session['modelSha256']:
        raise ValueError('Cannot compare embeddings from different speaker models')
    groups = load_json(comparison / 'global-speaker-groups.json')['groups']
    cache_hashes = load_json(comparison / 'global-speaker-session.json')['replacementEmbeddingCheckpoints']
    ids = {(member['chunk'], member['localSpeaker']): group['speaker'] for group in groups for member in group['members']}
    records = load_json(comparison / 'recordings.json'); rows = []
    for record in records:
        for cache in sorted((comparison / 'global-embeddings').glob(record['id'] + '-[0-9][0-9][0-9][0-9].json')):
            if cache_hashes.get(cache.name) != digest_file(cache):
                raise ValueError('Prior-shift embedding checkpoint changed; do not score it')
            values = load_json(cache)
            for local, vector in values['embeddings'].items():
                rows.append({'recordingNumber': record['number'], 'part': int(cache.stem.rsplit('-', 1)[1]),
                    'localSpeaker': int(local), 'existingTentativeLabel': ids.get((cache.stem, int(local)), 'Unknown'),
                    **score(vector, templates)})
    write_json(root / 'comparison.json', {'comparisonWorkspace': str(comparison), 'rows': rows,
        'profileSha256': digest_file(root / 'candidate-profile.json'),
        'note': 'Similarity only, NOT identity probability. Existing labels are not ground truth. No label is changed. A confirmed non-owner example is required before evaluating false matches.'})


def render(root):
    root = private_path(root); profile = load_json(root / 'candidate-profile.json')
    attestation = root / 'attestation.json'
    confirmed = attestation.exists() and load_json(attestation).get('profileSha256') == digest_file(root / 'candidate-profile.json')
    status = 'Owner-only speech confirmed; reference enrolled for LOCAL EVALUATION, not deployed identity recognition.' if confirmed else 'Pending confirmation that the recording contains only the owner speaking. No identity profile deployed.'
    e = lambda text: html.escape(str(text), quote=True)
    body = '<h1>Private owner voice reference</h1><p>' + e(status) + '</p><p>' + e(round(profile['durationSeconds'], 2)) + ' seconds; ' + str(len(profile['templates'])) + ' non-overlapping voice templates covering the recording; ' + str(len(profile['skippedWindows'])) + ' windows excluded by basic audio/speech checks. Separate templates retain variation rather than averaging all speaking styles into one vector.</p>'
    markdown = ['# Private owner voice reference', '', status, '', f"Duration: {profile['durationSeconds']:.2f}s. Templates: {len(profile['templates'])}. Excluded windows: {len(profile['skippedWindows'])}.", '']
    audio = root / 'reference-16k.wav'
    if audio.stat().st_size > 32 * 1024 ** 2:
        raise ValueError('Standalone reference exceeds embedded-audio limit; originals retained')
    encoded = base64.b64encode(audio.read_bytes()).decode()
    body += '<audio id="audio" controls preload="metadata" src="data:audio/wav;base64,' + encoded + '"></audio><p id="status"></p><h2>Reference speech windows</h2>'
    for template in profile['templates']:
        label = f"{template['start']:.2f}–{template['end']:.2f}s"
        body += '<button data-time="' + str(template['start']) + '">Listen ' + e(label) + '</button> '
        markdown.append('- ' + label)
    if (root / 'comparison.json').exists():
        comparison = load_json(root / 'comparison.json')
        body += '<h2>Reference similarity across the previous shift</h2><p>' + e(comparison['note']) + '</p><p>Score = third-best match to separate, non-overlapping reference windows. Higher similarity is not proof of identity. No threshold is deployed; do not assume a whole existing label belongs to the owner.</p><table><thead><tr><th>Recording</th><th>Current tentative label</th><th>Supported similarity</th><th>Best window</th></tr></thead><tbody>'
        markdown += ['', '## Prior-shift similarity comparison', comparison['note'], '', '| Recording | Tentative label | Supported similarity | Best window |', '|---|---|---|---|']
        for row in comparison['rows']:
            values = [row['recordingNumber'], row['existingTentativeLabel'], row['supportedSimilarity'], row['bestSimilarity']]
            body += '<tr>' + ''.join('<td>' + e(x) + '</td>' for x in values) + '</tr>'
            markdown.append('| ' + ' | '.join(str(x) for x in values) + ' |')
        body += '</tbody></table>'
    script = "document.addEventListener('click',e=>{const b=e.target.closest('button[data-time]');if(!b)return;const a=document.getElementById('audio');a.currentTime=Number(b.dataset.time);a.play().catch(()=>{document.getElementById('status').textContent='Press Play on the audio player.';});});"
    sha = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = "default-src 'none'; media-src data:; style-src 'unsafe-inline'; script-src 'sha256-" + sha + "'; base-uri 'none'; form-action 'none'"
    document = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="' + e(csp) + '"><title>Private voice reference</title><style>body{max-width:1100px;margin:auto;padding:24px;font:17px/1.6 system-ui;background:#faf8f2;color:#18332f;overflow-wrap:anywhere}audio{width:100%}button{padding:7px;margin:4px;cursor:pointer}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccd8d1;padding:8px;text-align:left}</style></head><body>' + body + '<script>' + script + '</script></body></html>'
    atomic_write(root / 'review.html', document)
    atomic_write(root / 'summary.md', '\n'.join(markdown))
    output = root / 'owner-review-directory.json'
    if output.exists():
        dest = private_path(load_json(output)['path']); dest.mkdir(parents=True, exist_ok=True, mode=0o700); dest.chmod(0o700)
        atomic_write(dest / 'Results.html', document)
        atomic_write(dest / 'Summary.md', '\n'.join(markdown))
