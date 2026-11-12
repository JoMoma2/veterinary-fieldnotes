from __future__ import annotations
import json, time
from .util import load_json, now, write_json, lock
from .ingest import transcribe
from .extraction import extract_recording, OutputLimitError
from .library import retrieve, commit, materialize
from .asr_quality import assess_segments, TranscriptionReviewRequired


class ProcessingDeferred(Exception):
    """An unavailable/shared GPU should not consume a recording's retry budget."""


def run(store, cfg, force_retry=False, before_stage=None, transcribe_only=False):
    if cfg.get("shift_context", {}).get("enabled") and not transcribe_only:
        from .shift_workflow import run as run_shift
        results=run_shift(store, cfg, force_retry, before_stage)
        if cfg.get('question_verification',{}).get('enabled') and not any(j['stage']=='transcribe' for j in store.jobs()):
            from .question_verification import run_checks
            run_checks(store,cfg)
        return results
    run_start = time.monotonic()
    results = []
    with lock(store.root):
        for old in store.jobs():
            job = store.get(old["id"])
            if job["stage"] in ['done', 'review']:
                continue
            if job["attempts"] >= cfg["retry"]["max_attempts"] or (
                not force_retry and job["retry_after"] > time.time()
            ):
                continue
            started = time.monotonic()
            timings = {}
            try:
                if job["stage"] == "transcribe":
                    if before_stage:
                        before_stage(job, "transcribe")
                    stage_start = time.monotonic()
                    transcribe(store, job, cfg)
                    timings["transcription"] = round(time.monotonic() - stage_start, 3)
                    store.update(
                        job["id"],
                        stage="extract",
                        attempts=0,
                        error=None,
                        retry_after=0,
                    )
                    job = store.get(job["id"])
                t = load_json(store.root / "transcripts" / f"{job['id']}.json")
                if job['stage'] == 'extract' and job['source_kind'] == 'audio':
                    quality = assess_segments(t['segments'])
                    write_json(store.root / 'transcription-quality' / f"{job['id']}.json", quality)
                    if quality['reviewRequired']:
                        raise TranscriptionReviewRequired('ASR repetition/quality warning; compare retained transcript with audio before extraction')
                if transcribe_only and job["stage"] == "extract":
                    results.append({"job": job["id"], "status": "transcript-ready", "timingSeconds": timings})
                    continue
                if job["stage"] == "extract":
                    if before_stage:
                        before_stage(job, "extract")
                    stage_start = time.monotonic()
                    context = retrieve(store, t, cfg["provider"]["context_char_limit"])
                    timings["retrieval"] = round(time.monotonic() - stage_start, 3)
                    stage_start = time.monotonic()
                    data = extract_recording(
                        store,
                        job,
                        t,
                        cfg,
                        context,
                    )
                    timings["extraction"] = round(time.monotonic() - stage_start, 3)
                    write_json(store.root / "extractions" / f"{job['id']}.json", data)
                    store.update(
                        job["id"], stage="commit", attempts=0, error=None, retry_after=0
                    )
                    job = store.get(job["id"])
                if job["stage"] == "commit":
                    stage_start = time.monotonic()
                    data = load_json(store.root / "extractions" / f"{job['id']}.json")
                    commit(store, job, t, data, cfg["archive"]["timezone"])
                    timings["commit"] = round(time.monotonic() - stage_start, 3)
                    store.update(
                        job["id"],
                        stage="done",
                        attempts=0,
                        error=None,
                        retry_after=0,
                        completed_at=now(),
                    )
                result = {"job": job["id"], "status": "done"}
                quality = [
                    load_json(p)
                    for p in (store.root / "quality" / job["id"]).glob("*.json")
                ]
                if quality:
                    result["quality"] = {
                        "classifiedSources": sum(
                            q.get("classifiedSources", 0) for q in quality
                        ),
                        "unclassifiedSources": sum(
                            q.get("unclassifiedSources", 0) for q in quality
                        ),
                        "warnings": sum(len(q.get("warnings", [])) for q in quality),
                        "repairs": sum(len(q.get("repairs", [])) for q in quality),
                    }
                    result["quality"]["reviewRequired"] = bool(
                        result["quality"]["unclassifiedSources"]
                        or result["quality"]["warnings"]
                    )
            except TranscriptionReviewRequired as error:
                store.update(job['id'], stage='review', attempts=0,
                             error='TranscriptionReviewRequired', retry_after=0)
                result = {'job': job['id'], 'status': 'review-required',
                          'stage': 'review', 'reason': str(error)}
            except ProcessingDeferred as error:
                result = {"job": job["id"], "status": "deferred", "reason": str(error)}
            except Exception as error:
                attempts = job["attempts"] + 1
                # Exception class only in durable logs: model/server error text may contain clinical data.
                store.update(
                    job["id"],
                    attempts=attempts,
                    error=type(error).__name__,
                    retry_after=time.time()
                    + cfg["retry"]["base_delay_seconds"] * 2 ** (attempts - 1),
                )
                result = {
                    "job": job["id"],
                    "status": "failed",
                    "stage": job["stage"],
                    "attempt": attempts,
                    "error": type(error).__name__,
                }
                if type(error) is ValueError or isinstance(error, OutputLimitError):
                    result["reason"] = str(error)
                elif isinstance(error, TimeoutError):
                    result["reason"] = (
                        "Operation timed out; retry is bounded and completed stages are preserved."
                    )
            result["timingSeconds"] = {
                **timings,
                "total": round(time.monotonic() - started, 3),
            }
            results.append(result)
            logfile = store.root / "events.jsonl"
            with logfile.open("a") as f:
                f.write(json.dumps({"at": now(), **result}) + "\n")
                f.flush()
            if result["status"] == "deferred":
                break
        try:
            stage_start = time.monotonic()
            materialize(store)
            write_json(
                store.root / "last-run-metrics.json",
                {
                    "at": now(),
                    "wallSeconds": round(time.monotonic() - run_start, 3),
                    "projectionSeconds": round(time.monotonic() - stage_start, 3),
                    "jobsAttempted": len(results),
                },
            )
        except Exception as error:
            results.append(
                {
                    "status": "failed",
                    "stage": "file-projection",
                    "error": type(error).__name__,
                    "reason": "Durable recording commits remain saved. Run again to regenerate portable files.",
                }
            )
    if not transcribe_only and cfg.get('question_verification',{}).get('enabled'):
        from .question_verification import run_checks
        run_checks(store,cfg)
    return results


def reset_failed(store, id):
    job = store.get(id)
    if not job:
        raise ValueError("Unknown job ID")
    fields = {'attempts': 0, 'retry_after': 0, 'error': None}
    if job['stage'] == 'review':
        fields['stage'] = 'extract' if (store.root / 'transcripts' / f'{id}.json').exists() else 'transcribe'
    store.update(id, **fields)
