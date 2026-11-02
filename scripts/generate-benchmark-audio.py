"""Generate a synthetic speech corpus in a new local directory. No clinical audio or model downloads."""

import argparse
import ctypes
import ctypes.util
import json
import wave
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--output", required=True, type=Path)
a = p.parse_args()
if a.output.exists():
    raise SystemExit("Choose a new directory; existing audio is never overwritten")
name = ctypes.util.find_library("espeak-ng")
if not name:
    raise SystemExit("espeak-ng library is required to generate the synthetic corpus")
a.output.mkdir(parents=True, mode=0o700)
lib = ctypes.CDLL(name)
lib.espeak_Initialize.restype = ctypes.c_int
rate = lib.espeak_Initialize(2, 0, None, 0)
lib.espeak_SetVoiceByName(b"en-us")
if rate <= 0:
    raise SystemExit("Speech synthesis initialization failed")
samples = []


@ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p
)
def callback(data, count, events):
    if data and count:
        samples.append(ctypes.string_at(data, count * 2))
    return 0


lib.espeak_SetSynthCallback(callback)
texts = [
    (
        "history",
        "This is a synthetic veterinary training discussion. The owner reports repeated litter box visits and increased grooming. Urine volume is unknown. Urethral obstruction is a concern, not a confirmed diagnosis. No treatment or outcome was stated.",
        ["grooming", "obstruction", "unknown"],
    ),
    (
        "uncertainty",
        "This is a synthetic teaching conversation. Feline infectious peritonitis is one possibility on a differential list. There is no test result. Do not invent a confirmed diagnosis or combine unrelated patients.",
        ["feline", "peritonitis", "diagnosis"],
    ),
]
rows = []
for id, text, terms in texts:
    samples.clear()
    encoded = text.encode()
    lib.espeak_Synth(ctypes.c_char_p(encoded), len(encoded) + 1, 0, 1, 0, 1, None, None)
    lib.espeak_Synchronize()
    file = a.output / f"{id}.wav"
    with wave.open(str(file), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(samples))
    rows.append({"id": id, "file": file.name, "reference": text, "terminology": terms})
manifest = a.output / "manifest.json"
manifest.write_text(
    json.dumps(
        {
            "origin": "synthetic",
            "generator": "espeak-ng local synthetic speech",
            "recordings": rows,
        },
        indent=2,
    )
    + "\n"
)
print(manifest)
