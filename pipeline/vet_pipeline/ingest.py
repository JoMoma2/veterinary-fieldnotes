from __future__ import annotations
import json, math, re, shutil, wave, uuid
from pathlib import Path
from .util import atomic_write, digest_file, now, write_json, load_json


def transcript_valid(t):
    if not isinstance(t, dict) or not isinstance(t.get("segments"), list):
        raise ValueError("Transcript needs a segments array")
    last = -1
    for s in t["segments"]:
        if not isinstance(s, dict) or not isinstance(s.get("text"), str):
            raise ValueError("Invalid transcript segment")
        a, b = s.get("start"), s.get("end")
        if (
            not all(
                isinstance(v, (float, int))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in (a, b)
            )
            or a < 0
            or b <= a
            or a < last
        ):
            raise ValueError("Invalid or unordered transcript offsets")
        last = a
    if not t["segments"]:
        raise ValueError("Transcript contains no speech")
    return t


def ingest(
    store, path: Path, shift_id: str, date: str, origin: str, authorization_ref: str
):
    import datetime

    datetime.date.fromisoformat(date)
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", shift_id):
        raise ValueError("Invalid shift ID")
    if origin not in ["synthetic", "authorized-record"]:
        raise ValueError("Invalid origin")
    if not authorization_ref:
        raise ValueError("Recording/processing authorization reference is required")
    kind = (
        "audio"
        if path.suffix.lower() == ".wav"
        else "transcript"
        if path.suffix.lower() == ".json"
        else None
    )
    if not kind:
        raise ValueError("Accepts WAV or timestamped transcript JSON only")
    before = path.stat()
    sha = digest_file(path)
    job_id = "r-" + sha[:24]
    existing = store.db.execute("SELECT * FROM jobs WHERE sha256=?", (sha,)).fetchone()
    if existing:
        return existing["id"], False
    # A partial voice-activation file is never queued until its contents and metadata are stable.
    if kind == "audio":
        try:
            wav = wave.open(str(path), "rb")
        except wave.Error:
            # Float/extended WAV headers need the local decoder; retain original bytes.
            from .audio_prepare import inspect_audio
            if not (inspect_audio(path)["durationSeconds"] or 0) > 0:
                raise ValueError("Empty or invalid WAV")
            wav = None
        if wav:
            with wav:
                if wav.getnframes() == 0:
                    raise ValueError("Empty WAV")
                frames = wav.getnframes()
                frame_size = wav.getnchannels() * wav.getsampwidth()
                seen = 0
                while chunk := wav.readframes(65536):
                    seen += len(chunk)
                if seen != frames * frame_size:
                    raise ValueError("Truncated WAV payload")
    else:
        transcript_valid(load_json(path))
    workspace_origin = store.db.execute("SELECT origin FROM jobs LIMIT 1").fetchone()
    if workspace_origin and workspace_origin["origin"] != origin:
        raise ValueError("Synthetic and real records require separate workspaces")
    existing_shift = store.db.execute(
        "SELECT origin,shift_date FROM jobs WHERE shift_id=? LIMIT 1", (shift_id,)
    ).fetchone()
    if existing_shift and (
        existing_shift["origin"] != origin or existing_shift["shift_date"] != date
    ):
        raise ValueError("A shift must have a consistent origin and date")
    sequence = store.db.execute(
        "SELECT COALESCE(MAX(sequence),-1)+1 FROM jobs WHERE shift_id=?", (shift_id,)
    ).fetchone()[0]
    target = store.root / "inputs" / f"{job_id}{path.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".copying")
    try:
        shutil.copyfile(path, temp)
        after = path.stat()
        if (
            after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or digest_file(temp) != sha
        ):
            raise ValueError("Source changed during import; retry once stable")
        with temp.open("rb") as f:
            import os

            os.fsync(f.fileno())
        temp.replace(target)
        import os
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        with target.open("rb") as retained:
            os.fsync(retained.fileno())
        directory = os.open(target.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        write_json(store.root / "source-metadata" / f"{job_id}.json", {
            "originalName": path.name, "sourceModifiedNs": before.st_mtime_ns,
            "sourceSizeBytes": before.st_size, "sha256": sha,
            "clockConfidence": "unknown", "dateBasis": "assigned import batch; not a verified recording clock",
        })
    finally:
        temp.unlink(missing_ok=True)
    with store.db:
        store.db.execute(
            "INSERT INTO jobs(id,sha256,shift_id,shift_date,origin,authorization_ref,source_name,source_mtime,source_kind,sequence,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                sha,
                shift_id,
                date,
                origin,
                authorization_ref,
                path.name,
                before.st_mtime,
                kind,
                sequence,
                now(),
            ),
        )
    return job_id, True


def transcribe(store, job, cfg):
    target = store.root / "transcripts" / f"{job['id']}.json"
    if target.exists():
        return transcript_valid(load_json(target))
    source = (
        store.root
        / "inputs"
        / f"{job['id']}{'.wav' if job['source_kind'] == 'audio' else '.json'}"
    )
    if job["source_kind"] == "transcript":
        t = transcript_valid(load_json(source))
    elif cfg["transcription"]["kind"] == "whisper-cpp":
        from .whisper_cpp import transcribe_cpp
        from .audio_prepare import normalize_copy
        needs_conversion = True
        try:
            with wave.open(str(source), "rb") as wav:
                needs_conversion = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2)
        except wave.Error:
            pass
        if needs_conversion:
            normalized = store.root / "normalized" / f"{job['id']}.wav"
            metadata = normalized.with_suffix(".json")
            if normalized.exists() and metadata.exists():
                saved = load_json(metadata)
                if saved["originalSha256"] != digest_file(source) or saved["normalizedSha256"] != digest_file(normalized):
                    raise ValueError("Saved normalized audio changed; preserve it for review")
            else:
                if normalized.exists():
                    # A crash between audio and manifest installation: retain that copy too.
                    normalized.rename(normalized.with_suffix(".interrupted-" + uuid.uuid4().hex + ".wav"))
                write_json(metadata, normalize_copy(source, normalized, max_seconds=86400))
            source = normalized
        t = transcribe_cpp(source, {**cfg["transcription"],
            "details_path": str(store.root / "transcription-details" / f"{job['id']}.json")})
    else:
        from faster_whisper import WhisperModel

        p = cfg["transcription"]
        if not p["model"]:
            raise ValueError(
                "Set transcription.model to a tested model or local model path"
            )
        model = WhisperModel(
            p["model"],
            device=p["device"],
            compute_type=p["compute_type"],
            local_files_only=not p["allow_model_download"],
        )
        segments, info = model.transcribe(
            str(source),
            language=p["language"] or None,
            vad_filter=True,
            word_timestamps=True,
        )
        t = {
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "words": [
                        {"start": w.start, "end": w.end, "word": w.word}
                        for w in (s.words or [])
                    ],
                }
                for s in segments
            ],
            "language": info.language,
        }
        transcript_valid(t)
    # Source mtime is preserved in the ledger, but never promoted to a reliable capture clock.
    write_json(target, t)
    return t
