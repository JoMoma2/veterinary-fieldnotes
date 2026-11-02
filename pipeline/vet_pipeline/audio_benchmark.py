"""Standalone transcription benchmark. Never changes pipeline settings or installs/downloads a model."""

from __future__ import annotations
import json
import re
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from .hardware import ResourceSampler, inventory
from .ingest import transcript_valid
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


def parse_whisper_cpp(data):
    segments = []
    for entry in data.get("transcription", []):
        offsets = entry.get("offsets", {})
        segments.append(
            {
                "start": offsets["from"] / 1000,
                "end": offsets["to"] / 1000,
                "text": entry["text"],
            }
        )
    return transcript_valid({"segments": segments})


def benchmark_audio(
    manifest: Path, output: Path, backend: str, model: str, executable=None, threads=4
):
    data = load_json(manifest)
    if data.get("origin") != "synthetic":
        raise ValueError(
            "This prepared audio benchmark accepts synthetic audio only; real audio requires a separately authorized corpus"
        )
    if backend not in ["faster-whisper", "whisper-cpp"]:
        raise ValueError("Unknown transcription benchmark backend")
    if backend == "whisper-cpp" and (not executable or not Path(model).is_file()):
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
                    with tempfile.TemporaryDirectory(prefix="vet-whisper-cpp-") as tmp:
                        prefix = Path(tmp) / "transcript"
                        r = subprocess.run(
                            [
                                str(executable),
                                "-m",
                                model,
                                "-f",
                                str(path),
                                "-l",
                                "en",
                                "-t",
                                str(threads),
                                "-ojf",
                                "-of",
                                str(prefix),
                            ],
                            capture_output=True,
                            text=True,
                            check=True,
                            timeout=600,
                        )
                        transcript = parse_whisper_cpp(
                            load_json(prefix.with_suffix(".json"))
                        )
                        # A compiled GPU backend alone is not proof that inference used it.
                        proof = [
                            line
                            for line in r.stderr.splitlines()
                            if re.search(
                                r"whisper_backend_init_gpu.*using.*(?:Vulkan|ROCm|HIP)",
                                line,
                                re.I,
                            )
                        ]
                        row["gpuAccelerationConfirmed"] = bool(proof)
                        row["backendEvidence"] = proof
                text = " ".join(s["text"].strip() for s in transcript["segments"])
                seconds = time.monotonic() - start
                row.update(
                    valid=True,
                    seconds=round(seconds, 3),
                    audioSeconds=duration,
                    realTimeFactor=seconds / duration,
                    wordErrorRate=word_error_rate(item["reference"], text),
                    reference=item["reference"],
                    transcript=transcript,
                    missingTerminology=[
                        term
                        for term in item.get("terminology", [])
                        if term.lower() not in text.lower()
                    ],
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
        "origin": "synthetic",
        "backend": backend,
        "model": model,
        "threads": threads,
        "modelSha256": digest_file(Path(model)) if Path(model).is_file() else None,
        "hardware": inventory(),
        "results": rows,
        "limitations": "Synthetic speech is a mechanical/terminology baseline, not representative clinical accuracy. First-file wall time includes model load; later Faster-Whisper files reuse the model. CPU/GPU utilization is host-wide; do not infer offload from GPU activity alone.",
    }
    write_json(output, report)
    return report
