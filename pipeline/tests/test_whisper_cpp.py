import json
import subprocess
import wave
from types import SimpleNamespace

import pytest
from vet_pipeline.ingest import ingest, transcribe
from vet_pipeline.whisper_cpp import transcribe_cpp


@pytest.mark.parametrize('decode_settings,expected_flags', [
    ({}, []),
    ({'max_text_context': 0, 'temperature_fallback': False}, ['-mc', '0', '-nf']),
])
def test_cpp_checkpoint_survives_extraction_interruption(
    store, cfg, tmp_path, monkeypatch, decode_settings, expected_flags
):
    wav = tmp_path / "synthetic.wav"
    with wave.open(str(wav), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 16000)
    executable = tmp_path / "whisper-cli"
    model = tmp_path / "model.bin"
    executable.touch()
    model.touch()
    cfg["transcription"].update(
        kind="whisper-cpp", executable=str(executable), model=str(model)
    )
    cfg['transcription'].update(decode_settings)
    calls = []

    def infer(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 1800
        assert args[args.index("-dev") + 1] == "0"
        for flag in expected_flags:
            assert flag in args
        if not expected_flags:
            assert '-mc' not in args and '-nf' not in args
        from pathlib import Path

        Path(args[-1] + ".json").write_text(
            json.dumps(
                {
                    "transcription": [
                        {
                            "offsets": {"from": 100, "to": 1122},
                            "text": "Synthetic unknown outcome.",
                        }
                    ]
                }
            )
        )
        return SimpleNamespace(stderr="whisper_backend_init_gpu: using Vulkan0 backend")

    monkeypatch.setattr(subprocess, "run", infer)
    job_id, _ = ingest(store, wav, "s-test", "2000-01-01", "synthetic", "test")
    first = transcribe(store, store.get(job_id), cfg)
    # Restart at the checkpoint, without requiring the source or another inference call.
    (store.root / "inputs" / f"{job_id}.wav").unlink()
    assert transcribe(store, store.get(job_id), cfg) == first
    assert len(calls) == 1
    assert first["segments"][0]["start"] == 0.1
    assert first["segments"][0]["end"] == 1.0
    assert (
        first["transcriptionBackend"]["timestampAdjustments"][0]["originalEnd"] == 1.122
    )
    assert first["transcriptionBackend"]["gpuAccelerationConfirmed"]
    assert first['transcriptionBackend']['decodingSettings']['temperatureFallback'] == cfg['transcription']['temperature_fallback']


def test_cpp_failure_does_not_create_checkpoint(store, cfg, tmp_path, monkeypatch):
    wav = tmp_path / "synthetic.wav"
    with wave.open(str(wav), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 1600)
    exe = tmp_path / "exe"
    exe.touch()
    cfg["transcription"].update(kind="whisper-cpp", executable=str(exe), model=str(exe))
    job_id, _ = ingest(store, wav, "s-test", "2000-01-01", "synthetic", "test")

    def interrupted(*args, **kwargs):
        raise subprocess.TimeoutExpired("whisper-cli", 1)

    monkeypatch.setattr(subprocess, "run", interrupted)
    with pytest.raises(subprocess.TimeoutExpired):
        transcribe(store, store.get(job_id), cfg)
    assert not (store.root / "transcripts" / f"{job_id}.json").exists()


def test_cpp_missing_files_fail_without_download(tmp_path):
    with pytest.raises(ValueError, match="existing local"):
        transcribe_cpp(tmp_path / "test.wav", {"executable": "", "model": ""})


@pytest.mark.parametrize(
    "origin,authorization", [("synthetic", ""), ("authorized-record", "")]
)
def test_real_audio_benchmark_requires_matching_origin_and_authorization(
    tmp_path, origin, authorization
):
    from vet_pipeline.audio_benchmark import benchmark_audio

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"origin": "authorized-record", "recordings": []}))
    with pytest.raises(ValueError):
        benchmark_audio(
            manifest,
            tmp_path / "report.json",
            "whisper-cpp",
            "",
            origin=origin,
            authorization_ref=authorization,
        )
