"""Prepare/review a private real-recording pilot; no upload or publication commands."""

import argparse, json, os
from pathlib import Path
from vet_pipeline.evaluation import (
    prepare,
    transcribe_session,
    extract_session,
    report_session,
)

p = argparse.ArgumentParser()
s = p.add_subparsers(dest="command", required=True)
i = s.add_parser("inspect")
i.add_argument("wav", type=Path)
a = s.add_parser("prepare")
a.add_argument("wav", type=Path)
a.add_argument("--workspace", type=Path, required=True)
a.add_argument("--date", required=True)
a.add_argument("--authorization-ref", required=True)
a.add_argument(
    "--origin", choices=["authorized-record", "synthetic"], default="authorized-record"
)
for name in ["transcribe", "extract", "report"]:
    a = s.add_parser(name)
    a.add_argument("workspace", type=Path)
    if name != "report":
        a.add_argument("--config", type=Path, required=True)
    if name == "extract":
        a.add_argument("--input", choices=["asr", "reference"], default="asr")
a = p.parse_args()
os.umask(0o077)
try:
    if a.command == "inspect":
        from vet_pipeline.audio_prepare import inspect_audio

        r = inspect_audio(a.wav)
    elif a.command == "prepare":
        r = prepare(a.wav, a.workspace, a.date, a.authorization_ref, a.origin)
    elif a.command == "transcribe":
        r = transcribe_session(a.workspace, a.config)
    elif a.command == "extract":
        r = extract_session(a.workspace, a.config, a.input)
    else:
        r = report_session(a.workspace)
    print(json.dumps(r, indent=2))
    if r.get("jobsDone") is False:
        raise SystemExit(1)
except Exception as error:
    import sys
    # Do not print HTTP bodies or clinical payloads in tracebacks.
    message = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else type(error).__name__
    print(json.dumps({"error": type(error).__name__, "message": message}), file=sys.stderr)
    raise SystemExit(1)
