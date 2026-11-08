# Whole-night context experiment

This is a separate private evaluation, not the default nightly extractor or a public
publication path. It reuses saved transcripts and does not invoke Whisper, edit the
live library, change global Ollama configuration, download models, or upload clinical
material. The original small-context results are preserved for comparison.

The owner's priority is educational quality and patient continuity, accepting up to
roughly eight hours of processing. Do not reduce source context/detail merely to
improve tokens per second.

## What changed

- A whole selected import batch is read together, across recording boundaries.
- Adjacent Whisper segments are grouped into roughly 500-character source blocks
  within each recording. No words are rewritten; original segment indices/offsets
  remain in the source map. This avoids spending tens of thousands of tokens on
  repeated long evidence identifiers and enum schemas.
- The model first proposes patient/discussion episodes, then writes a detailed
  account of each episode. Every detail request also contains the full available
  parsed-night transcript, not just an index summary. This is the same primary
  model, not multiple reviewing agents.
- High-recall hints enumerate all literal patient-label mentions and nearby source
  blocks, including separately annotated owner spelling variants. These are
  retrieval candidates, not automatic case links.
- Patient labels need literal name evidence. Unsupported labels are removed and
  their episodes kept unassigned. A nearby name alone does not prove a patient link.
  Model association reasons and uncertainty remain prominent in the report.
- Connected prose is allowed with quoted evidence. Summaries, facts, practical
  lessons and answers need exact eligible-source citations. Unique casing/spacing restoration or exact quote rebinding within the SAME
  recording is audited; no fuzzy words, cross-recording guesses or flagged-source
  acceptance is allowed. Validation establishes quotation provenance, not
  semantic/medical truth.
- Cards are optional and should test meaningful clinical/practical content. No
  deterministic quote-completion fallback is used.
- ASR-warning transcripts remain visibly marked context-only and cannot support
  facts, identity evidence or answers. Files without valid parsed timestamps stay
  available as raw review text/audio, outside extraction evidence. No ASR holds
  are silently bypassed.
- Per-request checkpoints bind source input, model digest and runtime settings;
  raw responses and rejected citations are retained privately. Retries are bounded
  to three; resource deferrals do not consume them; a failed detail episode does not
  erase other completed episodes.

## Verified installed model and allocation

Local `/api/show` identifies the installed `qwen3:30b` GGUF as Qwen3 MoE 30B-A3B,
finetune **Thinking**, version **2507**, Q4_K_M, advertised context262144. This is
the thinking-only variant, not the original switchable Qwen3 model. Therefore the
old production `thinking=false` setting should not be assumed to disable reasoning
correctly. The old chat template's unconditional `<think>` prefix is expected for
this variant, not evidence of a broken Ollama installation.

The experiment uses local `/api/chat`, `think=true`, context81920, output32768,
temperature0.6, top_p0.95, top_k20, min_p0, and40 requested GPU layers. Remaining
model/cache data uses system memory. A two-minute request-scoped keep-alive permits
prefix reuse without changing the shared Ollama service. Other client/GPU admission
checks still apply; no other model/service is forcibly unloaded or restarted.

