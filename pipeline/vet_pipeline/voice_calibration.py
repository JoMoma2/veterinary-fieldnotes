"""Small, private, blinded listening checks. No automatic identity deployment."""
import base64
import hashlib
import html
import io
import json
import random
import wave

from .private import private_path
from .util import load_json, write_json, digest_file, atomic_write
from .voice_reference import score


def prepare(root, comparison, manifest, count=12):
    import numpy as np
    import soundfile as sf
    import sherpa_onnx as so
    root = private_path(root); comparison = private_path(comparison)
    if not 4 <= count <= 24:
        raise ValueError('Use a small listening check of 4–24 clips')
    profile = load_json(root / 'candidate-profile.json'); profile_sha = digest_file(root / 'candidate-profile.json')
    if load_json(root / 'attestation.json').get('profileSha256') != profile_sha:
        raise ValueError('Owner-only reference must be explicitly confirmed first')
    model = private_path(load_json(private_path(manifest))['embedding'])
    if digest_file(model) != profile['binding']['models']['embedding']:
        raise ValueError('Incompatible speaker model')
    folder = root / 'calibration'; folder.mkdir(mode=0o700, exist_ok=True)
    binding = {'version': 1, 'profileSha256': profile_sha, 'comparisonSha256': digest_file(root / 'comparison.json'),
               'groupingSha256': digest_file(comparison / 'global-speaker-groups.json'), 'requestedClips': count}
    target = folder / 'pack.json'
    if target.exists():
        pack = load_json(target)
        if pack['binding'] != binding:
            raise ValueError('Listening-pack inputs changed; retain old annotations and use a new workspace')
        for case in pack['cases']:
            if digest_file(folder / (case['id'] + '.wav')) != case['clipSha256']:
                raise ValueError('Listening clip changed')
        return render(root)
    source = private_path(load_json(comparison / 'experiment.json')['referenceExperiment'])
    records = load_json(comparison / 'recordings.json'); settings = load_json(source / 'speaker-session.json')['settings']
    cases = []; selected = set(); selected_records = set()
    def choose(row, reference=None):
        if len(cases) >= count:
            return
        key = (row['recordingNumber'], row['part'], row['localSpeaker'])
        if key in selected or (reference is None and row['recordingNumber'] in selected_records):
            return
        record = records[row['recordingNumber'] - 1]
        cache = source / 'speaker-chunks' / (record['id'] + f"-{row['part']:04d}.json")
        turns = load_json(cache)['turns']; offset = row['part'] * settings['chunkSeconds']
        spans = []
        for turn in turns:
            if turn['localSpeaker'] != row['localSpeaker']:
                continue
            a, b = turn['start'] + offset, turn['end'] + offset
            if reference:
                a, b = max(a, reference['start']), min(b, reference['end'])
            if b - a >= 4 and not any(o['localSpeaker'] != turn['localSpeaker'] and max(a, o['start'] + offset) < min(b, o['end'] + offset) for o in turns):
                spans.append((a, b))
        if not spans:
            return
        a, b = max(spans, key=lambda s: s[1] - s[0]); length = min(6, b - a); start = (a + b - length) / 2
        cases.append({'recordingNumber': row['recordingNumber'], 'recordingId': record['id'], 'start': start,
                      'end': start + length, 'sourceLabel': row['existingTentativeLabel'],
                      'selection': 'owner-reference control' if reference else 'unlabelled calibration candidate'})
        selected.add(key); selected_records.add(row['recordingNumber'])
    rows = load_json(root / 'comparison.json')['rows']
    refs = load_json(comparison / 'owner-confirmed-spans.json')['references'] if (comparison / 'owner-confirmed-spans.json').exists() else []
    for ref in refs:
        if ref['end'] - ref['start'] >= 6:
            for row in rows:
                if row['recordingNumber'] == ref['recording']:
                    choose(row, ref)
    associated = set()
    if (comparison / 'owner-reference-checks.json').exists():
        associated = {s for ref in load_json(comparison / 'owner-reference-checks.json')['checks'] for s in ref['detectedVoiceGroups']}
    ascending = sorted(rows, key=lambda r: r['supportedSimilarity'] if r['supportedSimilarity'] is not None else -2)
    for row in [r for r in ascending if r['existingTentativeLabel'] in associated][:max(4, count // 3)]:
        choose(row)
    for row in reversed(ascending):
        if row['existingTentativeLabel'] not in associated and len(cases) < count * .75:
            choose(row)
    for row in ascending:
        choose(row)
    # Hidden sampling reason/scores: the owner judges the SOUND, not our suggestion.
    random.Random(profile_sha).shuffle(cases)
    extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=str(model), num_threads=4, provider='cpu'))
    source_manifest = load_json(source / 'experiment.json')['audio']; verified = set()
    for number, case in enumerate(cases, 1):
        path = source / 'inputs' / (case['recordingId'] + '.wav')
        if case['recordingId'] not in verified:
            if digest_file(path) != source_manifest[case['recordingId']]['sha256']:
                raise ValueError('Source audio changed; do not create calibration clips')
            verified.add(case['recordingId'])
        samples, rate = sf.read(path, start=round(case['start'] * 16000), stop=round(case['end'] * 16000), dtype='int16')
        if rate != 16000 or samples.ndim != 1:
            raise ValueError('Use retained mono16k workspace audio')
        stream = extractor.create_stream(); stream.accept_waveform(sample_rate=rate, waveform=samples.astype(np.float32) / 32768); stream.input_finished()
        case.update(score(extractor.compute(stream), profile['templates']))
        case['id'] = f'clip-{number:02d}'
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(samples.astype('<i2').tobytes())
        data = output.getvalue(); case['clipSha256'] = hashlib.sha256(data).hexdigest()
        clip = folder / (case['id'] + '.wav')
        if clip.exists() and digest_file(clip) != case['clipSha256']:
            raise ValueError('Existing calibration clip differs; preserve it for review')
        atomic_write(clip, data)
    pack = {'binding': binding, 'cases': cases, 'note': 'Private selected calibration sample, not representative whole-shift accuracy. No negative labels inferred from scores or old clusters.'}
    write_json(target, pack)
    return render(root)


