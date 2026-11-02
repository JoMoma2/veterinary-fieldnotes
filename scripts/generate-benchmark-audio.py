"""Generate a synthetic speech corpus in a new local directory. No clinical audio or model downloads."""

import argparse
import ctypes
import ctypes.util
import json
import wave
from pathlib import Path
from vet_pipeline.synthetic_audio import resample_pcm16_mono

p = argparse.ArgumentParser()
p.add_argument("--output", required=True, type=Path)
p.add_argument("--corpus", choices=["basic", "pipeline"], default="basic")
p.add_argument(
    "--timed",
    action="store_true",
    help="Synthesize source utterances separately with known buffer boundaries",
)
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
utterances = {}
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
if a.corpus == "pipeline":
    from vet_pipeline.util import REPO

    texts = []
    for file in sorted((REPO / "fixtures/pipeline/transcripts").glob("[0-9]*.json")):
        if file.name.endswith(".expected.json"):
            continue
        original = json.loads(file.read_text())
        expected = file.with_suffix(".expected.json")
        terms = (
            json.loads(expected.read_text()).get("terminology", [])
            if expected.exists()
            else []
        )
        texts.append(
            (file.stem, " ".join(s["text"] for s in original["segments"]), terms)
        )
        utterances[file.stem] = [s["text"] for s in original["segments"]]
rows = []
for id, text, terms in texts:
    pcm = bytearray()
    boundaries = []
    for part in utterances.get(id, [text]) if a.timed else [text]:
        samples.clear()
        encoded = part.encode()
        lib.espeak_Synth(
            ctypes.c_char_p(encoded), len(encoded) + 1, 0, 1, 0, 1, None, None
        )
        lib.espeak_Synchronize()
        chunk = resample_pcm16_mono(b"".join(samples), rate)
        start = len(pcm) / 32000
        pcm.extend(chunk)
        boundaries.append({"start": start, "end": len(pcm) / 32000, "text": part})
        if a.timed:
            pcm.extend(b"\0\0" * 8000)
    file = a.output / f"{id}.wav"
    with wave.open(str(file), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    rows.append(
        {
            "id": id,
            "file": file.name,
            "reference": text,
            "terminology": terms,
            "referenceSegments": boundaries if a.timed else [],
        }
    )
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
