# Private owner voice references

These local tools prepare a voice-reference dataset without creating a clinical
knowledge job, uploading recordings or changing shift speaker labels. Existing
speaker-model weights are not retrained; separate windows preserve voice variation.

## Prepare and inspect

Pause normal USB importing before connecting a recorder containing a reference.
The tool never stops services or writes to recorder media. Choose a new private
output directory outside every Git checkout:

```bash
python scripts/enroll-owner-voice.py prepare /path/to/owner-recording.wav \
  --directory /absolute/private/reference \
  --library-workspace /absolute/private/library
```

The original is copied/hash-verified; its name/timestamps are retained privately.
A purpose exclusion protects that exact content from ordinary ingestion even if
renamed. A different recording with the same name remains importable. Invalid
registries fail closed. Already-created knowledge jobs are not silently reclassified.
Restore normal USB polling after verifying the exclusion, and preserve the registry
when resetting or moving a workspace.

```bash
python scripts/enroll-owner-voice.py inspect /absolute/private/reference \
  --models /absolute/private/speaker-models/models.json \
  --compare /absolute/private/compatible-shift-evaluation
```

Comparison is optional. Embedding models must match; target checkpoint hashes are
verified. Raw/normalized audio, model hashes and settings bind resumption. Completed
analysis is reused. Non-overlapping windows are checked for speech coverage,
overlap, level and clipping; these checks do not prove speaker identity.

## Confirm and evaluate

Ask whether other people, TV/podcasts or similar speech are audible before treating
all candidates as the owner. If other voices may be present, use separately verified
owner-only material while preserving originals. Do not infer background-speech
ownership from a dominant voice or a spoken introduction.

Only after explicit owner-only confirmation:

```bash
python scripts/enroll-owner-voice.py confirm-owner-only /absolute/private/reference
```

This enrolls a LOCAL evaluation reference. It does not deploy identity recognition,
rewrite shift labels or create a permanent client/coworker roster. Scores use several
supporting reference windows; one favorable outlier is insufficient. Similarity is
not calibrated identity probability. Validate known owner AND non-owner examples;
noise, microphone placement and speaking-style differences remain relevant.

Speaker clusters are not ground truth. Different IDs may be one person; one ID may
contain several people. Case identity, ownership and professional roles need words,
context and evidence beyond labels. The new uncertainty policy is versioned so
legacy inference request fingerprints remain unchanged unless selected explicitly.

## Blinded listening calibration

After confirming the reference, prepare a small private listening pack:

```bash
python scripts/enroll-owner-voice.py calibration /absolute/private/reference \
  --compare /absolute/private/compatible-shift-evaluation \
  --models /absolute/private/speaker-models/models.json
```

The standalone report embeds short source-audio excerpts and hides model scores,
old labels and sampling hints while the owner listens. Labels are Your voice,
Someone else, Multiple voices, or Unsure. None are prefilled or inferred from memory.
Answers stay in page memory until explicitly downloaded; there is no account,
network request, server write or persistent browser tracking.

Save the labels JSON privately, then analyze its local path:

```bash
python scripts/enroll-owner-voice.py evaluate /absolute/private/reference \
  --labels /absolute/private/listening-labels.json
```

Pack hashes bind labels to exact audio/profile inputs. Evaluation reports local
counts at candidate thresholds, never auto-selects/deploys one, and excludes mixed
or unsure examples from binary identity counts. This selected calibration sample
is not a population error-rate estimate. If no clear non-owner examples exist,
false-match safety remains unmeasured. No uncertain memory is a negative label.

## Private output

The workspace contains original/normalized audio, model/settings bindings,
candidates, optional comparisons and ownership confirmation. Keep these outside
Git/public build and search bundles. No source deletion or clinical extraction occurs.
The readable report embeds audio/timestamp buttons for local use without a server;
a text summary is also available. Reports containing embedded audio are private.

Actual enrollment identities, paths, hashes, measurements and progress belong only
in CONTINUATION.md inside the private workspace. Public docs should describe code
and synthetic tests, never private session results.
