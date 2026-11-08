"""Private retained-WAV comparison. No extraction, publication, or cloud saving."""
from pathlib import Path
from .locations import local_path
import html
import json
import os
import sqlite3
import time
from urllib.parse import urlparse

from .asr_quality import assess_whisper, TranscriptionReviewRequired
from .audio_prepare import duration_seconds
from .morning import page
from .private import private_path, initialize_private
from .resources import check_resources
from .runner import ProcessingDeferred
from .util import atomic_write, digest_file, load_json, lock, now, write_json
from .whisper_cpp import transcribe_cpp


def prepare(source, output, cfg, authorization_ref):
    source, output = private_path(source), private_path(output)
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Use a separate private comparison directory')
    endpoint = urlparse(cfg['provider']['base_url'])
    p = cfg['transcription']
    if not authorization_ref.strip() or cfg['provider']['kind'] != 'ollama' or endpoint.hostname not in ['localhost', '127.0.0.1', '::1'] or endpoint.port != 11434 or p['kind'] != 'whisper-cpp' or p['allow_model_download']:
        raise ValueError('Explicit local-test authorization and installed local Whisper are required')
    db = sqlite3.connect('file:' + str(source / 'jobs.sqlite3') + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        jobs = [dict(j) for j in db.execute("SELECT id,sha256,sequence,source_name,origin FROM jobs WHERE source_kind='audio' ORDER BY shift_date,shift_id,sequence,id")]
    finally:
        db.close()
    if not jobs or len({j['origin'] for j in jobs}) != 1:
        raise ValueError('Choose a nonempty unmixed retained-audio workspace')
    records = []
    for number, job in enumerate(jobs, 1):
        original = source / 'inputs' / (job['id'] + '.wav')
        normalized = source / 'normalized' / (job['id'] + '.wav')
        audio = normalized if normalized.exists() else original
        baseline = source / 'transcription-details' / (job['id'] + '.json')
        if digest_file(original) != job['sha256']:
            raise ValueError('Retained original hash differs; preserve and inspect it')
        if normalized.exists():
            meta = load_json(normalized.with_suffix('.json'))
            if meta['originalSha256'] != job['sha256'] or meta['normalizedSha256'] != digest_file(audio):
                raise ValueError('Normalized source integrity differs')
        records.append({**job, 'number': number, 'original': str(original), 'audio': str(audio),
                        'audioSha256': digest_file(audio), 'durationSeconds': duration_seconds(audio),
                        'baseline': str(baseline), 'baselineSha256': digest_file(baseline) if baseline.exists() else None})
    binding = {'schemaVersion': 1, 'source': str(source), 'authorizationRef': authorization_ref,
               'settings': p, 'modelSha256': digest_file(local_path(p['model']).expanduser()),
               'executableSha256': digest_file(local_path(p['executable']).expanduser()), 'recordings': records}
    manifest = output / 'session.json'
    if manifest.exists():
        if load_json(manifest) != binding:
            raise ValueError('Comparison inputs/settings changed; choose a new private directory')
    else:
        initialize_private(output)
        write_json(manifest, binding)
    return output, binding


def render(root, session):
    e = lambda v: html.escape(str(v), quote=True)
    rows = []
    results = []
    progress = load_json(root / 'progress.json') if (root / 'progress.json').exists() else {}
    for item in session['recordings']:
        folder = root / 'results' / item['id']
        result = load_json(folder / 'result.json') if (folder / 'result.json').exists() else {}
        if result:
            results.append(result)
        status = result.get('status', 'running' if progress.get('recordingId') == item['id'] else 'queued')
        body = '<a href="../../index.html">Comparison</a><p>Private, unreviewed ASR comparison. Fewer repetitions do not establish accurate speech.</p>'
        body += '<p>Status: ' + e(status) + '</p><p>Original copy</p><audio controls preload="none" src="' + e(local_path(item['original']).as_uri()) + '"></audio><p>Working copy used by Whisper</p><audio controls preload="none" src="' + e(local_path(item['audio']).as_uri()) + '"></audio>'
        for label, path in [('Candidate', folder / 'whisper.json'), ('Original baseline', local_path(item['baseline']))]:
            body += '<h2>' + label + '</h2>'
            if path.exists():
                raw = load_json(path)
                q = assess_whisper(raw, item['durationSeconds'])
                body += '<pre>' + e(json.dumps(q, indent=2)) + '</pre><details><summary>Full raw ASR text and model timestamps</summary>'
                for entry in raw.get('transcription', []):
                    offsets = entry.get('offsets', {})
                    start = offsets.get('from')
                    link = ''
                    if isinstance(start, (int, float)) and 0 <= start / 1000 < item['durationSeconds']:
                        link = '<a href="' + e(local_path(item['audio']).as_uri()) + '#t=' + str(start / 1000) + '">Listen at ' + str(start / 1000) + 's</a> '
                    body += '<p>' + link + e(entry.get('text', '')) + '</p>'
                body += '</details>'
            else:
                body += '<p>No saved output yet.</p>'
        atomic_write(folder / 'index.html', page('Recording ' + str(item['number']) + ' — ' + item['source_name'], body))
        rows.append('<tr><td><a href="results/' + e(item['id']) + '/index.html">Recording ' + str(item['number']) + '</a></td><td>' + e(status) + '</td><td>' + e(result.get('seconds', '')) + '</td><td>' + e(result.get('candidateQuality', {}).get('maximumPhraseRepeats', '')) + '</td><td>' + e(result.get('baselineQuality', {}).get('maximumPhraseRepeats', '')) + '</td></tr>')
    summary = {'updatedAt': now(), 'total': len(session['recordings']), 'completed': len(results),
               'progress': progress, 'results': results,
               'limitations': 'No reference transcript: repetition and valid timestamps are not accuracy or useful-knowledge scores. No extraction/publication/upload is part of this test.'}
    write_json(root / 'summary.json', summary)
    body = '<p>Local retained-audio comparison. Source files and earlier transcripts are unchanged. Refresh to see saved results.</p><p>Candidate settings: max text context ' + e(session['settings']['max_text_context']) + ', temperature fallback ' + e(session['settings']['temperature_fallback']) + '.</p><p>' + str(len(results)) + '/' + str(len(session['recordings'])) + ' recordings finished. Results remain unreviewed.</p><pre>' + e(json.dumps(progress, indent=2)) + '</pre><table><thead><tr><th>Recording</th><th>Status</th><th>Seconds</th><th>Candidate max repeats</th><th>Baseline max repeats</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
    atomic_write(root / 'index.html', page('Fieldnotes — retained audio comparison', body))
    return summary


def run(source, output, cfg, authorization_ref):
    os.umask(0o077)
    root, session = prepare(source, output, cfg, authorization_ref)
    with lock(root):
        render(root, session)
        for item in session['recordings']:
            folder = root / 'results' / item['id']
            result_path = folder / 'result.json'
            if result_path.exists():
                old = load_json(result_path)
                if any(not (folder / name).exists() or digest_file(folder / name) != sha for name, sha in old['artifacts'].items()):
                    raise ValueError('Saved comparison artifact changed; preserve and inspect it')
                continue
            if digest_file(local_path(item['audio'])) != item['audioSha256']:
                raise ValueError('Comparison audio changed; preserve and inspect it')
            raw_path = folder / 'whisper.json'
            started = time.monotonic()
            result = {'number': item['number'], 'recordingId': item['id']}
            if raw_path.exists():
                # Crash after durable raw output: retain/review it, never repeat inference.
                result.update(status='raw-recovered-review', seconds=None)
            else:
                try:
                    check_resources(cfg, 'transcribe')
                except ProcessingDeferred as error:
                    write_json(root / 'progress.json', {'stage': 'waiting-resources', 'number': item['number'], 'reason': str(error), 'at': now()})
                    render(root, session)
                    raise
                write_json(root / 'progress.json', {'recordingId': item['id'], 'number': item['number'], 'stage': 'transcribe', 'startedAt': now()})
                render(root, session)
                print(json.dumps({'recording': item['number'], 'status': 'transcribing'}), flush=True)
                try:
                    transcript = transcribe_cpp(local_path(item['audio']), {**cfg['transcription'], 'details_path': str(raw_path), 'quality_path': str(folder / 'quality.json')})
                    write_json(folder / 'transcript.json', transcript)
                    result.update(status='review-required' if transcript['transcriptionQuality']['reviewRequired'] else 'completed-unreviewed', gpuConfirmed=transcript['transcriptionBackend']['gpuAccelerationConfirmed'])
                except TranscriptionReviewRequired:
                    result.update(status='review-required', reason='Invalid model timestamps retained without repair')
                except Exception as error:
                    result.update(status='failed', error=type(error).__name__)
                result['seconds'] = round(time.monotonic() - started, 3)
            if raw_path.exists():
                result['candidateQuality'] = assess_whisper(load_json(raw_path), item['durationSeconds'])
            baseline = local_path(item['baseline'])
            if baseline.exists():
                result['baselineQuality'] = assess_whisper(load_json(baseline), item['durationSeconds'])
            result['artifacts'] = {p.name: digest_file(p) for p in folder.glob('*.json') if p.name != 'result.json'}
            write_json(result_path, result)
            write_json(root / 'progress.json', {'stage': 'between-recordings', 'lastCompleted': item['number'], 'at': now()})
            render(root, session)
            print(json.dumps({'recording': item['number'], 'status': result['status'], 'seconds': result['seconds'], 'maxPhraseRepeats': result.get('candidateQuality', {}).get('maximumPhraseRepeats')}), flush=True)
        progress = load_json(root / 'progress.json') if (root / 'progress.json').exists() else {}
        if progress.get('stage') != 'finished':
            write_json(root / 'progress.json', {'stage': 'finished', 'at': now()})
        return render(root, session)
