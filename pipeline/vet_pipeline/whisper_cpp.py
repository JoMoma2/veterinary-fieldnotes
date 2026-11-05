"""Local whisper.cpp CLI adapter; no model downloads or system configuration changes."""

from __future__ import annotations
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from .util import load_json, write_json


def parse_whisper_cpp(data):
    from .ingest import transcript_valid

    return transcript_valid(
        {
            "segments": [
                {
                    "start": e["offsets"]["from"] / 1000,
                    "end": e["offsets"]["to"] / 1000,
                    "text": e["text"],
                }
                for e in data.get("transcription", [])
                if e["text"].strip()
            ]
        }
    )


def transcribe_cpp(source: Path, settings):
    executable = Path(settings["executable"]).expanduser()
    model = Path(settings["model"]).expanduser()
    if not executable.is_file() or not model.is_file():
        raise ValueError(
            "whisper-cpp needs an existing local executable and model file"
        )
    with wave.open(str(source), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
            16000,
            1,
            2,
        ):
            raise ValueError(
                "whisper-cpp requires mono 16 kHz PCM16 WAV; convert a workspace copy first"
            )
    with tempfile.TemporaryDirectory(prefix="vet-whisper-cpp-") as tmp:
        prefix = Path(tmp) / "transcript"
        decoding = []
        if settings.get('max_text_context', -1) >= 0:
            decoding += ['-mc', str(settings['max_text_context'])]
        if not settings.get('temperature_fallback', True):
            decoding += ['-nf']
        result = subprocess.run(
            [
                str(executable),
                "-m",
                str(model),
                "-f",
                str(source),
                "-l",
                settings["language"] or "auto",
                "-t",
                str(settings["threads"]),
                "-dev",
                str(settings["gpu_device"]),
                *decoding,
                "-ojf",
                "-of",
                str(prefix),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=settings["timeout_seconds"],
        )
        raw = load_json(prefix.with_suffix(".json"))
        if settings.get("details_path"):
            write_json(Path(settings["details_path"]), raw)
        from .asr_quality import assess_whisper, TranscriptionReviewRequired
        quality = assess_whisper(raw, duration)
        if settings.get('quality_path'):
            write_json(Path(settings['quality_path']), quality)
        if quality['invalidTimestampSegments'] or quality['outOfBoundsSegments']:
            raise TranscriptionReviewRequired('Retained Whisper output has invalid source timestamps; owner review required')
        transcript = parse_whisper_cpp(raw)
        transcript['transcriptionQuality'] = quality
        adjustments = []
        for index, segment in enumerate(transcript["segments"]):
            if segment["start"] >= duration or segment["end"] > duration + 1:
                raise ValueError(
                    "whisper-cpp timestamp exceeds source duration; review output"
                )
            if segment["end"] > duration:
                # Whisper may timestamp padded trailing audio. Bound only this small
                # overrun, retaining the original offset for audit; never alter text.
                adjustments.append(
                    {
                        "segment": index,
                        "originalEnd": segment["end"],
                        "boundedEnd": duration,
                    }
                )
                segment["end"] = duration
        proof = [
            line
            for line in result.stderr.splitlines()
            if re.search(
                r"whisper_backend_init_gpu.*using.*(?:Vulkan|ROCm|HIP)", line, re.I
            )
        ]
        transcript["transcriptionBackend"] = {
            "kind": "whisper-cpp",
            "model": model.name,
            "gpuAccelerationConfirmed": bool(proof),
            "backendEvidence": proof,
            "timestampAdjustments": adjustments,
            'decodingSettings': {'maxTextContext': settings.get('max_text_context', -1),
                                 'temperatureFallback': settings.get('temperature_fallback', True)},
        }
        return transcript
