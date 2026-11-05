"""Read-only shared Ollama/GPU admission checks; never evict another model."""
from pathlib import Path
import subprocess
import time

import httpx

from .evaluation import verified_local_model
from .runner import ProcessingDeferred


def ollama_clients():
    # Include server-side sockets: a remote or unidentifiable client must also
    # prevent admission. Polling HTTP clients are closed before this is called.
    try:
        result = subprocess.run(
            ['ss', '-H', '-tn', 'state', 'established',
             '( sport = :11434 or dport = :11434 )'],
            capture_output=True, text=True, check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        raise ProcessingDeferred('Cannot verify other Ollama clients; saved jobs remain queued') from None
    if result.stdout.strip():
        # An established keep-alive socket can be idle; conservatively wait.
        raise ProcessingDeferred('Another client has an open Ollama connection; waiting for shared use to finish')


def gpu_snapshot():
    devices = []
    for path in Path('/sys/class/drm').glob('card*/device/mem_info_vram_total'):
        try:
            if (path.parent / 'vendor').read_text().strip() == '0x1002':
                devices.append((int(path.read_text()), path.parent))
        except (OSError, ValueError):
            pass
    if not devices:
        raise ProcessingDeferred('AMD GPU resource telemetry unavailable; no unverified CPU fallback')
    total, device = max(devices)
    try:
        busy = int((device / 'gpu_busy_percent').read_text())
        used = int((device / 'mem_info_vram_used').read_text())
    except (OSError, ValueError):
        raise ProcessingDeferred('GPU telemetry temporarily unavailable') from None
    if not 0 <= busy <= 100 or not 0 <= used <= total:
        raise ProcessingDeferred('Invalid GPU telemetry; saved jobs remain queued')
    return {'busy': busy, 'used': used / 1024**2, 'free': (total - used) / 1024**2}


def resident_models(cfg):
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            response = client.get(cfg['provider']['base_url'].rstrip('/') + '/api/ps')
            response.raise_for_status()
            models = response.json()['models']
        if not isinstance(models, list) or any(not isinstance(m, dict) for m in models):
            raise ValueError('Invalid model metadata')
        return models
    except Exception:
        raise ProcessingDeferred('Local Ollama/model metadata is unavailable; saved jobs remain queued') from None


def _memory_admission(cfg, stage, digest, models, gpu):
    limits = cfg['unattended']
    if gpu['busy'] > limits['gpu_busy_limit']:
        raise ProcessingDeferred(f"Shared GPU busy ({gpu['busy']}%); inference deferred")
    if not models:
        if gpu['used'] > limits['gpu_memory_limit_mb']:
            raise ProcessingDeferred(f"Other GPU memory in use ({gpu['used']:.0f} MiB); inference deferred")
    elif not limits['reuse_idle_ollama']:
        raise ProcessingDeferred('Ollama has a resident model; idle reuse is disabled')
    elif stage == 'extract':
        # A different digest or context can trigger a reload/eviction. Reuse only
        # the exact tested model/context; do not guess at another model's needs.
        if not digest or len(models) != 1 or models[0].get('digest') != digest or models[0].get('context_length') != cfg['provider']['context_window']:
            raise ProcessingDeferred('Cached model/context differs from Fieldnotes; waiting without evicting it')
        size = models[0].get('size_vram')
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not 0 < size < float('inf'):
            raise ProcessingDeferred('Cached GPU memory metadata unavailable; inference deferred')
        if gpu['used'] - size / 1024**2 > limits['gpu_memory_limit_mb']:
            raise ProcessingDeferred('Other GPU allocations remain; cached-model reuse deferred')
    if stage == 'transcribe' and gpu['free'] < limits['transcription_free_memory_mb']:
        raise ProcessingDeferred('Insufficient free GPU memory for Whisper alongside cached allocations; waiting without unloading models')
    if stage == 'extract' and models and gpu['free'] < limits['reuse_free_memory_mb']:
        raise ProcessingDeferred('Insufficient GPU headroom for cached-model reuse; inference deferred')


def check_resources(cfg, stage):
    """Require a quiet interval, not merely an instantaneous idle GPU sample.

    This is cooperative admission, not a lock on applications we don't control.
    Another application can submit work after admission. Persistent HTTP sockets
    are conservatively busy because Ollama exposes no request-owner API.
    """
    if stage not in ['transcribe', 'extract']:
        raise ValueError('Unknown GPU processing stage')
    try:
        digest = verified_local_model(cfg)
    except Exception:
        raise ProcessingDeferred('Local Ollama/model metadata is unavailable; saved jobs remain queued') from None
    # Keep the interval fixed and short; repeated timer polls provide later retry.
    for sample in range(3):
        models = resident_models(cfg)
        ollama_clients()
        _memory_admission(cfg, stage, digest, models, gpu_snapshot())
        if sample < 2:
            time.sleep(1)
    # Catch a client that connected while the last GPU sample was being read.
    ollama_clients()
