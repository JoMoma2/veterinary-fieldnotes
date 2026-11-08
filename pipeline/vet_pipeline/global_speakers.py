"""Offline, whole-shift voice clustering from existing private speaker checkpoints.

No new audio/model inference. No permanent voice registry. Numeric thresholds are
provisional, not trained/calibrated identity confidence or an accuracy guarantee.
"""
from pathlib import Path
import time

from .private import private_path
from .util import digest_file, load_json, write_json, now, lock

SETTINGS = {'version': 'whole-shift-complete-v2', 'centeredSimilarity': .55, 'rawSimilarity': .9}
TITANET_SETTINGS = {'version': 'whole-shift-titanet-anchored-v3', 'centeredSimilarity': -1,
                    'rawSimilarity': .55, 'linkage': 'average', 'minimumPairSimilarity': .25}


def cluster(vectors, chunks, settings=None, cannot_link=None, seeds=()):
    """Complete-link clustering: every pair must pass both similarity thresholds.

    Center the shift's embeddings to reduce their strong common component. Local
    voices from the same chunk cannot merge, and an A-B-C similarity chain cannot
    join A/C when their pair fails. All shift vectors are considered together.
    """
    import numpy as np
    settings = dict(settings or SETTINGS)
    raw = np.asarray(vectors, dtype=float)
    if not len(raw):
        return [], {'meanNorm': 0}
    norms = np.linalg.norm(raw, axis=1)
    if not np.isfinite(raw).all() or (norms < 1e-12).any():
        raise ValueError('Invalid cached voice vector')
    raw = raw / norms[:, None]
    mean = raw.mean(axis=0); centered = raw - mean
    cn = np.linalg.norm(centered, axis=1)
    # Identical/degenerate vectors are not enough to establish distinct people.
    if (cn < 1e-8).any():
        return [[i] for i in range(len(raw))], {'meanNorm': float(np.linalg.norm(mean)), 'degenerate': True}
    centered /= cn[:, None]
    # The smaller threshold surplus is the conservative merge score.
    score = np.minimum(centered @ centered.T - settings['centeredSimilarity'], raw @ raw.T - settings['rawSimilarity'])
    conflict = np.equal.outer(chunks, chunks) if cannot_link is None else np.asarray(cannot_link, dtype=bool)
    score[conflict] = -2; np.fill_diagonal(score, -2)
    groups = {i: [i] for i in range(len(raw))}
    weights = {i: 1 for i in groups}; worst = raw @ raw.T
    worst[conflict] = -2
    def merge(a, b):
        row = (score[a] * weights[a] + score[b] * weights[b]) / (weights[a] + weights[b]) if settings.get('linkage') == 'average' else np.minimum(score[a], score[b])
        floor = np.minimum(worst[a], worst[b])
        row[(floor < settings.get('minimumPairSimilarity', -1)) | (score[a] < -1) | (score[b] < -1)] = -2
        score[a] = row; score[:, a] = row; score[a, a] = -2
        worst[a] = floor; worst[:, a] = floor; worst[b] = -2; worst[:, b] = -2
        score[b] = -2; score[:, b] = -2
        groups[a] += groups.pop(b); weights[a] += weights.pop(b)
    for seed in seeds:
        members = sorted(set(seed))
        if any(conflict[a, b] for a in members for b in members if a != b):
            raise ValueError('Owner reference anchors conflict with simultaneous voice evidence')
        for b in members[1:]:
            merge(members[0], b)
    while len(groups) > 1:
        a, b = np.unravel_index(score.argmax(), score.shape)
        if score[a, b] < 0:
            break
        if a > b:
            a, b = b, a
        merge(a, b)
    return sorted(groups.values(), key=min), {'meanNorm': round(float(np.linalg.norm(mean)), 5)}


