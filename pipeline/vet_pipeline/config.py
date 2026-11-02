from __future__ import annotations
import copy, json, os, tomllib
from pathlib import Path
from urllib.parse import urlparse

DEFAULT = {
    "provider": {
        "kind": "mock",
        "model": "fixture",
        "base_url": "http://127.0.0.1:11434",
        "api_key_env": "VET_AI_API_KEY",
        "allow_remote": False,
        "allow_paid": False,
        "timeout_seconds": 120,
        "context_char_limit": 12000,
        "context_window": 8192,
        "max_output_tokens": 4096,
        "thinking": None,
        "keep_alive": "0",
        "transcript_char_limit": 24000,
    },
    "transcription": {
        "kind": "faster-whisper",
        "model": "",
        "device": "cpu",
        "compute_type": "int8",
        "language": "en",
        "allow_model_download": False,
        "executable": "",
        "threads": 4,
        "gpu_device": 0,
        "timeout_seconds": 1800,
    },
    "archive": {"timezone": "Unknown until configured"},
    "retry": {"max_attempts": 3, "base_delay_seconds": 30},
    "retention": {"enabled": False, "days": 14, "require_remote": True},
    "backup": {"remote": "", "allow_clinical_remote": False, "timeout_seconds": 300},
    "usb": {
        "roots": [],
        "device_label": "",
        "sentinel": "",
        "glob": "**/*",
        "stable_seconds": 30,
        "origin": "authorized-record",
        "authorization_ref": "",
    },
}


def config(path: Path | None = None):
    out = copy.deepcopy(DEFAULT)
    if path:
        with path.open("rb") as f:
            data = tomllib.load(f)
        for k, v in data.items():
            if k not in out or not isinstance(v, dict):
                raise ValueError(f"Unknown configuration section {k}")
            if set(v) - set(out[k]):
                raise ValueError(f"Unknown configuration key in {k}")
            out[k].update(v)
    u = out["usb"]
    if u["sentinel"] and (
        Path(u["sentinel"]).is_absolute() or ".." in Path(u["sentinel"]).parts
    ):
        raise ValueError("USB sentinel must be a relative filename")
    if u["stable_seconds"] < 1:
        raise ValueError("USB stability interval must be positive")
    if (
        out["provider"]["transcript_char_limit"] < 1000
        or out["provider"]["context_char_limit"] < 0
    ):
        raise ValueError("Invalid inference context limit")
    if not 1 <= out["retry"]["max_attempts"] <= 10:
        raise ValueError("max_attempts must be 1–10")
    if out["retry"]["base_delay_seconds"] < 0 or out["retention"]["days"] < 0:
        raise ValueError("Negative retry or retention interval")
    t = out["transcription"]
    if t["kind"] not in ["faster-whisper", "whisper-cpp"]:
        raise ValueError("Unknown transcription backend")
    if not 1 <= t["threads"] <= 16 or t["timeout_seconds"] <= 0 or t["gpu_device"] < 0:
        raise ValueError("Invalid transcription resource limits")
    return out


def authorize_provider(cfg, origin):
    p = cfg["provider"]
    host = urlparse(p["base_url"]).hostname
    if p["kind"] == "mock":
        if origin != "synthetic":
            raise ValueError("Mock provider accepts synthetic inputs only")
        return
    if p["kind"] not in ["ollama", "openai-compatible"]:
        raise ValueError("Unknown provider")
    if not p["model"]:
        raise ValueError("Choose and benchmark an extraction model first")
    remote = host not in ["127.0.0.1", "localhost", "::1"]
    if remote and not p["allow_remote"]:
        raise ValueError(
            "Remote inference requires explicit allow_remote authorization"
        )
    if remote and urlparse(p["base_url"]).scheme != "https":
        raise ValueError("Remote inference requires HTTPS")
    if p["kind"] == "openai-compatible" and not p["allow_paid"]:
        raise ValueError(
            "API use requires explicit allow_paid authorization (subscriptions are not API permission)"
        )
    if (
        remote
        and origin == "authorized-record"
        and not cfg["backup"]["allow_clinical_remote"]
    ):
        raise ValueError(
            "Clinical third-party processing requires separate allow_clinical_remote authorization"
        )
