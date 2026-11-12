"""Shared, pinned transcribe.cpp access for local ASR and its comparisons."""
from __future__ import annotations
import array
import os
from pathlib import Path
import sys
import wave

from .locations import local_path
from .util import digest_file


def native(session):
    runtime = local_path(session['runtime']).resolve()
    library = runtime / 'build-vulkan/src/libtranscribe.so'
    if digest_file(library) != session['librarySha256']:
        raise ValueError('Native runtime changed')
    os.environ['TRANSCRIBE_LIBRARY'] = str(library)
    bindings = runtime / 'bindings/python/src'
    sys.path.insert(0, str(bindings))
    import transcribe_cpp
    if Path(transcribe_cpp.__file__).resolve() != bindings / 'transcribe_cpp/__init__.py':
        raise ValueError('Another native ASR binding is already loaded')
    return transcribe_cpp


def pcm(path):
    with wave.open(str(path), 'rb') as w:
        if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
            raise ValueError('Expected mono16k PCM16')
        data = array.array('h')
        data.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == 'big':
        data.byteswap()
    return array.array('f', (v / 32768 for v in data))


def split_ranges(ranges, total_samples, maximum=30 * 16000, overlap=16000):
    """Keep source offsets and explicit overlap without discarding boundary words."""
    if not (isinstance(maximum, int) and isinstance(overlap, int) and 0 <= overlap < maximum):
        raise ValueError('Invalid comparison window overlap')
    out = []
    for start, end in ranges:
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= total_samples):
            raise ValueError('Invalid source bounds')
        while start < end:
            stop = min(start + maximum, end)
            out.append([start, stop])
            if stop == end:
                break
            start = stop - overlap
    return out
