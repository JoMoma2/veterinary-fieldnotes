# USB automation and morning review

The organized installation lives in `~/FieldNotes/`; see [Local layout](LOCAL_LAYOUT.md). Historical path values in saved artifacts are translated internally. Old shell paths no longer exist; use the current layout for commands and new work.

**Current activation (2026-11-06):** owner requested resuming the registered recorder for the full private pipeline after reviewing filtered clips. Main timer is enabled. All audio/transcripts and intermediates are retained; no device deletion or cleanup is enabled. Public publication is explicitly on hold until morning approval. The recorder currently has35WAVs; import reads can be slow and all files are copied before AI begins. Leave the recorder plugged in until imports finish. The private Morning Review application launcher now uses the read-only loopback viewer; a publication-preview link shows saved candidate records without publishing anything. See latest SESSION_HANDOFF.md for current run status.

## Current status

**The real recorder is not connected. Production configuration, disabled systemd units and desktop launchers are staged; the production timer is not active.** Isolated synthetic timer tests actually ran Large V3 Vulkan and Qwen3 30B, interrupted/resumed processing, reconnected without duplicates and automatically verified private GitHub commits. This does not verify the actual recorder's USB behavior, filesystem, clocks or medical extraction quality.

Use Ubuntu's application search for **Fieldnotes — Register Recorder** and **Fieldnotes — Morning Review**. These launchers are installed under `~/.local/share/applications/`. No terminal or public web server is needed for normal use after registration.

## First actual shift — one-time registration

1. Connect your recorder while signed into Ubuntu. If it is not mounted, open it in **Files** first. Do not move/delete recordings. If no mounted USB filesystem with a UUID appears, registration refuses activation; actual hardware investigation is then needed.
2. Open **Fieldnotes — Register Recorder**. Select your recorder, checking the displayed filesystem UUID, serial (when available) and mount path. Registration reads device metadata and writes only the local private configuration; it never creates a marker or modifies recorder files.
3. Enter the appropriate **recording/local-processing authorization reference**. Ensure recording and retaining audio/transcripts for these first reviewed shifts is permitted. This is not indefinite retention permission.
4. For **private GitHub storage**, choose **Keep local only** unless separate authorization exists to store extracted knowledge, detailed case accounts and source quotations there. If authorization covers the material being synchronized, choose the explicit authorization option and enter its separate reference. Audio and full transcript files are never synchronized. Public publication remains separately reviewed.
5. Registration validates the current code's synthetic-test proof and preservation locks before enabling/starting the timer. Only the registered filesystem UUID and optional serial/label match. Other USB drives are ignored. No unsafe blanket USB rule is installed.
6. Leave Ubuntu **signed in**; locking the screen is fine and no terminal needs to remain open. Keep power connected and avoid other heavy GPU workloads. The user manager currently has **Linger=no**: after a reboot, queued work resumes when you sign in; logged-out/headless operation is not verified or enabled.
7. Open **Fieldnotes — Morning Review** when you return. Reload it to see fresh files if it was already open. Review the first shifts, especially medications, doses/units, negation, actual versus proposed treatment, case associations, unknown outcomes and source links. Do not treat successful processing as medical validation.

If local source retention or clinical third-party storage is not authorized, do not register that material. You can use the isolated 5–15 minute [manual evaluation workflow](FIRST_RECORDING.md) for appropriately authorized samples; it always disables cloud synchronization.

## What happens after connection

