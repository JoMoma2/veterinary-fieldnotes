"""Private, local-only first-recording evaluation; deliberately has no publication/upload path."""

from __future__ import annotations
import csv
import hashlib
import html
import json
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse
from .audio_prepare import inspect_audio, normalize_copy
from .config import config
from .ingest import ingest, transcribe, transcript_valid
from .library import current, materialize
from .private import private_path, initialize_private
from .runner import run
from .store import Store
from .util import atomic_write, digest_file, load_json, write_json, now

CATEGORIES = [
    "missed",
    "incorrect",
    "invented",
    "terminology",
    "source-link",
    "case-link",
    "topic",
    "study",
    "other",
]


def session(root):
    root = private_path(root)
    if not (root / "session.json").is_file():
        raise ValueError("Not an initialized private evaluation")
    data = load_json(root / "session.json")
    if (
        digest_file(root / "audio/original.wav") != data["originalSha256"]
        or digest_file(root / "audio/normalized.wav") != data["normalizedSha256"]
    ):
        raise ValueError(
            "Evaluation audio changed; preserve originals and start a new evaluation"
        )
    return root, data


def local_config(path):
    cfg = config(path)
    endpoint = urlparse(cfg["provider"]["base_url"])
    if (
        cfg["provider"]["kind"] != "ollama"
        or endpoint.hostname not in ["127.0.0.1", "localhost", "::1"]
        or endpoint.port != 11434
        or endpoint.username
        or endpoint.query
        or endpoint.path not in ["", "/"]
    ):
        raise ValueError(
            "Private evaluation permits only local Ollama; no external inference"
        )
    cfg["provider"].update(allow_remote=False, allow_paid=False)
    cfg["transcription"]["allow_model_download"] = False
    cfg["backup"].update(remote="", allow_clinical_remote=False)
    cfg["retention"]["enabled"] = False
    cfg["usb"]["roots"] = []
    return cfg


