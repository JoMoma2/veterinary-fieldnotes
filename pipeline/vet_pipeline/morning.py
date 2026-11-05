"""Owner-only static review pages. No server, external assets, AI or publication."""
from __future__ import annotations
import html, json, os, hashlib
from pathlib import Path
from urllib.parse import quote
from .library import current
from .private import private_path
from .util import atomic_write, load_json, write_json

STYLE = "body{font:17px/1.6 system-ui;max-width:1100px;margin:auto;padding:24px;background:#faf8f2;color:#18332f;overflow-wrap:anywhere}section,details{padding:16px;background:white;border:1px solid #b8c9bf;border-radius:10px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}audio{width:100%}a{color:#12645c}.flag{border-left:6px solid #b45c20}li{margin:8px 0}"
E = lambda x: html.escape(str(x))


def page(title, body):
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; media-src \'self\' file:; script-src \'none\'"><title>' + E(title) + '</title><style>' + STYLE + '</style></head><body><h1>' + E(title) + '</h1>' + body + '</body></html>'


def report(store, cfg, state):
    private_path(store.root)
    lib = current(store)
    jobs = list(store.jobs())
    root = store.root / 'review'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    dm = {d['id']: d for d in lib['discussions']}
    article_links = lambda d: ' '.join('<a href="../articles/' + E(a['id']) + '.html">' + E(a['title']) + '</a>' for a in lib['articles'] if d['id'] in a['sourceDiscussionIds'])
    audio_seconds = 0
    links = []
    groups = {}
    asr_flagged = 0
    asr_flagged_ids = set()
    for j in jobs:
        rid = j['id']
        meta_path = store.root / 'source-metadata' / (rid + '.json')
        meta = load_json(meta_path) if meta_path.exists() else {}
        if j['source_kind'] == 'audio':
            original = store.root / 'inputs' / (rid + '.wav')
            # Refresh old codec estimates once using the corrected duration reader;
            # preserve original filesystem/hash/name metadata and clock uncertainty.
            if original.exists() and ('durationSeconds' not in meta or meta.get('audioMetadataVersion') != 2):
                try:
                    from .audio_prepare import inspect_audio
                    meta.update(inspect_audio(original))
                    meta['audioMetadataVersion'] = 2
                    write_json(meta_path, meta)
                except Exception:
                    meta['durationSeconds'] = None
            audio_seconds += meta.get('durationSeconds') or 0
            # Convenience links preserve original names by shift; canonical files remain untouched.
            folder = store.root / 'retained' / j['shift_id']
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            for label, target in [(rid + '-' + j['source_name'], original),
                                  (rid + '-transcript.json', store.root / 'transcripts' / (rid + '.json'))]:
                link = folder / label
                if target.exists() and not link.exists() and not link.is_symlink():
                    link.symlink_to(os.path.relpath(target, folder))
            normalized = store.root / 'normalized' / (rid + '.wav')
            media = '../../normalized/' + rid + '.wav' if normalized.exists() else '../../inputs/' + rid + '.wav'
            body = '<a href="../index.html">Morning report</a><p>Original filename: ' + E(j['source_name']) + '; stage: ' + E(j['stage']) + '; error: ' + E(j['error'] or 'None') + '</p>'
            body += '<p>Original copy</p><audio controls preload="none" src="../../inputs/' + rid + '.wav"></audio>'
            body += '<p>Working copy (same time origin)</p><audio controls preload="none" src="' + media + '"></audio>'
        else:
            media = ''
            body = '<a href="../index.html">Morning report</a>'
        qp = store.root / 'transcription-quality' / (rid + '.json')
        quality = load_json(qp) if qp.exists() else {}
        if quality.get('reviewRequired'):
            asr_flagged += 1
            asr_flagged_ids.add(rid)
            body += '<section class="flag"><h2>Transcription needs audio review</h2><p>Repeated text or invalid timing was detected. This is a screening warning; it does not prove which words were spoken. Existing derived knowledge may be unreliable and remains unreviewed.</p><pre>' + E(json.dumps(quality, indent=2)) + '</pre></section>'
        body += '<details><summary>Original metadata / clock uncertainty</summary><pre>' + E(json.dumps(meta, indent=2)) + '</pre></details>'
        tp = store.root / 'transcripts' / (rid + '.json')
        if tp.exists():
            text = load_json(tp)
            body += '<h2>Full saved transcript</h2>'
            for s in text['segments']:
                label = f"{s['start']:.2f}–{s['end']:.2f}s"
                body += '<p>' + (('<a href="' + media + f'#t={s["start"]},{s["end"]}">' + label + '</a> ') if media else label + ' ') + E(s['text']) + '</p>'
        else:
            body += '<p>Transcript not available here: pending processing or recovered permanent knowledge without its original source media.</p>'
            raw_path = store.root / 'transcription-details' / (rid + '.json')
            if raw_path.exists():
                raw = load_json(raw_path)
                body += '<details><summary>Full raw Whisper output — unvalidated text and timestamps</summary><p>Preserved even when timestamp validation failed. These offsets are model output, not verified source links.</p>'
                for entry in raw.get('transcription', []):
                    body += '<p>' + E(json.dumps(entry.get('offsets', {}))) + ' ' + E(entry.get('text', '')) + '</p>'
                body += '</details>'
        body += '<h2>Extracted discussions</h2>'
        for d in lib['discussions']:
            if not any(s['recordingId'] == rid for s in d['segments']):
                continue
            body += '<section id="' + E(d['id']) + '" class="' + ('flag' if 'unclassified-source' in d['topics'] else '') + '"><h3>' + E(d['title']) + '</h3>' + article_links(d)
            body += '<pre>' + E(d['account']) + '</pre><ul>'
            body += ''.join('<li><strong>' + E(f['kind']) + '</strong>: ' + E(f['text']) + '</li>' for f in d['facts']) + '</ul></section>'
        body += '<p>Check medications, negation, evidence kinds, uncertain cases, omissions and source links. Valid quotes do not certify medical interpretation.</p>'
        body += '<p>Private diagnostics: <a href="../../quality/' + rid + '/">quality files</a>, <a href="../../extractions/' + rid + '/">chunk checkpoints</a>, <a href="../../transcription-details/' + rid + '.json">full Whisper JSON</a>.</p>'
        atomic_write(root / 'recordings' / (rid + '.html'), page(j['source_name'], body))
        link = '<li><a href="recordings/' + rid + '.html">' + E(j['source_name']) + '</a> — ' + E(j['stage']) + ((' / ' + E(j['error'])) if j['error'] else '') + '</li>'
        groups.setdefault(j['shift_id'], []).append(link)
    def sources(ids):
        output = []
        for did in ids:
            d = dm.get(did)
            if d and d['segments']:
                rid = d['segments'][0]['recordingId']
                output.append('<li><a href="../recordings/' + E(rid) + '.html#' + E(did) + '">' + E(d['title']) + '</a></li>')
        return '<ul>' + ''.join(output) + '</ul>'
    for a in lib['articles']:
        warning = ''
        if any(s['recordingId'] in asr_flagged_ids for did in a['sourceDiscussionIds'] for s in dm.get(did, {}).get('segments', [])):
            warning = '<section class="flag"><h2>Unreviewed transcription source</h2><p>This article uses ASR with quality warnings. Its claims may come from repeated or incorrectly recognized speech. Compare the linked audio before studying or relying on it.</p></section>'
        atomic_write(root / 'articles' / (a['id'] + '.html'), page(a['title'], '<a href="../index.html">Morning report</a>' + warning + '<pre>' + E(a['body']) + '</pre>' + sources(a['sourceDiscussionIds'])))
    pending = [j for j in jobs if j['stage'] != 'done']
    seconds = 0
    events = store.root / 'events.jsonl'
    if events.exists():
        for line in events.read_text().splitlines():
            try:
                seconds += json.loads(line).get('timingSeconds', {}).get('total', 0)
            except json.JSONDecodeError:
                pass  # A killed writer's final log line cannot hide saved records.
    counts = {k: len(v) for k, v in lib.items()}
    worker_seconds = 0
    worker_events = store.root / 'unattended/events.jsonl'
    if worker_events.exists():
        for line in worker_events.read_text().splitlines():
            try:
                worker_seconds += json.loads(line).get('seconds', 0)
            except json.JSONDecodeError:
                pass
    baseline = state.get('session', {}).get('articlesBefore', {})
    batch_ids = set(state.get('session', {}).get('recordingIds', []))
    summary = {'recordingsImported': len(jobs), 'recordingsProcessed': len(jobs) - len(pending),
               'recordingsAwaitingTranscriptReview': sum(j['stage'] == 'review' for j in jobs),
               'recordingsWithASRWarnings': asr_flagged,
               'audioSeconds': round(audio_seconds, 3), 'activeProcessingSeconds': round(seconds, 3),
               'workerSecondsIncludingInterruptedRuns': round(worker_seconds, 3),
               'batchRecordingsImported': len(batch_ids),
               'batchRecordingsProcessed': sum(j['id'] in batch_ids and j['stage'] == 'done' for j in jobs),
               'batchArticlesCreated': sum(a['id'] not in baseline for a in lib['articles']) if 'articlesBefore' in state.get('session', {}) else None,
               'batchArticlesUpdated': sum(a['id'] in baseline and baseline[a['id']] != hashlib.sha256(a['body'].encode()).hexdigest() for a in lib['articles']) if 'articlesBefore' in state.get('session', {}) else None,
               'incomplete': len(pending), 'unclassifiedDiscussions': sum('unclassified-source' in d['topics'] for d in lib['discussions']),
               'recordCounts': counts, 'lastWork': state.get('lastWork', {}),
               'lastObservedStage': state.get('activeRun'),
               'lastDiscovery': state.get('lastDiscovery', {}),
               'masterSync': state.get('masterSync', {}), 'lastPoll': state.get('lastPoll')}
    write_json(root / 'summary.json', summary)
    body = '<p>Private local review. Audio, full transcripts and intermediate results are retained. Import batches are not verified recording dates; clock offsets remain recording-relative.</p>'
    if asr_flagged:
        body += '<section class="flag"><h2>Audio/transcription review required</h2><p>' + str(asr_flagged) + ' recordings have ASR quality warnings. Read the warnings on each recording page and compare with its audio. Previously generated notes and questions from flagged sources are unreviewed; successful processing does not establish accuracy.</p></section>'
    body += '<h2>Processing summary</h2><pre>' + E(json.dumps(summary, indent=2)) + '</pre>'
    body += '<p>Per-job active time excludes unfinished interrupted attempts; worker time includes interruption/import/sync overhead but excludes timer waits. Last work/batch preserves meaningful activity rather than being overwritten by idle polls.</p>'
    body += '<h2>Shift / import batches</h2>'
    for shift, entries in groups.items():
        body += '<details open><summary>' + E(shift) + '</summary><ul>' + ''.join(entries) + '</ul></details>'
    body += '<h2>Knowledge articles</h2><ul>' + ''.join('<li><a href="articles/' + E(a['id']) + '.html">' + E(a['title']) + '</a></li>' for a in lib['articles']) + '</ul>'
    body += '<h2>Cases</h2>' + ''.join('<details><summary>' + E(c['title']) + '</summary><pre>' + E(json.dumps(c, indent=2)) + '</pre></details>' for c in lib['cases'])
    body += '<h2>Study questions</h2>' + ''.join('<details><summary>' + E(q['prompt']) + '</summary><pre>' + E(json.dumps(q, indent=2)) + '</pre></details>' for q in lib['questions'])
    body += '<h2>Publication candidates</h2><p><a href="publication-candidates.json">Generated review template</a> (all unapproved). Copy to a separate approval file before owner review; this candidate file is regenerated. Unapproved material never blocks private processing. The existing reviewed-publication helper pushes approved content; Cloudflare then rebuilds automatically.</p>'
    if pending:
        body += '<h2>Needs attention / waiting</h2><p>GPU/Ollama deferral does not consume retries. Recording errors retry up to the configured limit. After resolving an exhausted job, use vet-pipeline retry JOB_ID for this workspace; no successful transcription/extraction is repeated.</p><pre>' + E(json.dumps([dict(j) for j in pending], indent=2)) + '</pre>'
    atomic_write(root / 'index.html', page('Veterinary Fieldnotes — morning review', body))
    return summary