These choices follow the [model author's variant-specific guidance](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507).
The 80K allocation/synthetic ambiguity probe succeeded:4.78s, peak22130MiB GPU,
valid structured `unknown` association and actual allocated81920 context. This is
not a clinical benchmark. Early64K allocation/template trials were retained
privately; unfinished trial requests were stopped during setup before selecting
the final model-compatible profile. Never present those as completed real results.

## Current private dataset and report

Selected import batch:78new recordings from the last completed shift, excluding the
35older recordings.72parsed transcripts are saved;52pass the existing ASR screen,
20are context-only due to warnings;6have raw output but no valid parsed transcript.
Recorded-audio total is approximately6.59h, not a verified shift duration. Source
clock/calendar values are unverified; selection uses import-batch identity.

The72parsed transcripts contain3490segments and about34866plain-text tokens.
Compact source grouping produces324blocks; the final whole-night index prompt is
approximately39241tokens, leaving space for32768generated tokens plus margin
inside81920. The same full context is used in detail requests. Counts do not imply
speech/medical accuracy, completeness, or correct associations.

Private root:
`~/.local/share/vet-fieldnotes-evaluations/whole-night-context-20261107/`

Owner-facing landing file:
`~/Fieldnotes-private-review/Last-night-context-review.html`

The private loopback viewer serves `review/shift-context.html`: connected accounts,
facts/reasoning, patient-association evidence, unknowns, practical lessons, optional
study questions, source quotations/audio timestamps, complete source review, and
previous articles/cards for comparison. Reports update after saved model calls;
refresh to see progress. `readable-notes.md` is a portable readable text version.
Model-internal reasoning remains private raw diagnostic data, not clinical evidence.

Do not put the landing file, capability URL, transcripts, reports, raw responses or
source mappings in Git. The review service binds only127.0.0.1. WAVs are read-only
hard links to retained local working copies; no originals are modified/deleted.

## Run and resume

```bash
cd /home/quinten/vet-knowledge-library
uv run --project pipeline --extra evaluation python scripts/review-shift-context.py prepare \
  --source-workspace /absolute/private/live-workspace \
  --shift-id OWNER_SELECTED_IMPORT_BATCH \
  --directory /absolute/private/new-experiment \
  --config /absolute/private/pipeline.toml

uv run --project pipeline --extra evaluation python scripts/review-shift-context.py run \
  /absolute/private/new-experiment

uv run --project pipeline --extra evaluation python scripts/review-shift-context.py report \
  /absolute/private/new-experiment
```

Preparation requires a new directory outside every actual Git checkout and a
local-only Ollama profile. It copies transcript/raw review snapshots, records source
hashes and model digest, and does not carry old extraction checkpoints into a new
experiment. Resume uses the same `run` command and verifies immutable source hashes,
recording order, model digest and saved request identities.

Current worker is transient user unit `vet-fieldnotes-context-20261107.service`;
the separate viewer is `vet-fieldnotes-context-review-20261107.service`. Check
`systemctl --user status UNIT` and the private `experiment.json`, `attempts.json`,
`calls/` artifacts. Resource deferral exits75 and retries after60s. Fatal exit1 does
not loop forever. The unit has an8h active-invocation limit; successful checkpoints
remain restorable if interrupted. A collected transient unit must be recreated with
systemd-run; it is not a permanent USB service.

This combines context, reasoning mode, prompt and readable-synthesis changes.
Compare usefulness and associations directly against audio/owner review; do not
attribute an improvement solely to context or claim clinical readiness. Production
defaults/publication remain unchanged until results are reviewed.

## Readable projection updates

`review-shift-context.py watch-report PRIVATE_ROOT` is a temporary model-free
finalizer. It refreshes only completed model responses, preserves original raw
replies and old checkpoint bytes, records citation repairs/rejected items, and
versions derived projections under projection-history/. It self-exits after the
experiment stops. Current unit: vet-fieldnotes-context-report-finalizer-20261107.
It never reruns inference, edits the source transcript/audio or changes the patient
index. Atomic completed-file updates keep concurrent report readers safe.

Initial real index:39241input tokens,482.857s,5episode proposals. First detail:
39834input tokens,463.979s. These counts/timings do not establish clinical quality;
the owner's source comparison remains necessary. Integrity verification confirms
all72parsed transcripts,78retained audio links and raw Whisper copies unchanged.

Named-source retrieval also considers explicit owner spelling annotations, stored
only in the private experiment. It does not infer a patient link from a spelling
match. The first named index episode missed other literal mentions; detail
requests now explicitly point to every mention plus nearby context while retaining
the whole night. This does not guarantee correct association.

First two detailed episodes are available. One narrative passed citation restoration;
another retains unresolved citations and is shown only in an explicitly unaccepted
review section. Accepted cited facts/cards remain separate. Do not confuse a
readable draft or real context allocation with validated clinical performance.

Current regression suite:207Python tests pass, including unchanged source copies,
full-context delivery, exact/unique same-recording citation restoration, refusal to
rebind across recordings, optional alias hints, immutable request identity, bounded
retry/resource deferral, partial failure isolation, versioned raw-preserving
projections, and escaped unaccepted-narrative display.
