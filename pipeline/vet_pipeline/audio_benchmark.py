"""Standalone transcription benchmark. Never changes pipeline settings or installs/downloads a model."""

from __future__ import annotations
import json
import re
import time
import wave
from pathlib import Path
from .locations import local_path

from .hardware import ResourceSampler, inventory
from .ingest import transcript_valid
from .whisper_cpp import parse_whisper_cpp
from .util import load_json, write_json, now, digest_file


def words(text):
    return re.findall(r"[\w]+(?:'[\w]+)?", text.lower())


def word_error_rate(reference, hypothesis):
    expected, actual = words(reference), words(hypothesis)
    if not expected:
        return None
    previous = list(range(len(actual) + 1))
    for i, a in enumerate(expected, 1):
        current = [i]
        for j, b in enumerate(actual, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b))
            )
        previous = current
    return previous[-1] / len(expected)


def utterance_alignment(reference_segments, transcript):
    tokens, owners = [], []
    for segment in transcript["segments"]:
        part = words(segment["text"])
        tokens.extend(part)
        owners.extend([segment] * len(part))
    aligned = []
    for ref in reference_segments:
        phrase = words(ref["text"])[:6]
        matches = (
            [
                i
                for i in range(len(tokens) - len(phrase) + 1)
                if tokens[i : i + len(phrase)] == phrase
            ]
            if phrase
            else []
        )
        if len(matches) == 1:
            start = owners[matches[0]]["start"]
            aligned.append(
                {
                    "referenceStart": ref["start"],
                    "hypothesisSegmentStart": start,
                    "startErrorSeconds": start - ref["start"],
                }
            )
        else:
            aligned.append(
                {
                    "referenceStart": ref["start"],
                    "startErrorSeconds": None,
                    "reason": "Opening phrase did not match uniquely",
                }
            )
    errors = [
        abs(v["startErrorSeconds"])
        for v in aligned
        if v["startErrorSeconds"] is not None
    ]
    return {
        "method": "Coarse phrase-matched segment starts versus known synthetic utterance-buffer starts; not word-level or ER alignment accuracy.",
        "utterances": aligned,
        "meanAbsoluteStartErrorSeconds": sum(errors) / len(errors) if errors else None,
        "maxAbsoluteStartErrorSeconds": max(errors) if errors else None,
    }


def benchmark_audio(
    manifest: Path,
    output: Path,
    backend: str,
    model: str,
    executable=None,
    threads=4,
    origin="synthetic",
    authorization_ref="",
):
    data = load_json(manifest)
    if origin not in ["synthetic", "authorized-record"] or data.get("origin") != origin:
        raise ValueError(
            "Manifest origin must match the explicitly selected benchmark origin"
        )
    if origin == "authorized-record" and not authorization_ref:
        raise ValueError(
            "Real audio benchmark requires a recording/processing authorization reference"
        )
    from .util import REPO

    if origin == "authorized-record" and REPO in output.resolve().parents:
        raise ValueError(
            "Real audio benchmark reports must remain outside the public application repository"
        )
    if backend not in ["faster-whisper", "whisper-cpp"]:
        raise ValueError("Unknown transcription benchmark backend")
    if backend == "whisper-cpp" and (not executable or not local_path(model).is_file()):
        raise ValueError(
            "Configure an existing whisper.cpp executable and local model file; automatic downloads are disabled"
        )
    rows = []
    transcriber = None
    for item in data["recordings"]:
        path = (manifest.parent / item["file"]).resolve()
        start = time.monotonic()
        row = {"id": item["id"], "inputSha256": digest_file(path)}
        with ResourceSampler() as resources:
            try:
                with wave.open(str(path), "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate()
                if backend == "faster-whisper":
                    from faster_whisper import WhisperModel

                    if transcriber is None:
                        transcriber = WhisperModel(
                            model,
                            device="cpu",
                            compute_type="int8",
                            cpu_threads=threads,
                            local_files_only=True,
                        )
                    inference_start = time.monotonic()
                    segments, _ = transcriber.transcribe(
                        str(path), language="en", vad_filter=True, beam_size=5
                    )
                    transcript = transcript_valid(
                        {
                            "segments": [
                                {"start": s.start, "end": s.end, "text": s.text}
                                for s in segments
                            ]
                        }
                    )
                    row["inferenceSeconds"] = round(
                        time.monotonic() - inference_start, 3
                    )
                    row["gpuAccelerationConfirmed"] = False
                else:
                    from .whisper_cpp import transcribe_cpp

                    transcript = transcribe_cpp(
                        path,
                        {
                            "executable": str(executable),
                            "model": model,
                            "language": "en",
                            "threads": threads,
                            "gpu_device": 0,
                            "timeout_seconds": 600,
                        },
                    )
                    row.update(transcript["transcriptionBackend"])
                    row["rawTimestampBoundsValid"] = not transcript[
                        "transcriptionBackend"
                    ]["timestampAdjustments"]
                text = " ".join(s["text"].strip() for s in transcript["segments"])
                seconds = time.monotonic() - start
                row.update(
                    valid=True,
                    seconds=round(seconds, 3),
                    audioSeconds=duration,
                    realTimeFactor=seconds / duration,
                    wordErrorRate=word_error_rate(item["reference"], text)
                    if item.get("reference")
                    and (
                        origin == "synthetic"
                        or item.get("referenceKind") == "human-transcript"
                    )
                    else None,
                    reference=item.get("reference"),
                    referenceKind=item.get(
                        "referenceKind",
                        "synthetic-text" if origin == "synthetic" else "recollection",
                    ),
                    timestampBoundsValid=all(
                        0 <= s["start"] < s["end"] <= duration + 0.1
                        for s in transcript["segments"]
                    ),
                    transcript=transcript,
                    missingTerminology=[
                        term
                        for term in item.get("terminology", [])
                        if term.lower() not in text.lower()
                    ],
                    utteranceAlignment=utterance_alignment(
                        item.get("referenceSegments", []), transcript
                    ),
                )
            except Exception as e:
                row.update(
                    valid=False,
                    error=type(e).__name__,
                    seconds=round(time.monotonic() - start, 3),
                )
                if type(e) is ValueError:
                    row["reason"] = str(e)
        row["hardwareUtilization"] = resources.summary()
        rows.append(row)
    report = {
        "schemaVersion": 1,
        "at": now(),
        "origin": origin,
        "backend": backend,
        "model": model,
        "threads": threads,
        "modelSha256": digest_file(local_path(model)) if local_path(model).is_file() else None,
        "hardware": inventory(),
        "results": rows,
        "limitations": "Synthetic speech is a mechanical/terminology baseline, not representative clinical accuracy. First-file wall time includes model load; later Faster-Whisper files reuse the model. CPU/GPU utilization is host-wide; do not infer offload from GPU activity alone.",
    }
    write_json(output, report)
    return report
