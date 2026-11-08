# Whole-shift speaker correction and repetition exclusion

The organized installation lives in `~/FieldNotes/`; see [Local layout](LOCAL_LAYOUT.md). Historical paths in this document still work through compatibility shortcuts. Use the new layout for new work.

This is still a private evaluation, not a verified identity system or a replacement
for normal nightly processing. Original audio, full transcripts, previous speaker
maps and model responses are retained. No publication or clinical cloud upload.

## What was wrong

The first implementation did keep a roster across files, but its fixed-reference
similarity/margin test was inappropriate for these measurements. It produced214
labels from215local voice groups: effectively a new label almost every time.
Successful JSON/inference tests did not establish useful speaker recognition.

Another issue was counting silence inside a Whisper interval against speaker
coverage. The new optional alignment judges dominance over detected speech,
with minimum coverage safeguards. Mixed/poorly detected passages remain uncertain;
one brief sound cannot label a long unsupported transcript passage. Legacy reports
keep their original alignment behavior.

## Revised evaluation

`global_speakers.py` compares the shift's local voice measurements together.
It reuses all102saved segmentation checkpoints; Whisper and segmentation are not
rerun. Similarity thresholds alone do not prove two recordings contain one person.

One additional embedding candidate was evaluated: NVIDIA TitaNet-Large, supplied
as a101,405,493-byte ONNX model by Sherpa. This is local CPU inference in the
existing isolated Python3.12environment; no NVIDIA GPU, Torch or driver install.
The [NVIDIA model card](https://huggingface.co/nvidia/speakerverification_en_titanet_large)
describes speaker embeddings and the CC-BY-4.0 license. Attribution is also saved in
the private model manifest. The original WeSpeaker weights/manifest are unchanged.

```bash
cd /home/quinten/vet-knowledge-library
pipeline/.venv/bin/python scripts/setup-speaker-models.py \
  ~/.local/share/vet-fieldnotes-ai/models/speakers --titanet
```

Model-specific score scales matter: the original embeddings had a strong common
component; unsupervised centering of TitaNet hurt the supplied known-owner reference
similarity. The final experimental candidate uses raw TitaNet similarity, average
linkage with a.55merge threshold and.25minimum cross-pair floor, plus exclusions
for overlapping local voices. Different local clusters in one chunk are not
automatically different people: local diarization can split one voice itself.
These parameters are provisional, not calibrated identity confidence.

The owner supplied clear known-self passages across files. Suitable isolated
references anchor that one identity before automatic grouping. We do not assume
every voice audible near a reference is the owner. A noisy reference with no
detected speech and a short potentially mixed exchange are not used as anchors.
Reference agreement is therefore **supervised**, not an independent accuracy test.
Other members of an owner-anchored group remain acoustic inferences.

The current map has120unverified acoustic groups,17spanning multiple recordings.
Those counts are not verified people or an accuracy percentage. False splits,
false merges, missed speech, ASR timing errors and faint secondary voices remain
limitations. No permanent client/staff roster was created. Do not claim solved
speaker recognition until the owner checks representative audio.

Replacement embeddings have separate per-chunk bounded-attempt checkpoints bound
to the original WAV, segmentation result and model hash. Grouping settings,
replacement caches and owner references are also hash-bound. Use a fresh experiment
for changed inputs/settings; never relabel already-completed knowledge inference
in place. Earlier centered-score and unseeded trials remain private for comparison.

## Five-repeat exclusion

The owner requested excluding wording repeated five or more consecutive times.
`repetition_filter.py` detects normalized exact token sequences, within and across
Whisper segments, and records character ranges. It masks the entire detected run
from model input and rejects quotations overlapping excluded ranges. Focused source
copies use the same mask, so they cannot reintroduce the repeated text.

Forty runs are marked in this selected shift. Original words, source identifiers,
offsets and full transcript files stay intact and visible in private review. The
rule can exclude genuine repetition and miss other hallucinations; it is not a
medical or semantic truth check. It does not fix Whisper itself or bypass existing
ASR review holds. The threshold is explicit/configurable in the isolated preparation
API; ordinary grounded extraction now also uses5for future requests. Completed old
results are not retroactively overwritten. Private raw archives stay complete.

## Where to review and resume

Final private root:
`~/.local/share/vet-fieldnotes-evaluations/whole-night-context-20261107/shift-wide-speakers-v3-20261108/`

Owner-visible folder:
`~/Fieldnotes-private-review/Shift-wide-speakers-20261108/`

Open `Results.html` directly for readable notes/reference checks/transcripts.
`Speaker-labelled-transcript.md` is ready after grouping; `Medical-notes.md` updates
after new Qwen results. `Audio-review.html` opens the separate read-only loopback
viewer. Standalone files remain readable if viewer links expire.

Worker: `vet-fieldnotes-global-speakers-v3-20261108.service`.
Viewer: `vet-fieldnotes-global-speakers-review-20261108.service`.

The new extraction automatically waits for the original speaker-study Qwen run
to finish; both never intentionally use the GPU concurrently. At the startup
checkpoint the speaker stage and40-run mask are complete, with Qwen waiting for
the earlier job. Full-night96Kcontext/32Koutput and source validation are preserved.
No approval action is needed to continue private processing. Publication stays off.

Resume only if no healthy worker is running:
```bash
~/.local/share/vet-fieldnotes-ai/diarization-venv/bin/python \
  scripts/review-shift-context.py run-global-speakers \
  ~/.local/share/vet-fieldnotes-evaluations/whole-night-context-20261107/shift-wide-speakers-v3-20261108 \
  --models ~/.local/share/vet-fieldnotes-ai/models/speakers/titanet-models.json
```

Do not publish private reference annotations, voice vectors, source mappings,
capability URLs or actual case material. Keep all existing retention safeguards.
