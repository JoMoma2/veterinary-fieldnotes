import json
from types import SimpleNamespace

import pytest

from vet_pipeline import resources
from vet_pipeline.config import config
from vet_pipeline.runner import ProcessingDeferred


@pytest.fixture
def quiet(monkeypatch, cfg):
    cfg['provider']['context_window'] = 8192
    monkeypatch.setattr(resources, 'verified_local_model', lambda c: 'selected-digest')
    monkeypatch.setattr(resources, 'resident_models', lambda c: [])
    monkeypatch.setattr(resources, 'ollama_clients', lambda: None)
    monkeypatch.setattr(resources, 'gpu_snapshot', lambda: {'busy': 0, 'used': 600, 'free': 23900})
    monkeypatch.setattr(resources.time, 'sleep', lambda n: None)
    return cfg


def cached(monkeypatch, digest='selected-digest', context=8192):
    monkeypatch.setattr(resources, 'resident_models', lambda c: [
        {'digest': digest, 'context_length': context, 'size_vram': 20000 * 1024**2}])
    monkeypatch.setattr(resources, 'gpu_snapshot', lambda: {'busy': 0, 'used': 20600, 'free': 3900})


def test_free_gpu_and_no_model_allows_both_stages(quiet):
    resources.check_resources(quiet, 'transcribe')
    resources.check_resources(quiet, 'extract')


def test_idle_compatible_model_can_be_reused_for_extraction(quiet, monkeypatch):
    cached(monkeypatch)
    resources.check_resources(quiet, 'extract')


@pytest.mark.parametrize('stage', ['transcribe', 'extract'])
def test_live_connection_still_defers_without_model_eviction(quiet, monkeypatch, stage):
    def connected():
        raise ProcessingDeferred('another client')
    monkeypatch.setattr(resources, 'ollama_clients', connected)
    with pytest.raises(ProcessingDeferred, match='another client'):
        resources.check_resources(quiet, stage)


def test_warm_model_cannot_squeeze_out_whisper(quiet, monkeypatch):
    cached(monkeypatch)
    with pytest.raises(ProcessingDeferred, match='Insufficient free GPU'):
        resources.check_resources(quiet, 'transcribe')


def test_small_idle_cached_model_leaves_whisper_headroom(quiet, monkeypatch):
    monkeypatch.setattr(resources, 'resident_models', lambda c: [{'digest': 'other-small-model'}])
    monkeypatch.setattr(resources, 'gpu_snapshot', lambda: {'busy': 0, 'used': 5000, 'free': 19000})
    resources.check_resources(quiet, 'transcribe')


@pytest.mark.parametrize('digest,context', [('other-model', 8192), ('selected-digest', 4096), ('selected-digest', 32768), ('selected-digest', None)])
def test_incompatible_cached_model_or_context_waits(quiet, monkeypatch, digest, context):
    cached(monkeypatch, digest, context)
    with pytest.raises(ProcessingDeferred, match='model/context differs'):
        resources.check_resources(quiet, 'extract')


def test_idle_reuse_can_be_disabled(quiet, monkeypatch):
    cached(monkeypatch)
    quiet['unattended']['reuse_idle_ollama'] = False
    with pytest.raises(ProcessingDeferred, match='reuse is disabled'):
        resources.check_resources(quiet, 'extract')


@pytest.mark.parametrize('gpu,reason', [
    ({'busy': 50, 'used': 20600, 'free': 3900}, 'Shared GPU busy'),
    ({'busy': 0, 'used': 23900, 'free': 600}, 'Other GPU allocations'),
    ({'busy': 0, 'used': 20600, 'free': 600}, 'Insufficient GPU headroom'),
])
def test_busy_gpu_and_headroom_still_protect_shared_work(quiet, monkeypatch, gpu, reason):
    cached(monkeypatch)
    monkeypatch.setattr(resources, 'gpu_snapshot', lambda: gpu)
    with pytest.raises(ProcessingDeferred, match=reason):
        resources.check_resources(quiet, 'extract')


def test_activity_during_quiet_interval_prevents_start(quiet, monkeypatch):
    samples = iter([{'busy': 0, 'used': 600, 'free': 23900}, {'busy': 80, 'used': 600, 'free': 23900}])
    monkeypatch.setattr(resources, 'gpu_snapshot', lambda: next(samples))
    with pytest.raises(ProcessingDeferred, match='Shared GPU busy'):
        resources.check_resources(quiet, 'extract')


def test_client_connecting_after_last_sample_prevents_start(quiet, monkeypatch):
    calls = []
    def connected():
        calls.append(1)
        if len(calls) == 4:
            raise ProcessingDeferred('new client')
    monkeypatch.setattr(resources, 'ollama_clients', connected)
    with pytest.raises(ProcessingDeferred, match='new client'):
        resources.check_resources(quiet, 'extract')


@pytest.mark.parametrize('stdout,expected', [('', False), ('0 0 127.0.0.1:4242 127.0.0.1:11434\n', True)])
def test_socket_inspection_is_read_only_and_checks_both_sides(monkeypatch, stdout, expected):
    def run(args, **kwargs):
        assert args == ['ss', '-H', '-tn', 'state', 'established', '( sport = :11434 or dport = :11434 )']
        return SimpleNamespace(stdout=stdout)
    monkeypatch.setattr(resources.subprocess, 'run', run)
    if expected:
        with pytest.raises(ProcessingDeferred, match='open Ollama connection'):
            resources.ollama_clients()
    else:
        resources.ollama_clients()


def test_missing_socket_tool_defers_safely(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(resources.subprocess, 'run', missing)
    with pytest.raises(ProcessingDeferred, match='Cannot verify'):
        resources.ollama_clients()


@pytest.mark.parametrize('setting,value', [('reuse_idle_ollama', 'yes'), ('reuse_free_memory_mb', 0), ('transcription_free_memory_mb', -1)])
def test_invalid_reuse_config_rejected(tmp_path, setting, value):
    path = tmp_path / 'settings.toml'
    path.write_text('[unattended]\n' + setting + ' = ' + json.dumps(value) + '\n')
    with pytest.raises(ValueError, match='reuse/headroom'):
        config(path)
