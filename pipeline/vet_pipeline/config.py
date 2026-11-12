from __future__ import annotations
import copy, json, os, tomllib
from pathlib import Path
from .locations import local_path
from urllib.parse import urlparse

DEFAULT = {
    "provider": {
        "kind": "mock",
        "extraction_protocol": "grounded-v2",
        "model": "fixture",
        "base_url": "http://127.0.0.1:11434",
        "api_key_env": "VET_AI_API_KEY",
        "allow_remote": False,
        "allow_paid": False,
        "timeout_seconds": 120,
        "context_char_limit": 12000,
        "context_window": 8192,
        "tokenizer_path": "",
        "tokenizer_sha256": "",
        "chat_overhead_tokens": 64,
        "context_safety_tokens": 128,
        "max_output_tokens": 4096,
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
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
        "max_text_context": -1,
        "temperature_fallback": True,
        "audio_filter": "none",
        "runtime": "",
        "runtime_sha256": "",
        "model_sha256": "",
        "vad_model": "",
        "vad_model_sha256": "",
        "gpu_name": "7900",
    },
    "archive": {"timezone": "Unknown until configured"},
    "retry": {"max_attempts": 3, "base_delay_seconds": 30},
    "github": {
        "enabled": False,
        "checkout": "",
        "allow_clinical": False,
        "retry_seconds": 60,
        "max_retry_seconds": 3600,
        "verify_interval_seconds": 3600,
    },
    "question_verification": {"enabled": False, "references_dir": "", "max_reference_age_days": 180, "reference_char_limit": 14000, "auto_refresh_sources": False, "refresh_days": 7, "max_output_tokens": 32768, "max_attempts": 2, "timeout_seconds": 1800, "research_enabled": False, "search_results": 4},
    "shift_context": {"enabled": False, "context_window": 98304, "max_output_tokens": 32768,
                      "gpu_layers": 32, "timeout_seconds": 3600,
                      "chat_template_path": "", "chat_template_sha256": "",
                      "native_reasoning_effort": "high", "stream_responses": False,
                      "temperature": .6, "top_p": .95, "top_k": 20, "min_p": 0.0},
    "retention": {"enabled": False, "days": 14, "require_remote": True,
                  "automatic_deletion": False, "retain_source_audio": True,
                  "retain_transcripts": True},
    "unattended": {"simulation_root": "", "gpu_busy_limit": 20,
                   "gpu_memory_limit_mb": 3000, "session_hours": 8,
                   "reuse_idle_ollama": True, "reuse_free_memory_mb": 1024,
                   "transcription_free_memory_mb": 6000,
                   "timezone": "America/Detroit", "inhibit_sleep": True},
    "backup": {
        "remote": "",
        "allow_clinical_remote": False,
        "timeout_seconds": 300,
        "executable": "rclone",
        "config_file": "",
    },
    "usb": {
        "roots": [],
        "device_label": "",
        "device_uuid": "",
        "device_serial": "",
        "automount_read_only": False,
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
        with local_path(path).open("rb") as f:
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
    if not (0 <= out["unattended"]["gpu_busy_limit"] <= 100
            and out["unattended"]["gpu_memory_limit_mb"] >= 0
            and 1 <= out["unattended"]["session_hours"] <= 24):
        raise ValueError("Invalid unattended resource/session limits")
    limits = out['unattended']
    if type(limits['reuse_idle_ollama']) is not bool or any(
        isinstance(limits[key], bool) or not isinstance(limits[key], (int, float))
        or not 1 <= limits[key] <= 1048576
        for key in ['reuse_free_memory_mb', 'transcription_free_memory_mb']
    ):
        raise ValueError('Invalid idle-model reuse/headroom settings')
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
    g = out["github"]
    if (g["enabled"] and not g["checkout"]) or not (
        1 <= g["retry_seconds"] <= g["max_retry_seconds"]
        and g["verify_interval_seconds"] >= 1
    ):
        raise ValueError("Invalid private GitHub synchronization settings")
    v=out['question_verification']
    if (type(v['enabled']) is not bool or type(v['auto_refresh_sources']) is not bool
        or type(v['research_enabled']) is not bool or not 1 <= v['search_results'] <= 6
        or not 1<=v['max_attempts']<=3 or v['max_output_tokens']<256
        or v['reference_char_limit']<100 or v['max_reference_age_days']<1
        or not 1<=v['refresh_days']<=v['max_reference_age_days'] or v['timeout_seconds']<=0):
        raise ValueError('Invalid independent question verification settings')
    p = out["provider"]
    if (
        p["context_window"] < 512
        or p["max_output_tokens"] < 1
        or min(p["chat_overhead_tokens"], p["context_safety_tokens"]) < 0
    ):
        raise ValueError("Invalid inference token budget")
    if out["provider"]["extraction_protocol"] not in ["legacy", "grounded-v2"]:
        raise ValueError("Unknown extraction protocol")
    if t["kind"] not in ["faster-whisper", "whisper-cpp", "parakeet"]:
        raise ValueError("Unknown transcription backend")
    if not 1 <= t["threads"] <= 16 or t["timeout_seconds"] <= 0 or t["gpu_device"] < 0:
        raise ValueError("Invalid transcription resource limits")
    if type(t['max_text_context']) is not int or not -1 <= t['max_text_context'] <= 16384 or type(t['temperature_fallback']) is not bool:
        raise ValueError('Invalid Whisper decoding controls')
    if t['audio_filter'] not in ['none', 'highpass', 'denoise'] or (t['audio_filter'] != 'none' and t['kind'] not in ['whisper-cpp', 'parakeet']):
        raise ValueError('Invalid ASR audio filter')
    if t['kind'] == 'parakeet' and any(not t[k] for k in ['runtime', 'runtime_sha256', 'model', 'model_sha256', 'vad_model', 'vad_model_sha256', 'gpu_name']):
        raise ValueError('Parakeet requires pinned local runtime, weights and an explicit GPU')
    s = out['shift_context']
    if (type(s['enabled']) is not bool or type(s['stream_responses']) is not bool
        or s['context_window'] < 512 or s['max_output_tokens'] < 1 or s['timeout_seconds'] <= 0
        or bool(s['chat_template_path']) != bool(s['chat_template_sha256'])
        or s['native_reasoning_effort'] not in ['low', 'medium', 'high', 'xhigh']
        or not 0 <= s['temperature'] <= 2 or not 0 < s['top_p'] <= 1
        or not 0 <= s['min_p'] <= 1 or s['top_k'] < 0):
        raise ValueError('Invalid whole-shift inference settings')
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