The user timer polls approximately every two minutes, also resuming queued work after login/restart even if the recorder has been removed. Matching uses registered UUID and serial where available, configured mount roots and optional label; a label/sentinel alone is insufficient for unattended activation. When the exact registered filesystem is unmounted, the worker requests a **read-only** mount through the existing UDisks service with no interactive authentication. The mount request uses the existing [UDisks read-only options](https://storaged.org/udisks/docs/udisksctl.1.html). If mounting is denied, the report records the failure and later polls retry. Already-mounted filesystems are read only by the application; it never remounts, edits, repairs or erases them.

File size and timestamp must remain unchanged across computer-observed polls for 30 seconds, independent of an incorrect recorder clock. Initial import normally starts on a subsequent poll (approximately 2–4 minutes after connection). Incomplete/changing/symlink/escaping paths are deferred or rejected individually. New WAVs are copied, hashed and recorded independently before AI processing. Original names, relative source paths, source size, filesystem modification nanoseconds, format/duration and SHA256 are retained privately. Hash deduplication survives reconnection and restart. Original recorder bytes remain untouched.

Whisper runs locally with Large V3 f16/Vulkan. Nonstandard rates/channels/PCM formats use a **separate normalized mono16k PCM16 copy**, never overwrite the imported original. Completed transcripts and raw Whisper JSON are checkpointed before grounded Qwen3 extraction. Existing evidence/source validation, conservative cases, append-only article updates, unclassified source preservation and question quarantine remain in use. If Qwen omits questions for an otherwise grounded discussion, one labeled literal source-recall cloze card can be prepared from an exact fact quote; it is not model-authored medical teaching. Unclassified excerpts do not produce fallback cards. Quality files count these fallback cards separately.

Work is sequential. Before each transcription/extraction stage, the worker checks installed local model metadata, established Ollama connections on port 11434 and AMD busy/VRAM telemetry across three samples over two seconds. Running MMM/FCC services or a cached model alone do not establish active inference. Any open Ollama connection, busy GPU or unavailable diagnostics defers processing without consuming retries. Even an idle persistent HTTP connection is conservatively treated as busy: Ollama's [model inventory](https://docs.ollama.com/api/ps) does not expose request ownership/activity. Nothing inspects prompt contents or modifies MMM/FCC, Ollama settings, drivers or model files; no forced model-unload request is issued.

An idle cached model can be reused for extraction only when its digest and context length exactly match the selected model/settings, with at least1,024 MiB free and at most3,000 MiB of unrelated allocations. Whisper may run alongside an idle cached model only with at least6,000 MiB free. Without cached models, the existing3,000 MiB used-memory ceiling remains. GPU activity must stay at or below20%. Defaults are `[unattended] reuse_idle_ollama=true`, `reuse_free_memory_mb=1024`, and `transcription_free_memory_mb=6000`; old private configurations inherit them without rewriting the file. Setting `reuse_idle_ollama=false` restores the blanket resident-model exclusion. Incompatible model/context or inadequate headroom waits without evicting the cache. Existing inference-request keep-alive settings are unchanged.

These are cooperative admission checks, **not an exclusive lock**: another application can submit work after admission. Fieldnotes does not interrupt that application or preempt an inference already running. Normal stage retries/checkpoints protect saved work if subsequent resource contention causes failure. A worker already running when these files change retains its loaded guard; the new rules take effect on the next worker start, with no forced restart.

A temporary [systemd `idle:sleep` inhibitor](https://www.freedesktop.org/software/systemd/man/latest/systemd-inhibit.html) is held during active work and released afterward. No permanent power setting is changed; if the session denies inhibition, processing continues and `sleepInhibited=false` is reported. Actual signed-out/inactive-session mount and power policy must be tested before depending on headless operation.

## Private locations and retention lock

Production workspace: **`~/.local/share/vet-fieldnotes-live/`**, owner-only and outside Git.

| Location | Contents |
| --- | --- |
| `retained/SHIFT_ID/` | Convenient original-filename links and transcript links grouped by import batch |
| `inputs/RECORDING_ID.wav` | Byte-identical imported originals; SHA is based on these bytes |
| `source-metadata/RECORDING_ID.json` | Original names/paths, exact filesystem metadata, hashes and format |
| `normalized/` | Separate converted working WAVs plus integrity manifests, when needed |
| `transcripts/RECORDING_ID.json` | Full saved ASR text and recording-relative offsets |
| `transcription-details/` | Full successful whisper.cpp JSON |
| `extractions/`, `quality/`, `quarantine/` | Grounded results, durable chunks/budgets, warnings and invalid questions |
| `library/current/` | Regenerable permanent knowledge projection; canonical records also live transactionally in the SQLite ledger |
| `unattended/state.json`, `events.jsonl` | Last meaningful work, batch state, interruptions and polling history |
| `master-sync/state.json`, `events.jsonl` | Durable private GitHub push/retry status |
| `review/index.html` | Offline morning interface, with per-recording audio/transcript/discussion pages and article/source links |
| `review/publication-candidates.json` | Generated, **unapproved** content-hash-bound review template |

The import date/batch is **not a verified recording clock or clinical shift date**. Filesystem times and relative offsets are preserved, not promoted to certain real-world discussion times. Filesystem-time/path sort order is unverified if the device clock is wrong. Reconnection within the configurable 8-hour import-session window keeps a batch; later new files create another import batch. Idle/reconnection polls do not replace the last meaningful batch. First connection may contain several old shifts; source timestamps/paths help owner review but the software does not invent their boundaries.

The initial private TOML explicitly uses:

```toml
[retention]
enabled = false
retain_source_audio = true
retain_transcripts = true
automatic_deletion = false
days = 14
require_remote = true
```

The unattended command refuses any configuration that weakens those locks. The older cleanup command also refuses deletion while the preservation flags are set, even if `enabled=true` is accidentally toggled. No audio, transcript, normalized source or extraction checkpoint is automatically deleted. `days` is a future cleanup eligibility threshold, **not** an automatic purge or permission for indefinite retention. Set workplace-compliant review/retention arrangements for the first shifts; any future deletion policy needs a separate explicit owner decision and tested change. Source recorder files are never cleanup targets.

## Morning report and failures

Transcription review holds are separate from transient failures. Severe repeated-phrase patterns or invalid Whisper timestamps preserve the entire raw output and place that recording in `review`, without spending retries or feeding it into extraction. Other files continue. Morning/recording/source-derived article pages show warnings; failed raw text is available as explicitly unvalidated output. Previously completed notes from flagged ASR remain private/unreviewed and are not automatically deleted. Absence of a screen warning does not establish accuracy. Held recordings do not automatically retry; an explicit `retry` re-evaluates quality rather than approving it. Start with the [manual reference workflow](FIRST_RECORDING.md) to diagnose/correct source speech; preserve prior ASR and do not reset completed/applied records to overwrite existing notes.

The offline report shows imported/processed/incomplete recordings, audio duration, measured worker/per-job times, batch article additions/updates, canonical case/question counts, unclassified discussions, last observed stage, GitHub status and pending jobs. Audio links seek to recorded offsets; articles link to their actual discussion entries. It refreshes on stage boundaries and after a poll, with no external assets, server or AI call. Recorded worker time includes interrupted/import/sync overhead but excludes timer waiting; per-job active metrics may exclude an unfinished interrupted attempt.

Recording failures retry up to 3 times per failed stage by default; other recordings continue. GPU/Ollama availability deferrals do not exhaust that budget. Completed transcripts/chunks/commits survive interruption. After fixing an exhausted recording's cause, an operator can reset only its retry state:

```bash
cd /home/quinten/vet-knowledge-library
uv run --project pipeline vet-pipeline --workspace ~/.local/share/vet-fieldnotes-live \
  --config ~/.config/vet-fieldnotes/pipeline.toml retry RECORDING_ID
```

The next timer poll resumes the saved stage. Inspect the morning report first; never erase checkpoints to retry. Private GitHub failures remain durably pending and retry with capped backoff without repeating AI. Independent backup is optional and cannot block local processing. The service template requires no backup key.

Operator diagnostics (not required each shift):

```bash
systemctl --user status vet-fieldnotes.timer vet-fieldnotes.service
journalctl --user -u vet-fieldnotes.service --since today
systemctl --user disable --now vet-fieldnotes.timer  # stops new polls
systemctl --user stop vet-fieldnotes.service         # interrupts current work; checkpoints retained
```

## Storage and publication

When either clinical-storage permission gate is off, the local outbox explicitly shows `awaiting-authorization` with `pending=true`; no Git/network sync attempt occurs. This is a deliberate local-only state and does not fail otherwise healthy local processing. Approving storage later resumes the durable snapshot without retranscription/extraction. Actual network/upload failures still report failure and retry with capped backoff. Explicitly requesting sync without authorization still returns an unsuccessful command status. The morning status refreshes when the normal sync stage next runs; an older error can remain visible while a recording is still extracting.

Private GitHub is primary remote knowledge storage, local is secondary. Registration's optional separate storage consent controls **both** clinical GitHub gates and records the reference in owner-only `~/.config/vet-fieldnotes/github-storage-authorization.json`. Keeping local-only leaves clinical pushes pending while all private processing/review completes. The synthetic tests verified actual private GitHub pushes from background units. Before live use, the exclusively synthetic master archive was preserved under `synthetic-validation/pre-live-*`, with a verified private commit and its integrity manifest/history intact. `production-storage.json` reserves the normal `archive/` path for authorized real knowledge, initially absent/empty; synchronization rejects synthetic records in that reserved namespace. This prevents test records mixing into first live storage. That does not grant clinical storage permission. GitHub receives only permanent knowledge/archive/manifests and sanitized status, not WAV, full transcript, SQLite, credentials or review HTML files. Source quotations in extracted records may still be sensitive and require the storage authorization.

Publication candidates are generated automatically without approving them. Copy the generated template to a **separate** owner approval file before editing; the candidate template is regenerated. The existing `scripts/publish-approved.py` validates content hashes and privacy/authorization approval, exports/builds/commits only approved public content and can push it. That push triggers Cloudflare's existing automatic Git deployment. No autonomous public publisher is activated, and public review never blocks private processing. See [OPERATIONS.md](OPERATIONS.md#edit-and-review-knowledge). Production remains empty until appropriately authorized publication.

## Reproduce setup and testing

Staging is already done on this computer; it does not activate production:

```bash
uv run --project pipeline --extra evaluation python scripts/register-recorder.py --stage
# No arguments opens the registration dialog after connecting the real recorder:
uv run --project pipeline --extra evaluation python scripts/register-recorder.py
```

For a terminal-based registration instead of the desktop launcher:

```bash
uv run --project pipeline --extra evaluation python scripts/register-recorder.py \
  --mount /ACTUAL/RECORDER/MOUNT --authorization-ref LOCAL-PROCESSING-REFERENCE --activate
# Only if separately authorized, additionally pass:
# --storage-authorization-ref PRIVATE-GITHUB-STORAGE-REFERENCE
```

Synthetic hardware/software proof is private at `~/.local/share/vet-fieldnotes-setup/synthetic-test.json`, bound to critical pipeline code SHA. An absent/stale proof prevents activation. The repeatable test below installs a temporary **synthetic-only** user timer, simulates attachment/removal, uses real installed models, sends SIGINT after saved work, checks unchanged checkpoints, reconnection and optional actual synthetic private-master sync. It removes its test units in `finally`; source/test artifacts remain retained. Never substitute clinical input in this helper.

```bash
uv run --project pipeline --extra evaluation python scripts/test-unattended.py \
  --audio-directory ~/.local/share/vet-fieldnotes-validation/local-ai-r2/pipeline7-audio \
  --directory ~/.local/share/vet-fieldnotes-validation/NEW-UNUSED-TEST-DIRECTORY
```

Omit `--sync-private` for local-only reruns. To repeat remote synchronization, additionally pass `--sync-private --master-checkout /PATH/SEPARATE-SYNTHETIC-PRIVATE-CHECKOUT`. It refuses a master reserved for production or containing clinical knowledge; never reuse the live namespace for synthetic tests. The registration workflow and actual read-only mounting still need verification with the physical recorder; those have not been claimed tested.