def regroup(reference, root, settings=None, overrides=None):
    """New output workspace only; source checkpoint files are hash-bound/read-only."""
    reference = private_path(reference); root = private_path(root)
    if reference == root or (root / 'calls/index.json').exists():
        raise ValueError('Use a fresh workspace; never relabel completed inference in place')
    records = load_json(reference / 'recordings.json'); settings = dict(settings or SETTINGS)
    nodes = []; chunks = []; hashes = {}
    for record in records:
        for path in sorted((reference / 'speaker-chunks').glob(record['id'] + '-[0-9][0-9][0-9][0-9].json')):
            value = load_json(path); hashes[path.name] = digest_file(path)
            part = int(path.stem.rsplit('-', 1)[1]); key = path.stem
            chunks.append({'recordingId': record['id'], 'recordingNumber': record['number'], 'part': part, 'key': key, 'data': value})
            for local in dict.fromkeys(turn['localSpeaker'] for turn in value['turns']):
                vector = (overrides.get(key, {}) if overrides is not None else value['embeddings']).get(str(local))
                if vector:
                    nodes.append({'chunk': key, 'recordingNumber': record['number'], 'local': local, 'vector': vector})
    binding = {'settings': settings, 'sourceCheckpointHashes': hashes,
               'sourceSessionSha256': digest_file(reference / 'speaker-session.json')}
    if overrides is not None:
        binding['replacementEmbeddingSessionSha256'] = digest_file(root / 'global-embedding-session.json')
        binding['replacementEmbeddingCheckpoints'] = {p.name: digest_file(p) for p in sorted((root / 'global-embeddings').glob('*-[0-9][0-9][0-9][0-9].json'))}
    binding['ownerReferenceSha256'] = digest_file(root / 'owner-confirmed-spans.json') if (root / 'owner-confirmed-spans.json').exists() else None
    prior = root / 'global-speaker-session.json'
    if prior.exists() and load_json(prior) != binding:
        raise ValueError('Immutable whole-shift speaker input/settings changed')
    write_json(prior, binding)
    import numpy as np
    conflict = np.zeros((len(nodes), len(nodes)), dtype=bool)
    by_key = {c['key']: c for c in chunks}
    for i, left in enumerate(nodes):
        for j, right in enumerate(nodes[:i]):
            if left['chunk'] == right['chunk']:
                turns = by_key[left['chunk']]['data']['turns']
                overlap = sum(max(0, min(a['end'], b['end']) - max(a['start'], b['start']))
                              for a in turns for b in turns if a['localSpeaker'] == left['local'] and b['localSpeaker'] == right['local'])
                conflict[i, j] = conflict[j, i] = overlap >= .3
    seeds = []
    if (root / 'owner-confirmed-spans.json').exists():
        references = load_json(root / 'owner-confirmed-spans.json')['references']; candidates = []
        chunk_seconds = load_json(reference / 'speaker-session.json')['settings']['chunkSeconds']
        for ref in references:
            amounts = {}
            for i, node in enumerate(nodes):
                if node['recordingNumber'] != ref['recording']:
                    continue
                chunk = by_key[node['chunk']]; offset = chunk['part'] * chunk_seconds
                amount = sum(max(0, min(ref['end'], t['end'] + offset) - max(ref['start'], t['start'] + offset))
                             for t in chunk['data']['turns'] if t['localSpeaker'] == node['local'])
                if amount:
                    amounts[i] = amount
            if amounts:
                best = max(amounts, key=amounts.get)
                if amounts[best] >= 3 and amounts[best] / sum(amounts.values()) >= .85:
                    candidates.append(best)
        candidates = sorted(set(candidates))
        if len({nodes[i]['recordingNumber'] for i in candidates}) >= 2:
            seeds = [candidates]
    groups, diagnostics = cluster([n['vector'] for n in nodes], [n['chunk'] for n in nodes], settings, conflict, seeds)
    mapping = {}; members = []
    for number, group in enumerate(groups, 1):
        label = f'Speaker_{number:03d}'
        for i in group:
            mapping[nodes[i]['chunk'], nodes[i]['local']] = label
        members.append({'speaker': label, 'recordings': sorted({nodes[i]['recordingNumber'] for i in group}),
                        'members': [{'chunk': nodes[i]['chunk'], 'localSpeaker': nodes[i]['local']} for i in group]})
    labels = {record['id']: [] for record in records}
    chunk_seconds = load_json(reference / 'speaker-session.json')['settings']['chunkSeconds']
    for chunk in chunks:
        offset = chunk['part'] * chunk_seconds
        for turn in chunk['data']['turns']:
            label = mapping.get((chunk['key'], turn['localSpeaker']), 'Unknown')
            labels[chunk['recordingId']].append({'start': turn['start'] + offset, 'end': turn['end'] + offset,
                'speaker': label, 'similarity': None, 'basis': 'whole-shift constrained cluster; unverified' if label != 'Unknown' else 'no clean voice embedding'})
    failed = list(load_json(reference / 'speaker-labels.json').get('failed', []))
    if (root / 'global-embedding-failures.json').exists():
        failed += load_json(root / 'global-embedding-failures.json')
    write_json(root / 'speaker-labels.json', {'scope': 'whole shift only; unverified offline clusters',
               'speakers': [m['speaker'] for m in members], 'turns': labels, 'failed': failed})
    if (root / 'owner-confirmed-spans.json').exists():
        calibration = load_json(root / 'owner-confirmed-spans.json'); checks = []
        for ref in calibration['references']:
            record = records[ref['recording'] - 1]; amounts = {}
            for turn in labels[record['id']]:
                overlap = max(0, min(ref['end'], turn['end']) - max(ref['start'], turn['start']))
                if overlap:
                    amounts[turn['speaker']] = amounts.get(turn['speaker'], 0) + overlap
            checks.append({**ref, 'detectedVoiceGroups': sorted(amounts), 'detectedSpeechSeconds': round(sum(amounts.values()), 3)})
        clear = [c for c in checks if c['detectedSpeechSeconds'] >= 3 and len(c['detectedVoiceGroups']) == 1 and c['detectedVoiceGroups'][0] != 'Unknown']
        matched = len({c['recording'] for c in clear}) >= 2 and len({c['detectedVoiceGroups'][0] for c in clear}) == 1
        write_json(root / 'owner-reference-checks.json', {'label': calibration['label'], 'checks': checks,
            'clearReferencesAgree': matched, 'clearReferenceMinimumDetectedSeconds': 3,
            'usedAsIdentityAnchors': bool(seeds),
            'note': 'Owner-provided clear references anchor the owner voice across files. Agreement is supervised, NOT independent recognition accuracy. Other group members remain inferred; possible secondary voices and imperfect timestamps remain relevant.'})
    # No vectors in this report/map: the original private recovery cache remains intact.
    write_json(root / 'global-speaker-groups.json', {'settings': settings, 'groups': members, 'diagnostics': diagnostics,
               'localVoiceGroups': len(nodes), 'globalGroups': len(groups),
               'groupsSpanningRecordings': sum(len(m['recordings']) > 1 for m in members),
               'ownerReferenceAnchors': bool(seeds),
               'note': 'Grouping/coverage counts, not verified people or speaker accuracy; owner reference agreement uses manual identity supervision.'})
    write_json(root / 'speaker-progress.json', {'status': 'complete-with-failures' if failed else 'complete',
               'recordings': len(records), 'recordingsCompleted': len(records), 'completedChunks': len(chunks),
               'speakers': len(groups), 'finishedAt': now(), 'reusedAudioAnalysis': True, 'failed': failed})
    experiment = load_json(root / 'experiment.json')
    experiment['speakerAlignment'] = 'detected-speech-v2'
    write_json(root / 'experiment.json', experiment)
    from . import speakers
    speakers.annotate(root); speakers.render(root)
    from .shift_context import render
    render(root)


