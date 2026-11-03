"""Inspect and normalize private working copies using local libswresample (PyAV)."""

from __future__ import annotations
import os
import uuid
import wave
from pathlib import Path
from .util import digest_file


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
            "Choose a nonempty recording of at most 15 minutes; trim a copy explicitly before this pilot"
        )
    before = digest_file(source)
    temp = target.with_name(target.name + ".partial-" + uuid.uuid4().hex)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        samples = 0
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
                save(resampler.resample(frame))
            save(resampler.resample(None))
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
