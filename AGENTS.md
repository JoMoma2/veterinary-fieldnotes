# Veterinary FieldNotes

Read the private hub `~/FieldNotes/SESSION_HANDOFF.md` first for current machine state and authorization. This file describes source maintenance; historical experiment journals are not current instructions.

## Current direction

Keep Parakeet TDT v3 with Silero speech detection for transcription and Qwen3.8 27B for local whole-shift extraction. The owner chose quality above speed and a small number of effective checks. Use the tested native model/template and reasoning settings; do not add a stack of reviewers or treat JSON validity, exact quotes or speed as medical accuracy. Speaker recognition is not selected.

Completed runs can be archived privately outside active discovery. Preserve recordings, transcripts, results and checkpoints unless the owner explicitly authorizes their deletion. Recorder clearing requires verified local archive copies and exact-file safeguards. Consult the private handoff and current operation receipts before cleanup; never rerun historical scripts blindly. Preserve existing uncommitted work.

Read the private handoff for current automation state. Processing, cloud storage and publication have separate authorizations. The owner has authorized automatic publication of future runs through a local privacy-screened public copy; completed archived tests remain excluded. Do not broaden that authorization to raw clinical uploads, paid inference or historical experiments.

## Privacy and source integrity

- Real audio, transcripts, identities, embeddings, source hashes, private report paths, capability URLs, credentials and private ledgers stay outside every public/source Git checkout. The hub itself must never become Git.
- Recording/local inference authorization, clinical remote storage and publication are separate permissions. Names removed alone do not establish privacy review.
- Only eligible real educational material enters production. Synthetic fixtures stay in separate test/demo datasets. Never deploy a demo build or synthetic readiness results.
- Retain original recordings, full transcripts and raw ASR. Normalize/filter separate copies with hashes; never rewrite source wording/times to make a model answer pass. Preserve frozen request bindings and successful checkpoints.
- Unknown patient identity, credentials, species, diagnoses and outcomes stay unknown. Acoustic groups are not confirmed identities. Keep unsupported or omitted material available privately.
- Source grounding establishes provenance, not medical truth. Real study-question publication requires the existing supported external-reference proof and the applicable publication authorization. Automatic privacy review is labelled as automated, never fabricated human review. Reference coverage is limited. Do not invent medical corrections.
- No paid API, clinical web search or external clinical inference/storage without authorization. Private GitHub sync has separate clinical gates; independent backup remains optional.
- Shared Ollama, other applications (including MMM/FCC), system Python, GPU drivers and service defaults remain intact. Do not unload another application's model or alter global settings for FieldNotes.

## Layout and workflow

`~/FieldNotes/app` is this source checkout. Private data, reports, configuration, models, tools and maintenance belong in the other hub folders; see `docs/LOCAL_LAYOUT.md`. Necessary OS unit/desktop registrations live in their standard user directories. `locations.local_path` resolves historical prefixes at access only; do not bulk-rewrite immutable saved artifacts or recreate retired shortcuts.

The Python pipeline uses a private SQLite ledger with WAL/FULL, content-hash import deduplication, stage/window checkpoints, transactional canonical records and portable Markdown/JSON. Normal stages are transcribe → extract → commit → done. Whole-shift mode transcribes recordings independently and then uses the complete shift for an episode map and detail requests. Same-named patients are not automatically merged; unclassified evidence remains retained. See `docs/NIGHTLY_WHOLE_SHIFT.md`.

`parakeet.py` and `native_asr.py` provide the selected local transcription backend with pinned runtime/weights, CPU VAD and explicit discrete Vulkan GPU selection. Raw replies survive review holds and successful windows survive interruptions. Overlap is retained; coarse audio-window bounds are labelled, never claimed as word timing. Whisper/Faster-Whisper and comparison tools remain source-compatible for recovery, without making them the active lineup.

Whole-shift input, reasoning and answer share context. Current selected settings are 81,920 context / 32,768 output per request with native thinking; leave those limits alone unless requested. Oversize input fails without source truncation. `shift_context` supports pinned native templates, decoding settings and private stream checkpoints. Historical comparison defaults are not production defaults. Model choices and settings never activate automation.

Public Astro/TypeScript content is validated by Zod and shared schemas, and Pagefind indexes built HTML. Private data is never a website build input. `publicProjection` and publication approvals bind exact content; changes invalidate approval. `auto_publication` uses a separate local, hash-bound privacy gate, literal redactions on a copy, opaque stable public IDs and independent question evidence. Raw source appendices, archive-only discussions and original source metadata remain private. Uncertain records stay private, successful privacy checks are checkpointed, and deployments retry without rerunning extraction. Preserve stable private IDs, source references, privacy gates and rollback compatibility.

Several discussions may share their first source position (`order`). Keep their permanent IDs unique and use `compareDiscussions` for consistent ordering in the archive and discussion numbering. Preserve the recording ID/sequence, source-bound and reference checks.

## Useful checks

From this checkout:

```bash
pipeline/.venv/bin/python -m pytest pipeline/tests -q
npm run check
npm test
npm run build
```

Use the installed Node runtime under `~/FieldNotes/tools/runtime` if needed; see LOCAL_LAYOUT.md. Run checks appropriate to the change, and avoid repeating already-passing suites without a reason. Public upstream/generated speech can check mechanics without exposing real recordings; it does not prove clinical accuracy. Build production from eligible public exports only. Publishing requires the owner's applicable authorization.

Machine-specific progress, paths and private outcomes belong only in the hub handoff. Keep that handoff concise and factual; inspect live state instead of reviving historical experiment instructions.

Public patient names follow the owner's fixed species/sex policy: male dog Spot,
female dog Bella, male cat Pickles, female cat Donut; unknown-sex dogs Dog X,
unknown-sex cats Cat X, and unknown species Patient X. Never add numbering or infer
traits from a name. Matching real animal names may remain when they are already
the assigned alias. People and clinics with matching names remain private. Scan
all public human-readable fields, retain private identity evidence outside Git,
and validate the final copy before publishing. Distinct cases keep distinct IDs.

The optional study researcher searches public literature using only short generic
medical concepts checked against the private identity catalog. Never send private
questions, transcripts or case histories to search providers. Public study-card
revisions are separate from the immutable private extraction and require their own
current independent evidence and privacy checks. See docs/PUBLIC_PRIVACY_STUDY.md.