def verified_local_model(cfg):
    import httpx

    model = cfg["provider"]["model"]
    with httpx.Client(
        base_url=cfg["provider"]["base_url"],
        timeout=10,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = client.get("/api/tags")
        response.raise_for_status()
        entry = next(
            (m for m in response.json().get("models", []) if m.get("name") == model),
            None,
        )
        if (
            not entry
            or entry.get("size", 0) < 100_000_000
            or entry.get("remote_host")
            or entry.get("remote_model")
            or model.lower().endswith("cloud")
        ):
            raise ValueError(
                "Select an already installed local model, not a cloud-backed or missing model"
            )
        response = client.post("/api/show", json={"model": model})
        response.raise_for_status()
        detail = response.json()
        if (
            detail.get("remote_host")
            or detail.get("remote_model")
            or detail.get("details", {}).get("format") != "gguf"
        ):
            raise ValueError("Model metadata does not establish local GGUF inference")
        return entry.get("digest")


def prepare(source, root, date, authorization_ref, origin="authorized-record"):
    import datetime

    datetime.date.fromisoformat(date)
    if (
        origin not in ["authorized-record", "synthetic"]
        or not authorization_ref.strip()
    ):
        raise ValueError(
            "Recording/processing origin and authorization reference are required"
        )
    source = Path(source).expanduser().resolve()
    info = inspect_audio(source)
    if (
        source.suffix.lower() != ".wav"
        or info["durationSeconds"] is None
        or not 0 < info["durationSeconds"] <= 900
    ):
        raise ValueError(
            "Select a stable WAV of at most 15 minutes, not a whole untested shift"
        )
    root = initialize_private(root)
    (root / "audio").mkdir(mode=0o700)
    source_hash = digest_file(source)
    original = root / "audio/original.wav"
    shutil.copyfile(source, original)
    after = source.stat()
    if (
        source_hash != digest_file(original)
        or after.st_mtime_ns != info["fileModifiedNs"]
        or after.st_size != info["sizeBytes"]
    ):
        raise ValueError("Source changed while copying; no source media was modified")
    converted = normalize_copy(original, root / "audio/normalized.wav")
    data = {
        **converted,
        "schemaVersion": 1,
        "origin": origin,
        "authorizationRef": authorization_ref,
        "recordingDate": date,
        "dateBasis": "owner-selected; not inferred from filesystem timestamp",
        "sourceName": source.name,
        "sourceFileModifiedNs": info["fileModifiedNs"],
        "clockConfidence": "unknown",
        "preparedAt": now(),
    }
    write_json(root / "session.json", data)
    atomic_write(
        root / "recollections.md",
        "# Recollections — write before reading the AI output\n\nMemory notes are not a verbatim reference and may be mistaken.\n\n",
    )
    atomic_write(
        root / "review.csv",
        "model,input,category,reference,observed,source_start,comment\n",
    )
    return {
        "workspace": str(root),
        "durationSeconds": info["durationSeconds"],
        "sourcePreserved": digest_file(source) == source_hash,
        "next": "Write recollections.md, then transcribe.",
    }


def transcribe_session(root, config_path):
    root, data = session(root)
    cfg = local_config(config_path)
    fingerprint = hashlib.sha256(
        json.dumps(cfg["transcription"], sort_keys=True).encode()
    ).hexdigest()
    if (root / "transcription.json").exists():
        previous = load_json(root / "transcription.json")
        if previous["settingsSha256"] != fingerprint or previous[
            "transcriptSha256"
        ] != digest_file(root / "transcript.json"):
            raise ValueError(
                "Immutable ASR transcript/settings changed; use reference.json for corrections or a new evaluation"
            )
        return {"cached": True, "transcript": str(root / "transcript.json")}
    store = Store(root / "transcription-workspace")
    try:
        job, _ = ingest(
            store,
            root / "audio/normalized.wav",
            "s-evaluation",
            data["recordingDate"],
            data["origin"],
            data["authorizationRef"],
        )
        started = time.monotonic()
        text = transcribe(store, store.get(job), cfg)
        write_json(root / "transcript.json", text)
        write_json(
            root / "transcription.json",
            {
                "settingsSha256": fingerprint,
                "transcriptSha256": digest_file(root / "transcript.json"),
                "seconds": round(time.monotonic() - started, 3),
                "backend": cfg["transcription"]["kind"],
                "model": cfg["transcription"]["model"],
            },
        )
        if not (root / "reference.json").exists():
            write_json(
                root / "reference.json",
                {
                    "referenceStatus": "draft-not-corrected",
                    "segments": text["segments"],
                },
            )
    finally:
        store.close()
    return {
        "cached": False,
        "transcript": str(root / "transcript.json"),
        "referenceTemplate": str(root / "reference.json"),
    }


def input_transcript(root, input_kind):
    root, data = session(root)
    if not (root / "transcription.json").exists():
        raise ValueError("Run transcription first")
    if (
        digest_file(root / "transcript.json")
        != load_json(root / "transcription.json")["transcriptSha256"]
    ):
        raise ValueError(
            "Original ASR transcript changed; edit the separate reference instead"
        )
    path = root / ("transcript.json" if input_kind == "asr" else "reference.json")
    text = transcript_valid(load_json(path))
    if (
        input_kind == "reference"
        and text.get("referenceStatus") != "manually-corrected"
    ):
        raise ValueError(
            "Mark referenceStatus as manually-corrected only after listening/correcting it"
        )
    if any(
        s["end"] > data["normalizedDurationSeconds"] + 0.001 for s in text["segments"]
    ):
        raise ValueError("Reference offsets exceed the recording duration")
    return text, path


def extract_session(root, config_path, input_kind="asr"):
    root, data = session(root)
    cfg = local_config(config_path)
    text, path = input_transcript(root, input_kind)
    local_digest = verified_local_model(cfg)
    identity = {
        "model": cfg["provider"]["model"],
        "modelDigest": local_digest,
        "providerSettings": cfg["provider"],
        "input": input_kind,
        "inputSha256": digest_file(path),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    tag = "".join(c if c.isalnum() else "-" for c in cfg["provider"]["model"])[:48]
    destination = root / "results" / f"{tag}-{input_kind}-{digest}"
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    snapshot = destination / "input.json"
    if not snapshot.exists():
        write_json(snapshot, text)
    elif load_json(snapshot) != text:
        raise ValueError("Saved extraction input changed; preserve the original result and use a new evaluation")
    store = Store(destination / "workspace")
    try:
        ingest(
            store,
            snapshot,
            "s-evaluation",
            data["recordingDate"],
            data["origin"],
            data["authorizationRef"],
        )
        started = time.monotonic()
        processing = run(store, cfg)
        library = current(store)
        record = {
            **identity,
            "seconds": round(time.monotonic() - started, 3),
            "results": processing,
            "jobsDone": all(j["stage"] == "done" for j in store.jobs()),
            "recordCounts": {k: len(v) for k, v in library.items()},
            "at": now(),
        }
        if processing or not (destination / "run.json").exists():
            write_json(destination / "run.json", record)
        # Manual reorganization uses the established apply-edits path. Never replace existing owner edits.
        if record["jobsDone"] and not (destination / "editable-library").exists():
            materialize(store)
            shutil.copytree(
                (store.root / "library/current").resolve(),
                destination / "editable-library",
            )
    finally:
        store.close()
    report_session(root)
    return {
        "result": destination.name,
        "jobsDone": record["jobsDone"],
        "records": record["recordCounts"],
        "report": str(root / "review.html"),
    }


def report_session(root):
    from .audio_benchmark import word_error_rate
    from difflib import unified_diff

    root, data = session(root)
    esc = lambda value: html.escape(str(value))
    sections = [
        '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; media-src \'self\' file:; script-src \'none\'"><meta name="viewport" content="width=device-width"><title>Private Fieldnotes review</title><style>body{overflow-wrap:anywhere;font:17px/1.6 system-ui;max-width:1150px;margin:auto;padding:24px;background:#faf8f2;color:#18332f}section,details{padding:18px;border:1px solid #b8c9bf;margin:16px 0;border-radius:10px;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere}audio{width:100%}.flag{border-left:6px solid #b45c20}a{color:#12645c}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #bbb;overflow-wrap:anywhere}</style></head><body><h1>Private recording evaluation</h1><p>Local-only. No clinical accuracy claim or publication approval is implied. Do not share this report.</p>'
    ]
    sections += [
        f'<p>Origin: {esc(data["origin"])}. Owner-selected date: {esc(data["recordingDate"])}. File timestamps do not establish recording clock time.</p><h2>Listen</h2><p>Original copy</p><audio controls preload="none" src="audio/original.wav"></audio><p>Normalized working copy (same time origin)</p><audio controls preload="none" src="audio/normalized.wav"></audio>'
    ]
    sections += [
        "<h2>Recollections — not ground truth</h2><pre>"
        + esc((root / "recollections.md").read_text())
        + "</pre>"
    ]
    asr = (
        load_json(root / "transcript.json")
        if (root / "transcript.json").exists()
        else {"segments": []}
    )

    def lines(t):
        return [
            f"[{s['start']:.3f}–{s['end']:.3f}] {s['text']}\n" for s in t["segments"]
        ]

    sections += [
        "<h2>Whisper transcription (unaltered)</h2><pre>"
        + esc("".join(lines(asr)))
        + "</pre>"
    ]
    if (root / "reference.json").exists():
        ref = transcript_valid(load_json(root / "reference.json"))
        corrected = ref.get("referenceStatus") == "manually-corrected"
        sections += [
            "<h2>Manual reference</h2><p>"
            + (
                "Marked manually corrected."
                if corrected
                else "Draft only: no WER is computed."
            )
            + "</p><pre>"
            + esc("".join(lines(ref)))
            + "</pre>"
        ]
        if corrected:
            transcript_valid(ref)
            wer = word_error_rate(
                " ".join(s["text"] for s in ref["segments"]),
                " ".join(s["text"] for s in asr["segments"]),
            )
            if wer is None:
                raise ValueError(
                    "Corrected reference must contain actual words before WER can be computed"
                )
            sections += [
                f"<p>Normalized WER versus your corrected reference: {wer:.2%}. This is not semantic or medical accuracy.</p><pre>"
                + esc(
                    "".join(
                        unified_diff(
                            lines(asr),
                            lines(ref),
                            fromfile="ASR",
                            tofile="Manual reference",
                        )
                    )
                )
                + "</pre>"
            ]
    annotations = list(csv.DictReader((root / "review.csv").open(newline="")))
    sections += [
        "<h2>Your review findings</h2><p>Edit review.csv to record missed, incorrect, invented, terminology, source-link, case-link, topic and study problems. Re-run report to refresh.</p><pre>"
        + esc(json.dumps(annotations, indent=2))
        + "</pre>"
    ]
    for result in sorted((root / "results").glob("*/run.json")):
        meta = load_json(result)
        store = Store(result.parent / "workspace")
        try:
            library = current(store)
        finally:
            store.close()
        sections += [
            f"<section><h2>{esc(meta['model'])} — {esc(meta['input'])}</h2><p>Run: {esc(result.parent.name)}<br>Input SHA256: {esc(meta['inputSha256'])}</p><p>{esc(meta['seconds'])} seconds; {esc(meta['recordCounts'])}. Processing complete: {esc(meta['jobsDone'])}.</p>"
        ]
        for d in sorted(
            library["discussions"],
            key=lambda d: min(s["startSeconds"] for s in d["segments"]),
        ):
            unclassified = "unclassified-source" in d["topics"]
            sections += [
                f'<details class="{"flag" if unclassified else ""}" open><summary>{esc(d["title"])}</summary><p>ID: {esc(d["id"])}; topics: {esc(d["topics"])}</p>'
            ]
            for source in d["segments"]:
                sections += [
                    f'<a href="audio/normalized.wav#t={source["startSeconds"]},{source["endSeconds"]}">Listen {source["startSeconds"]:.2f}–{source["endSeconds"]:.2f}s</a> '
                ]
            sections += ["<pre>" + esc(d["account"]) + "</pre><ul>"]
            sections += [
                "<li><strong>"
                + esc(f["kind"])
                + "</strong>: "
                + esc(f["text"])
                + "</li>"
                for f in d["facts"]
            ]
            sections += ["</ul></details>"]
        for c in library["cases"]:
            sections += [
                f"<p>Case {esc(c['id'])}: diagnosis {esc(c['diagnosis'] or 'Unknown')}; outcome {esc(c['outcome'] or 'Unknown')}; source discussions {esc(c['sourceDiscussionIds'])}.</p>"
            ]
        for article in library["articles"]:
            sections += [
                f"<details><summary>Article target: {esc(article['title'])} ({esc(article['id'])})</summary><pre>{esc(article['body'])}</pre></details>"
            ]
        for q in library["questions"]:
            sections += [
                f"<details><summary>Study: {esc(q['prompt'])}</summary><pre>{esc(q.get('answer', q.get('explanation', '')))}</pre></details>"
            ]
        sections += [
            "<p>To reorganize unclassified information, edit this result’s editable-library snapshot, retaining IDs and source references, then use vet-pipeline apply-edits against its workspace. Patient/topic context stays unassigned until reviewed.</p></section>"
        ]
    sections += ["</body></html>"]
    atomic_write(root / "review.html", "\n".join(sections))
    return {
        "report": str(root / "review.html"),
        "openLocally": "Open this file in your local browser; no public server or AI is needed to review.",
    }
