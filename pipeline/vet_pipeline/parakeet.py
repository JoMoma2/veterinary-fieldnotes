"""Local Parakeet + Silero transcription using the selected comparison settings.

Original media and raw replies remain retained. Checkpoints bind the exact audio,
weights, runtime and settings; changing any of them never reuses another result.
"""
from __future__ import annotations
from contextlib import ExitStack
import dataclasses
from pathlib import Path
import threading
import time

from .asr_quality import assess_segments, TranscriptionReviewRequired
from .locations import local_path
from .native_asr import native, pcm, split_ranges
from .util import digest_file, load_json, write_json

VAD = {'threshold': .5, 'min_speech_ms': 250, 'min_silence_ms': 300, 'speech_pad_ms': 200}


def timed_run(session, samples, seconds, **kwargs):
    timer = threading.Timer(seconds, session.cancel)
    timer.daemon = True
    started = time.monotonic()
    timer.start()
    try:
        result = session.run(samples, **kwargs)
        if time.monotonic() - started >= seconds:
            raise TimeoutError('ASR window time allowance reached')
        return result
    finally:
        timer.cancel()
        timer.join()


def transcribe_parakeet(source, settings):
    source = Path(source)
    details = Path(settings['details_path'])
    folder = details.with_suffix('.windows')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = {k: local_path(settings[k]).resolve() for k in ['model', 'vad_model', 'runtime']}
    for key in ['model', 'vad_model']:
        if not settings[key + '_sha256'] or digest_file(paths[key]) != settings[key + '_sha256']:
            raise ValueError('Pinned ASR weight changed: ' + key)
    binding = {
        'version': 1, 'audioSha256': digest_file(source),
        'model': str(paths['model']), 'modelSha256': settings['model_sha256'],
        'vadModel': str(paths['vad_model']), 'vadSha256': settings['vad_model_sha256'],
        'runtime': str(paths['runtime']), 'librarySha256': settings['runtime_sha256'],
        'language': settings['language'], 'threads': settings['threads'],
        'gpuName': settings['gpu_name'], 'vad': VAD, 'windowSamples': 480000,
        'overlapSamples': 16000, 'decoderContext': 4096,
    }
    api = native(binding)
    audio = pcm(source)
    plan_path = folder / 'plan.json'
    if plan_path.exists():
        plan = load_json(plan_path)
        if plan['binding'] != binding:
            raise ValueError('ASR input/settings changed; preserve existing checkpoints')
    else:
        with api.Model(str(paths['vad_model']), backend='cpu') as model, model.vad_session(n_threads=2) as vad:
            result = timed_run(vad, audio, settings['timeout_seconds'], **VAD)
        ranges = [[max(0, int(s.start_sample)), min(len(audio), int(s.end_sample))] for s in result.segments]
        ranges = sorted([a, b] for a, b in ranges if a < b)
        excluded = []
        cursor = 0
        for a, b in ranges:
            if a > cursor:
                excluded.append([cursor, a])
            cursor = max(cursor, b)
        if cursor < len(audio):
            excluded.append([cursor, len(audio)])
        plan = {'binding': binding, 'ranges': split_ranges(ranges, len(audio)), 'excludedRanges': excluded,
                'note': 'VAD exclusions are speech-not-detected intervals, not confirmed silence. Overlap is retained.'}
        write_json(plan_path, plan)
    segments = []
    windows = []
    window_issues = []
    with ExitStack() as stack:
        engine = None
        for number, (a, b) in enumerate(plan['ranges']):
            checkpoint = folder / f'window-{number:04d}.json'
            if checkpoint.exists():
                saved = load_json(checkpoint)
                if saved['range'] != [a, b]:
                    raise ValueError('ASR checkpoint source bounds changed')
            else:
                if engine is None:
                    devices = [d for d in api.backends() if d.kind == 'vulkan' and d.device_type == 'gpu'
                               and settings['gpu_name'].casefold() in d.description.casefold()]
                    if len(devices) != 1:
                        raise ValueError('Expected exactly one configured discrete Vulkan GPU')
                    model = stack.enter_context(api.Model(str(paths['model']), backend='vulkan', device=devices[0]))
                    if model.device.kind != 'vulkan':
                        raise ValueError('Requested Vulkan acceleration was not selected')
                    engine = stack.enter_context(model.session(n_threads=settings['threads'], n_ctx=4096))
                try:
                    result = timed_run(engine, audio[a:b], settings['timeout_seconds'],
                                       language=settings['language'] or 'en', timestamps='auto')
                except Exception as error:
                    write_json(folder / f'window-{number:04d}-error-{time.time_ns()}.json',
                               {'range': [a, b], 'errorClass': type(error).__name__})
                    raise
                rows = [{'start': a / 16000 + s.t0_ms / 1000, 'end': a / 16000 + s.t1_ms / 1000,
                         'text': s.text, 'timing': 'model-' + result.timestamp_kind}
                        for s in result.segments if s.text.strip()] if result.timestamp_kind != 'none' else []
                if not rows and result.text.strip():
                    rows = [{'start': a / 16000, 'end': b / 16000, 'text': result.text, 'timing': 'audio-window'}]
                saved = {'range': [a, b], 'segments': rows, 'raw': dataclasses.asdict(result),
                         'device': model.device.description}
                write_json(checkpoint, saved)
            for row in saved['segments']:
                if row['start'] < a / 16000 or row['end'] > b / 16000 + .001:
                    window_issues.append(number)
            segments.extend(saved['segments'])
            windows.append(saved)
    quality = assess_segments(segments, len(audio) / 16000)
    if window_issues:
        quality['reviewRequired'] = True
        quality['reasons'].append('Model timestamps exceed their input window; raw timing retained')
        quality['windowTimestampIssues'] = sorted(set(window_issues))
    write_json(details, {'backend': 'parakeet-tdt-v3+silero-vad', 'plan': plan, 'windows': windows,
                         'segments': segments, 'quality': quality})
    write_json(Path(settings['quality_path']), quality)
    if quality['reviewRequired']:
        raise TranscriptionReviewRequired('Parakeet output needs review; original audio and raw output retained')
    return {'segments': segments, 'language': settings['language'] or 'en',
            'transcriptionBackend': {'kind': 'parakeet', 'speechDetection': 'silero-vad',
                                     'gpuAccelerationConfirmed': True, 'binding': binding,
                                     'timingNote': 'Model times when available; audio-window times are labelled. Overlap retained.'}}