def render(root):
    root = private_path(root); folder = root / 'calibration'; pack = load_json(folder / 'pack.json'); sha = digest_file(folder / 'pack.json')
    e = lambda value: html.escape(str(value), quote=True)
    body = '<h1>Private voice listening check</h1><p>Listen to the actual voice. Choose Your voice, Someone else, Multiple voices, or Unsure. Do not infer identity from the words or patient details. If noisy or mixed, say so. No answer is assumed from an old speaker label.</p><p>Answers stay in this page memory until you download them. No server, account, tracking, upload or automatic speaker-label changes.</p><p id="status">No clips labelled yet.</p>'
    for index, case in enumerate(pack['cases'], 1):
        clip = folder / (case['id'] + '.wav')
        if digest_file(clip) != case['clipSha256']:
            raise ValueError('Calibration clip changed; do not render mismatched audio')
        audio = base64.b64encode(clip.read_bytes()).decode()
        body += '<section data-id="' + e(case['id']) + '"><h2>Clip ' + str(index) + '</h2><audio controls preload="none" src="data:audio/wav;base64,' + audio + '"></audio><p>'
        for value, label in [('owner', 'Your voice'), ('other', 'Someone else'), ('mixed', 'Multiple voices'), ('unsure', 'Unsure')]:
            body += '<button data-label="' + value + '" aria-pressed="false">' + label + '</button> '
        body += '</p></section>'
    body += '<button id="download">Download my labels</button><p>Save the JSON locally and provide its file path for analysis. This selected sample does not measure population accuracy.</p>'
    script = "const answers={};document.addEventListener('click',e=>{const b=e.target.closest('button[data-label]');if(!b)return;const s=b.closest('section');answers[s.dataset.id]=b.dataset.label;s.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));document.getElementById('status').textContent=Object.keys(answers).length+' clips labelled';});document.addEventListener('play',e=>{if(e.target.tagName==='AUDIO')document.querySelectorAll('audio').forEach(a=>{if(a!==e.target)a.pause();});},true);document.getElementById('download').addEventListener('click',()=>{const data={version:1,packSha256:" + json.dumps(sha) + ",answers};const a=document.createElement('a');const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.href=u;a.download='voice-calibration-labels.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);});"
    script_sha = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = "default-src 'none'; media-src data:; style-src 'unsafe-inline'; script-src 'sha256-" + script_sha + "'; base-uri 'none'; form-action 'none'"
    document = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="' + e(csp) + '"><title>Private voice listening check</title><style>body{max-width:900px;margin:auto;padding:24px;font:17px/1.6 system-ui;background:#faf8f2;color:#18332f;overflow-wrap:anywhere}section{background:white;padding:16px;margin:16px 0;border:1px solid #c5d5cc;border-radius:10px}audio{width:100%}button{font:inherit;padding:9px;margin:4px;cursor:pointer}button[aria-pressed=true]{background:#174f42;color:white}</style></head><body>' + body + '<script>' + script + '</script></body></html>'
    atomic_write(folder / 'Review.html', document)
    if (root / 'owner-review-directory.json').exists():
        dest = private_path(load_json(root / 'owner-review-directory.json')['path'])
        atomic_write(dest / 'Calibration.html', document)
    return folder / 'Review.html'


def evaluate(root, annotations, thresholds=(.45, .55, .65, .75)):
    root = private_path(root); folder = root / 'calibration'; pack = load_json(folder / 'pack.json'); labels = load_json(private_path(annotations))
    if labels.get('version') != 1 or labels.get('packSha256') != digest_file(folder / 'pack.json'):
        raise ValueError('Annotations belong to a different listening pack')
    allowed = {case['id'] for case in pack['cases']}; answers = labels.get('answers', {})
    if not isinstance(answers, dict) or any(k not in allowed or v not in ['owner', 'other', 'mixed', 'unsure'] for k, v in answers.items()):
        raise ValueError('Invalid listening labels')
    results = []
    for threshold in thresholds:
        result = {'threshold': threshold, 'trueOwnerMatches': 0, 'missedOwner': 0, 'falseOwnerMatches': 0, 'correctOther': 0, 'mixedOrUnsure': 0}
        for case in pack['cases']:
            truth = answers.get(case['id'])
            if not truth:
                continue
            if truth in ['mixed', 'unsure']:
                result['mixedOrUnsure'] += 1; continue
            predicted = case['supportedSimilarity'] is not None and case['supportedSimilarity'] >= threshold
            key = ('trueOwnerMatches' if predicted else 'missedOwner') if truth == 'owner' else ('falseOwnerMatches' if predicted else 'correctOther')
            result[key] += 1
        results.append(result)
    write_json(folder / 'evaluation.json', {'results': results, 'labelsCount': len(answers), 'note': 'Selected local calibration counts, not a production error-rate estimate. No threshold chosen or deployed.'})
    return results
