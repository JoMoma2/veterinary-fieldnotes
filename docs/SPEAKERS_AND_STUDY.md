# Private speaker and medical-question evaluation

The organized installation lives in `~/FieldNotes/`; see [Local layout](LOCAL_LAYOUT.md). Historical paths in this document still work through compatibility shortcuts. Use the new layout for new work.

This opt-in experiment reuses the selected shift's saved audio and transcripts.
It does not invoke Whisper again, replace the live library, publish anything,
upload clinical data, or change global Ollama, GPU drivers, ROCm, MMM or FCC.
The owner asked for a brief startup check and then unattended completion.

## What the test does

1. CPU diarization finds speech turns in ten-minute recording-relative chunks.
2. English speaker embeddings attempt conservative matching across this shift's
   chunks/files. Labels are `Speaker_001`, etc. Distinct local voices are not
   merged within a chunk. Close/ambiguous global matches produce a new cluster;
   insufficient clean speech remains unknown. Matching scores are similarities,
   not identity probabilities. References stay fixed to avoid progressive drift.
3. Timestamp overlap attaches voice metadata to existing Whisper segments.
   Mixed or insufficient coverage is explicitly uncertain. This is not word-level
   speaker alignment; original transcript text and offsets are preserved.
4. Qwen receives the complete available parsed night, with compact speaker tags.
   It proposes episodes and speaker roles/relationships from conversational
   context, weighing explicit exchanges, repeated clues, contrary evidence and
   alternative explanations. Mere patient mentions, proximity, medical vocabulary
   or tone do not establish ownership or professional credentials.
5. Role proposals include supporting source quotes and subjective confidence
   between 0 and 1. Scores are **not calibrated probabilities**. Deterministic
   validation checks real speaker IDs and source quotation provenance, not the
   truth of a social relationship. All labels/roles remain reviewable hypotheses.
6. Detailed notes preserve useful case/practical knowledge. Study questions test
   only transferable veterinary **medical** knowledge, independent of a patient's
   identity or events on a particular shift. No case vignettes, record recall,
   dates/names, quote completion or nonmedical workflow trivia. Anecdotal findings
   cannot silently become general medical principles. Zero questions is allowed.

The shared prompt policy and obvious-violation filter are in `study_policy.py`.
The filter is not a semantic medical examiner. Owner review remains essential.
The old grounded extractor's forced cloze fallback has been removed for future
requests, but historical cards and extraction checkpoints are preserved.
Legacy whole-night A/B prompt/cache identities remain unchanged by default.

## Installation and models

The local test uses Python 3.12.15, sherpa-onnx/core 2.0.1, NumPy 2.5.4,
SoundFile 0.13.1, and the existing editable pipeline/evaluation dependencies.
These run in a separate environment, not the ordinary pipeline or system Python.

```bash
cd /home/quinten/vet-knowledge-library
uv venv --python 3.12 ~/.local/share/vet-fieldnotes-ai/diarization-venv
uv pip install --python ~/.local/share/vet-fieldnotes-ai/diarization-venv/bin/python \
  -r requirements-speakers.txt
pipeline/.venv/bin/python scripts/setup-speaker-models.py \
  ~/.local/share/vet-fieldnotes-ai/models/speakers
```

Do not recreate an already working environment unnecessarily. Public downloads:
Sherpa's pyannote segmentation 3.0 archive (6,958,444 bytes, included MIT license)
and English WeSpeaker VoxCeleb ResNet34 (26,534,365 bytes). Full-precision
segmentation is used. `models.json` records paths/source URLs/local SHA256 hashes;
these hashes bind reuse, not an independently verified upstream signature.
No Hugging Face token, cloud inference, Torch, ROCm or GPU installation is required.
Official API/model sources:
[Sherpa diarization models](https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html),
[diarization example](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/offline-speaker-diarization.py),
[speaker embedding example](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/speaker-identification.py).

The initial real 45-second audio probe took 0.86 seconds and produced two turns
and one voice embedding. This proves local inference works, not speaker accuracy.
CPU-only, four threads and lower worker priority avoid another GPU workload.
Qwen runs sequentially afterward using the existing GPU admission safeguards.
Speaker tags/schema need additional prompt room: this experiment uses 98,304 total
context tokens, 32,768 reserved generated tokens, and 32 requested GPU layers with
RAM offload. A request-local synthetic allocation probe succeeded in 9.67 seconds
(22 input / 219 generated tokens); this is not a medical or memory-peak benchmark.
No source text/output allowance was reduced, and global Ollama settings stay intact.

## Results and recovery

Current private experiment:
`~/.local/share/vet-fieldnotes-evaluations/whole-night-context-20261107/speakers-medical-20261108/`.
The dataset is frozen to the earlier selected batch: 78 recordings, 72 parsed
transcripts. Twenty ASR-warning transcripts are context-only; six raw-only files
remain available for review, not evidence. No new shift is selected at midnight.

Owner-visible copies refresh after saved results in:
`~/Fieldnotes-private-review/Speakers-and-medical-questions-20261108/`

- `Results.html`: standalone readable notes plus speaker-labelled transcript;
  no server, scripts, links or internet required to read it.
- `Medical-notes.md`: readable medical/case notes, question answers and role hypotheses.
- `Speaker-labelled-transcript.md`: full valid transcript wording with estimated voices.
- `Audio-review.html`: links to the separate read-only loopback audio viewer.
  If that viewer restarts, this landing can become stale; standalone copies still work.

Worker: `vet-fieldnotes-speakers-study-20261108.service`.
Viewer: `vet-fieldnotes-speakers-review-20261108.service`.
Check progress without printing patient text:
```bash
systemctl --user show vet-fieldnotes-speakers-study-20261108.service \
  -p ActiveState -p SubState -p MainPID -p Result
```

Private `speaker-progress.json` tracks the CPU stage; `experiment.json` tracks
subsequent Qwen extraction. Active CPU work does not mean extraction has started.
`speaker-chunks/` contains immutable per-chunk outputs, bounded-attempt state and
private embeddings for recovery. These are scoped to this experiment only and
never loaded as a future-shift client/coworker roster. No automatic deletion or
permanent staff enrollment/Quinten naming was enabled. Staff persistence is deferred.

Resume with `review-shift-context.py run-speakers PRIVATE_ROOT --models MANIFEST`
in the isolated environment when no healthy worker is already active. Successful
chunks are reused; deterministic label assignment resumes in the same order.
After speaker annotation, successful Qwen calls also resume independently.
Three attempts per chunk/request, retained failures and original source files
protect partial work. A failed speaker chunk leaves that audio interval unknown
and does not erase successful recordings or prevent private notes being generated.

The transient worker has an eight-hour invocation limit. It does not survive a
reboot as a permanent automation configuration; checkpoints remain restorable.
Do not promote this test to the nightly workflow until the owner reviews voice
splits/merges, role evidence, case continuity and medical question usefulness.

All private outputs, voice vectors, source mappings, real names and capability
URLs must stay outside every Git checkout and public build/search bundle.