def reembed(reference, root, manifest):
    """Reuse exact diarization turns; compare a different CPU embedding backend.

    This does not re-transcribe or rerun segmentation. Each chunk has bounded
    attempts and a fingerprint binding the source WAV, turn cache and model.
    """
    import numpy as np
    import soundfile as sf
    import sherpa_onnx as so
    from .speakers import unit, render
    reference = private_path(reference); root = private_path(root)
    model = Path(load_json(private_path(manifest))['embedding'])
    identity = {'modelSha256': digest_file(model), 'version': 'cached-turn-embedding-v1', 'threads': 4}
    target = root / 'global-embedding-session.json'
    if target.exists() and load_json(target) != identity:
        raise ValueError('Replacement embedding model/settings changed')
    write_json(target, identity)
    extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=str(model), num_threads=4, provider='cpu'))
    records = load_json(reference / 'recordings.json'); experiment = load_json(reference / 'experiment.json')
    chunk_seconds = load_json(reference / 'speaker-session.json')['settings']['chunkSeconds']
    progress = {'status': 're-embedding', 'recordings': len(records), 'recordingsCompleted': 0, 'completedChunks': 0}
    write_json(root / 'speaker-progress.json', progress); overrides = {}; failures = []
    for number, record in enumerate(records, 1):
        path = reference / 'inputs' / (record['id'] + '.wav')
        if digest_file(path) != experiment['audio'][record['id']]['sha256']:
            raise ValueError('Source WAV changed before replacement embedding')
        for cache in sorted((reference / 'speaker-chunks').glob(record['id'] + '-[0-9][0-9][0-9][0-9].json')):
            binding = {**identity, 'turnCacheSha256': digest_file(cache), 'audioSha256': experiment['audio'][record['id']]['sha256']}
            out = root / 'global-embeddings' / cache.name
            if out.exists():
                saved = load_json(out)
                if saved['binding'] != binding:
                    raise ValueError('Replacement embedding checkpoint changed')
            else:
                attempts_path = out.with_name(out.stem + '-attempts.json')
                attempts = load_json(attempts_path).get('attempts', 0) if attempts_path.exists() else 0
                saved = None
                for attempt in range(attempts, 3):
                    write_json(attempts_path, {'attempts': attempt + 1})
                    try:
                        with sf.SoundFile(path) as audio:
                            part = int(cache.stem.rsplit('-', 1)[1]); audio.seek(part * chunk_seconds * 16000)
                            samples = audio.read(chunk_seconds * 16000, dtype='float32')
                        turns = load_json(cache)['turns']; vectors = {}
                        for local in dict.fromkeys(t['localSpeaker'] for t in turns):
                            clean = [t for t in turns if t['localSpeaker'] == local and t['end'] - t['start'] >= 1.5
                                     and not any(o['localSpeaker'] != local and max(t['start'], o['start']) < min(t['end'], o['end']) for o in turns)]
                            batch = []
                            for turn in sorted(clean, key=lambda t: t['end'] - t['start'], reverse=True)[:3]:
                                start = int(turn['start'] * 16000); end = min(len(samples), int(min(turn['end'], turn['start'] + 12) * 16000))
                                stream = extractor.create_stream(); stream.accept_waveform(sample_rate=16000, waveform=np.ascontiguousarray(samples[start:end])); stream.input_finished()
                                if extractor.is_ready(stream):
                                    batch.append(unit(extractor.compute(stream)))
                            if batch:
                                vectors[str(local)] = unit(np.mean(batch, axis=0).tolist())
                        saved = {'binding': binding, 'embeddings': vectors}; write_json(out, saved); break
                    except Exception as error:
                        write_json(attempts_path, {'attempts': attempt + 1, 'errorClass': type(error).__name__})
                if saved is None:
                    # An embedding failure leaves that chunk's voices unknown;
                    # never mix incompatible model vectors or lose its source audio.
                    saved = {'embeddings': {}}
                    failures.append({'recordingNumber': number, 'chunk': int(cache.stem.rsplit('-', 1)[1]) + 1, 'errorClass': 'replacement embedding attempts exhausted'})
            overrides[cache.stem] = saved['embeddings']
            progress['completedChunks'] += 1
        progress.update(recordingsCompleted=number, updatedAt=now()); write_json(root / 'speaker-progress.json', progress); render(root)
    write_json(root / 'global-embedding-failures.json', failures)
    return overrides


def run_after_reference(root, model_manifest):
    """Refine speakers on CPU, then wait for existing extraction before using GPU."""
    from .shift_context import run
    root = private_path(root); experiment = load_json(root / 'experiment.json')
    reference = private_path(experiment['referenceExperiment'])
    with lock(root / 'global-run'):
        if not experiment.get('globalSpeakerRefinementComplete'):
            overrides = reembed(reference, root, model_manifest)
            regroup(reference, root, TITANET_SETTINGS, overrides)
            experiment = load_json(root / 'experiment.json'); experiment['globalSpeakerRefinementComplete'] = True
            write_json(root / 'experiment.json', experiment)
        from .repetition_filter import prepare as filter_repetitions
        filter_repetitions(root, threshold=5)
        experiment = load_json(root / 'experiment.json'); experiment['status'] = 'waiting-for-reference'
        write_json(root / 'experiment.json', experiment)
        from .shift_context import render
        render(root)
        while load_json(reference / 'experiment.json')['status'] in ['prepared', 'running', 'deferred']:
            time.sleep(20)
        run(root)
