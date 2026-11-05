"""Inspect and normalize private working copies using local libswresample (PyAV)."""

from __future__ import annotations
import os
import struct
import uuid
import wave
from pathlib import Path
from .util import digest_file


def _recorder_ima_timing(path):
    """Recognize complete IMA WAVs whose fact field incorrectly counts blocks.

    Some LU08 recorders write block count as sample count and an inaccurate
    byte rate. Never trust either duration in that case: count complete blocks,
    validate their declared samples, then require the decoder to agree below.
    Other WAVs retain the existing strict header/decoded-duration check.
    """
    size = path.stat().st_size
    with path.open('rb') as source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WAVE':
            return None
        end = struct.unpack_from('<I', header, 4)[0] + 8
        if end != size:
            raise ValueError('WAV RIFF size differs from payload; preserve source for review')
        fmt = fact = data_size = None
        while source.tell() < end:
            chunk = source.read(8)
            if len(chunk) != 8:
                raise ValueError('Truncated WAV chunk header')
            tag, length = struct.unpack('<4sI', chunk)
            next_chunk = source.tell() + length + length % 2
            if next_chunk > end:
                raise ValueError('Truncated WAV chunk payload')
            if tag == b'fmt ':
                if fmt is not None:
                    raise ValueError('Ambiguous WAV format chunks')
                fmt = source.read(min(length, 20))
            elif tag == b'fact' and length >= 4:
                fact = struct.unpack('<I', source.read(4))[0]
            elif tag == b'data':
                if data_size is not None:
                    raise ValueError('Multiple WAV audio payloads require review')
                data_size = length
            source.seek(next_chunk)
    if fmt is None or len(fmt) < 20 or data_size is None:
        return None
    tag, channels, rate, _, align, bits, extension, per_block = struct.unpack('<HHIIHHHH', fmt)
    if tag != 17 or channels != 1 or bits != 4:
        return None
    if extension < 2 or align <= 4 or per_block != (align - 4) * 2 + 1 or rate <= 0:
        raise ValueError('Invalid IMA ADPCM block/sample layout')
    if not data_size or data_size % align:
        raise ValueError('Incomplete IMA ADPCM audio block; preserve source for review')
    blocks = data_size // align
    if fact != blocks:
        return None
    return {'samples': blocks * per_block, 'rate': rate, 'blocks': blocks}


def inspect_audio(path):
    path = Path(path)
    stat = path.stat()
    import av

    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError("No audio stream found")
        stream = container.streams.audio[0]
        codec = stream.codec_context
        duration = (
            float(stream.duration * stream.time_base)
            if stream.duration is not None
            else (
                container.duration / av.time_base
                if container.duration is not None
                else None
            )
        )
        info = {
            "codec": codec.name,
            "sampleRate": codec.sample_rate,
            "channels": len(codec.layout.channels),
            "sampleFormat": codec.format.name if codec.format else None,
            "durationSeconds": duration,
            "sizeBytes": stat.st_size,
            "fileModifiedNs": stat.st_mtime_ns,
            "clockConfidence": "unknown",
        }
    if info['codec'] == 'adpcm_ima_wav':
        timing = _recorder_ima_timing(path)
        if timing:
            info.update(
                headerDurationSeconds=info['durationSeconds'],
                durationSeconds=timing['samples'] / timing['rate'],
                durationBasis='complete IMA ADPCM blocks; decoder agreement required',
                expectedDecodedSamples=timing['samples'],
                timingWarnings=['Recorder fact field counts blocks instead of samples; header byte-rate duration is unreliable. Recording clock remains unknown.'],
            )
    from datetime import datetime, timezone

    info["fileModifiedUtc"] = datetime.fromtimestamp(
        stat.st_mtime, timezone.utc
    ).isoformat()
    try:
        with wave.open(str(path), "rb") as wav:
            info["wavBitsPerSample"] = wav.getsampwidth() * 8
    except (wave.Error, EOFError):
        info["wavBitsPerSample"] = None
    return info


def normalize_copy(source, target, max_seconds=900):
    import av

    source = Path(source)
    target = Path(target)
    if source.resolve() == target.resolve() or target.exists():
        raise ValueError("Never overwrite the source or an existing normalized copy")
    info = inspect_audio(source)
    if (
        info["durationSeconds"] is None
        or not 0 < info["durationSeconds"] <= max_seconds
    ):
        raise ValueError(
            f"Choose a nonempty recording of at most {max_seconds:g} seconds; trim a copy explicitly if needed"
        )
    before = digest_file(source)
    temp = target.with_name(target.name + ".partial-" + uuid.uuid4().hex)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        samples = 0
        decoded_samples = 0
        with av.open(str(source)) as container, wave.open(str(temp), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)

            def save(frames):
                nonlocal samples
                for frame in frames:
                    samples += frame.samples
                    if samples > 16000 * max_seconds:
                        raise ValueError("Decoded audio exceeds pilot duration limit")
                    out.writeframesraw(bytes(frame.planes[0])[: frame.samples * 2])

            for frame in container.decode(audio=0):
                if frame.is_corrupt:
                    raise ValueError('Decoder reported corrupt audio; preserve source for review')
                decoded_samples += frame.samples
                save(resampler.resample(frame))
            save(resampler.resample(None))
        if info.get('expectedDecodedSamples') is not None and decoded_samples != info['expectedDecodedSamples']:
            raise ValueError('Decoded sample count differs from complete IMA blocks; inspect source for truncation')
        if abs(samples / 16000 - info["durationSeconds"]) > 0.05:
            raise ValueError(
                "Decoded duration differs from header; inspect the source for truncation"
            )
        if digest_file(source) != before:
            raise ValueError(
                "Source changed during conversion; retry after it is stable"
            )
        with temp.open("rb") as file:
            os.fsync(file.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return {
        **info,
        "normalizedSamples": samples,
        "normalizedDurationSeconds": samples / 16000,
        "originalSha256": before,
        "normalizedSha256": digest_file(target),
    }
