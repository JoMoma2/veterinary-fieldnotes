"""Optional genuine Faster-Whisper smoke test using only generated speech. Never a clinical accuracy benchmark."""

import argparse, ctypes, ctypes.util, json, tempfile, wave
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--download-model", action="store_true")
args = p.parse_args()
name = ctypes.util.find_library("espeak-ng")
if not name:
    raise SystemExit(
        "Install espeak-ng to synthesize the test WAV, or use the pipeline with an authorized WAV."
    )
lib = ctypes.CDLL(name)
lib.espeak_Initialize.restype = ctypes.c_int
rate = lib.espeak_Initialize(2, 0, None, 0)
if rate <= 0:
    raise SystemExit("Speech synthesis failed to initialize")
samples = []


@ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p
)
def callback(data, count, events):
    if data and count:
        samples.append(ctypes.string_at(data, count * 2))
    return 0


lib.espeak_SetSynthCallback(callback)
lib.espeak_SetVoiceByName(b"en-us")
text = b"This is a synthetic training recording. The outcome is unknown. Do not invent a diagnosis."
lib.espeak_Synth(ctypes.c_char_p(text), len(text) + 1, 0, 1, 0, 1, None, None)
lib.espeak_Synchronize()
with tempfile.TemporaryDirectory(prefix="vet-audio-smoke-") as tmp:
    file = Path(tmp) / "synthetic.wav"
    with wave.open(str(file), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(samples))
    from faster_whisper import WhisperModel

    model = WhisperModel(
        "tiny.en",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        local_files_only=not args.download_model,
    )
    segments, info = model.transcribe(str(file), language="en", vad_filter=True)
    rows = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    assert rows and all(r["end"] > r["start"] >= 0 for r in rows)
    assert "unknown" in " ".join(r["text"] for r in rows).lower()
    print(
        json.dumps(
            {"model": "tiny.en (smoke test only)", "segments": rows, "passed": True},
            indent=2,
        )
    )
