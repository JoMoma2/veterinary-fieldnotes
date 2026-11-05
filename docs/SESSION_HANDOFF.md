# Session handoff — registered recorder and first-run compatibility fix

## Latest state — 2026-11-05 (supersedes staged-state notes below)

**Commit recovery follow-up:** the first recording completed extraction but failed during canonical commit because `library.commit` still opened the compressed original with stdlib `wave`. It now reads codec-aware duration, and when normalized ASR audio exists it verifies its source hash/normalized hash/manifest and uses that exact input's sample duration. This also handles a 20.8 microsecond resampling boundary difference without rewriting citations or relaxing source bounds. The morning report refreshes pre-fix cached metadata once (`audioMetadataVersion=2`), correcting header-derived duration totals while preserving metadata/clock warnings. Synthetic regression covers 96k ADPCM→16k normalization, a final source quote at the normalized boundary, commit-only recovery without any repeated inference, deduplication and original hashes.

The actual first extraction passed an isolated private-ledger commit check before restart. Only Fieldnotes was interrupted, with all 213 saved transcript/extraction JSON hashes verified unchanged. Only its exhausted commit retry was reset. **The first recording is now done in the live ledger and visible in Morning Review**; at inspection there were two transcripts, two knowledge articles, 95 discussions and 423 study records, all private/unreviewed (these counts do not establish medical quality). The second recording's extraction chunks remain resumable; inspect current state for newer progress. Private repair validation lives under `~/.local/share/vet-fieldnotes-repairs/`, outside Git. No audio/transcript/extraction files or clinical text were committed or uploaded.

Intentional local-only storage had also been incorrectly reported as upload failure. `sync_pending_master` now saves `status=awaiting-authorization,pending=true,attempts=0` before any Git/network operation when either clinical-storage gate is off. Local run/unattended/nightly processing no longer exits failed solely for that status; explicit sync requests and actual network/recording errors still fail. Both clinical gates remain false; do not authorize uploads on the owner's behalf. Granting both permissions later changes the existing fingerprint and resumes the durable snapshot without repeating AI. **148 Python tests passed** including unauthorized-no-Git-call, later authorized local-bare-remote sync, source-boundary integrity and status regressions. Timer is enabled and worker was restarted with these fixes; no MMM/FCC/Ollama/global GPU settings changed. Old master-sync failure state is replaced when the next normal sync stage runs, after ongoing extraction; do not interrupt inference just to refresh that status.

**Latest guard update:** the owner explicitly authorized borrowing idle shared Ollama/GPU capacity while preserving the current run. `resources.py` now samples open connections on port 11434 and GPU activity three times over two seconds, permits idle exact-digest/context extraction reuse with1,024 MiB spare, and requires6,000 MiB free for Whisper beside cached models. Other clients, incompatible context/digest, unknown diagnostics or insufficient headroom defer; no explicit unload, global configuration change or MMM/FCC restart. HTTP keep-alive sockets are conservatively busy; this cannot exclude a request arriving after admission. New settings are defaults merged into the existing private config on the next process, not a live config rewrite. The in-progress worker was not restarted and retained its old in-memory guard.143 Python tests passed; probes on the real machine correctly detected its active Ollama connection. At inspection one real transcript was saved (304.469 s ASR), first-recording extraction was actively checkpointing and six recordings awaited transcription. Check the current private ledger/report for later progress; do not publish those results.

The activation proof fingerprint now also covers `resources.py` and `audio_prepare.py`. The previous private synthetic proof is historical for the earlier code; **future re-registration requires rerunning the existing synthetic unattended test when shared GPU/clinical processing is idle**. This does not disable the already registered timer or interrupt current processing. Do not replace the proof with fabricated success or run competing GPU tests mid-shift.

The owner connected the Yiko LU08 and explicitly requested registering that specific USB device and activating automatic local processing. Its filesystem UUID and USB serial are saved **only in the private owner configuration**. The production timer is now enabled; it imports only the registered device, not arbitrary flash drives. Seven WAVs were safely imported into the live private workspace. Both clinical cloud-storage permission gates remain false; no public publication is enabled. All audio/transcript retention locks remain on. Actual private audio has now been decoded locally; do not include any of it, transcripts, private paths/identifiers or extracted content in Git.

The first run failed at normalization: mono IMA ADPCM WAVs report an unreliable byte-rate duration and write **block count in the fact sample-count field**. `audio_prepare.py` now recognizes only that structurally verified pattern, checks RIFF/chunk sizes, complete blocks, samples-per-block and decoder agreement, and retains both the original header estimate and a timing warning in normalized manifests. Truncated blocks, invalid layout, corruption, ordinary PCM duration mismatches and duration limits still fail closed. All seven retained inputs normalized successfully without changing their source hashes. The samples use the declared sample rate; true recorder clock/physical timing and medical accuracy remain unverified. Do not use incorrect filenames as actual shift dates.

Only Fieldnotes was paused for the repair. The seven affected transcription retry counters were reset after verified conversion, without clearing any checkpoints. The timer was restarted. The shared-GPU gate may defer while another application keeps an Ollama model resident; **never unload it or stop MMM/FCC**. The CLI now distinguishes healthy queued/deferred work from actual failures; persistent recording errors and discovery/import errors still return failure. A deferred poll does not prove transcription or extraction succeeded. Check the live ledger and morning report for the latest stage before reporting progress.

Validation: **121 Python tests passed**, including new synthetic compressed-WAV compatibility/truncation/layout/limit/hash checks and deferred-versus-error exit-code tests. Source files, normalized working copies/manifests and any later transcripts remain under `~/.local/share/vet-fieldnotes-live/`; morning review is `review/index.html`. Never enable deletion, clinical uploads or public approval automatically. Independent backup remains optional/deferred. Next: allow shared GPU capacity to become available, verify the first actual Whisper transcript and subsequent extraction, then manually review real terminology/case associations and clarify recorder clock and actual coverage with the owner.

## Current outcome

Continue `/home/quinten/vet-knowledge-library`; session began at `1977f8e`. Use `git log` for the final implementation commit. Website design is unchanged and production content remains empty. The major next step is **connect/register the actual recorder**, then review a first authorized real recording. Do not rerun synthetic model searches or redesign the app.

The user now explicitly authorizes production USB service activation **after a passed synthetic test and safe device identification**. This supersedes prior blanket instructions against activation. No recorder is connected, so **production remains staged/disabled**. No real data was processed and no clinical cloud permission was enabled. Actual hardware/medical-quality integration is unverified.

Read `docs/USB_AUTOMATION.md`, `AGENTS.md`, and the current `docs/OPERATIONAL_READINESS.md`. The prior local-only 5–15 minute evaluation remains in `docs/FIRST_RECORDING.md`; it deliberately disables synchronization. Historical AI comparisons/errors remain in `docs/LOCAL_AI_BENCHMARKS.md`.

## Installed/staged owner setup

- Configuration: `~/.config/vet-fieldnotes/pipeline.toml`, mode600. Large V3 Vulkan + local `qwen3:30b` grounded-v2. Registered UUID/serial and local authorization reference are blank until owner registration. Private GitHub sync enabled, but **both clinical storage gates false**. Independent backup remote empty/optional.
- Live private workspace: `~/.local/share/vet-fieldnotes-live/`, mode700, currently empty of clinical data.
- Units: `~/.config/systemd/user/vet-fieldnotes.service` and `.timer`, installed but **timer disabled/service inactive**. Executes `vet-pipeline unattended` with the live workspace. Polls approximately 2 minutes, resumes after login/restart. No backup-key argument. No real-recorder service activation occurred.
- App-menu launchers: **Fieldnotes — Register Recorder**, **Fieldnotes — Morning Review**, under `~/.local/share/applications/`. No terminal needed for daily use after registration.
- User manager works (has unrelated pre-existing degraded status/spice unit warning); `Linger=no` unchanged. Stay signed in; screen lock is fine. Headless/logged-out mounting/operation is not claimed verified. No global power/udev/driver/ROCm/Ollama/MMM/FCC setting changed.
- Private activation proof: `~/.local/share/vet-fieldnotes-setup/synthetic-test.json`. Current passed test is bound to processing/storage core SHA; registration refuses absent/stale proof. Temporary synthetic test units have been removed; no test pipeline should be left running.

## Retention: absolute initial lock

```
[retention]
enabled = false
retain_source_audio = true
retain_transcripts = true
automatic_deletion = false
```

Unattended mode refuses weaker values. The cleanup function itself refuses deletion while these protection flags remain, even if the older `enabled` option is accidentally set. **Never delete originals on the recorder.** Preserve imported WAVs, normalized copies, full transcripts, Whisper JSON, extraction/chunk/quality reports and source links for reviewed initial shifts. This is not indefinite workplace retention permission; owner must manage a compliant policy. Do not activate deletion without a new explicit decision.

## What was integrated

- Exact configured filesystem UUID and optional inherited USB serial/label/roots matching; no generic every-drive import. If configured and the exact volume is unmounted, UDisks requests read-only mounting without interactive authentication. Mounted media is only read by this app. Actual hardware/UDisks behavior still needs a real device test.
- Automatic scan checks size/mtime unchanged across computer-observed polls, independent of the recorder clock. Future-dated synthetic WAV tested. Incomplete/changing/symlink/escaping files fail/defer individually; reliable byte SHA dedup survives reconnect/restart.
- Ingest keeps byte-identical originals, original names/relative source paths, size, exact filesystem modification ns, codec/duration, clock uncertainty and hashes. Copy file/directory fsync precedes durable job registration. Convenience `retained/SHIFT_ID/` links preserve names without duplicating large originals.
- Non-mono/non16k/nonPCM16 WAVs normalize a separate verified copy through local PyAV, with source hashes and preserved interrupted copies. No overwrite of originals. Successful full Whisper JSON now stays under `transcription-details/` alongside parsed full transcripts.
- Existing pipeline stages/source validation/case/topic consolidation/checkpoints remain. Optional per-stage GPU gate checks Ollama metadata/resident models, AMD busy/VRAM telemetry, and installed local GGUF status before inference. Busy/unavailable resources defer without consuming file retries. Never unload another model or stop MMM/FCC. Default limits 20% busy / 3,000 MiB used; conservative availability check, not an exclusive GPU scheduler.
- Temporary `systemd-inhibit idle:sleep` helper holds only during active work, then its owned process group is released, including interruption. No permanent sleep setting changes.
- Private offline morning report (`review/index.html`, per-recording and article pages) displays summary, last observed stage, measured times, failed/incomplete jobs, original/working audio, full transcripts, exact timestamp playback, extracted facts/accounts, source/article links, cases, questions, unclassified excerpts and unapproved publication candidates. CSP/escaping/no external assets; no server/listening port. Refresh browser to see generated updates.
- Import sessions are **uncertain import batches**, not guessed actual shift dates/times. Eight-hour configurable session window; unchanged reconnect/idle polls do not replace last meaningful batch. Wrong recorder clocks do not stall imports but can affect unverified sort order. Do not infer true chronology or sum voice-activated durations into shift clock time.
- `review/publication-candidates.json` is generated all-unapproved, separate from any owner approval file. Public review never blocks processing. No autonomous public publisher activated; approved publication helper pushes validated content and existing Cloudflare Git deployment rebuilds automatically.
- Qwen sometimes omitted questions in repeat runs. Deterministic fallback now adds at most one literal cloze/source-recall flashcard for a classified grounded discussion with a suitable exact fact quote and no model question. Labeled as **not model-authored or medically verified**; unknowns/context preserved; never applies to unclassified excerpts. Quality counts fallback cards separately. It does not improve/model-certify semantic medical understanding.

## Storage decision and private master preparation

Private GitHub primary remote + local secondary + Cloudflare approved public hosting. Independent cloud provider remains optional/deferred; do not ask for Drive credentials or require backup keys.

The master previously contained synthetic durability/AI-test records. Before real use, `scripts/prepare-live-master.py` verified synthetic-only data and preserved the entire archive/status under:

`synthetic-validation/pre-live-2026-11-03-014659-279497Z/archive`

Integrity/manifests/history remain intact, with verified private commit **4545eaea81b6fc8a1c00c2e2c9946776b0021881**. `production-storage.json` reserves the normal **archive/** path for authorized real knowledge; it is absent/empty until first authorized live save. This avoids the existing missing-record guard rejecting the first real library as an incomplete replacement of synthetic tests. Private sync now refuses synthetic data in that reserved namespace. Do not repopulate it with test data.

Both clinical gates remain false in live config. During actual registration the owner may separately opt into private GitHub storage only with appropriate authorization covering the material synchronized, and supply its reference; it is recorded owner-only in `~/.config/vet-fieldnotes/github-storage-authorization.json`. Local recording permission alone does not authorize GitHub. Choosing local-only keeps processing/review working and the clinical sync pending. Public publication approval remains distinct. No WAV, transcript file, SQLite database, review HTML or credentials are synced; extracted quotations/accounts can still be sensitive and require storage permission.

Existing durable GitHub outbox/backoff/remote commit verification remains; subsequent polls retry without new recordings or repeated inference. Local knowledge/commits survive network failures. No force push/reset. The actual master checkout is fast-forwarded through the production-preparation commit and clean. Prior cloud-verified synthetic commits include cf613392c875c6c313c4667bf901fc362b1ef03f,16856c26d9f14bc8ca62fa9088936aa6fe89287b,2d43acb6ec6184a3573f14a69f3fb8d5ba26db25.

## Real tests and artifacts

Private artifacts: `~/.local/share/vet-fieldnotes-validation/usb-automation-r1` through `r4`. Each simulated a removable recorder directory attachment through a real background systemd user timer. No direct pipeline invocation was needed after attachment.

- Runs r1/r2/r3 exercised actual Large V3 Vulkan → Qwen3 → canonical articles/cases/discussions/cards, SIGINT after saved transcript/completed work, automatic resume, unchanged checkpoint hashes, unplug/reconnect dedup, complete source retention, normalization and actual private GitHub push verification. r3 includes a future-year source mtime, imports4/4 files,79.156 s audio,134.871 s wall including deliberate interruption/timer/network waits,58.903 s worker time;8 existing article updates,2 new cases,8 discussions. Qwen authored no new cards that repeat; this led to the explicit source-recall fallback.
- Final r4 rechecked complete local pipeline after fallback, without cloud sync because production namespace is now reserved. **4 WAVs/79.268 s audio →5 articles,2 cases,7 discussions,6 cards**; **115.101 s elapsed including waits/interruption**,45.015 s worker time. Three fallback cards counted separately. Three saved transcript/extraction hashes unchanged across interruption; reconnection/no duplicate jobs; stereo32k normalized separately; future-dated source imported; all originals/transcripts retained. Four successful Whisper outputs explicitly confirm Vulkan acceleration.
- Offline desktop390/1440px checks validated audio, article→source discussion anchors, layout and zero HTTP requests. Clicking a4.66 s timestamp actually set media playback to4.66 s.
- **110 Python tests** pass; new tests cover retention lock, UUID/inherited serial/read-only mount calls, future-clock stability, queued GPU deferral/no retry consumption, private review/unclassified visibility, source conversion/retention, registration/activation/clinical consent, synthetic→live master preservation and literal-card provenance. Existing dedup/resume/clinical-public-privacy/backup/recovery tests remain.
- Public site/source design unchanged; finish/check production build and CI/live site at final commit. Only sanitized results belong in docs/validation/usb-automation.json. Private logs under `/tmp/fieldnotes-usb-*.log` and retained run roots.

## Installed AI paths (unchanged)

```
~/.local/share/vet-fieldnotes-ai/whisper.cpp-v1.9.5/build-vulkan/bin/whisper-cli
~/.local/share/vet-fieldnotes-ai/models/ggml-large-v3.bin
~/.local/share/vet-fieldnotes-ai/tokenizers/qwen3/tokenizer.json
Ollama 0.34: qwen3:30b; qwen3.5:9b-q4_K_M; gemma3:12b-it-q4_K_M
```

Ryzen 7 7800X3D / RX 7900 XTX (24 GiB) / 64 GiB RAM / Ubuntu 26.04.1. No new weight/driver/ROCm/system dependency installed. Local uv environment already supplies PyAV/tokenizers; Zenity/UDisks/systemd already installed. Other GPU jobs can defer processing indefinitely; no unsafe forced eviction. No paid API or real clinical data used. Keep existing offline model-comparison evaluation available for the first authorized sample; ASR drug/negation/case-label errors and extraction evidence-kind mistakes still need human review.

## Exact next actions

1. Connect the actual recorder and launch **Fieldnotes — Register Recorder** (application menu). Select its mounted UUID/serial, provide appropriate local recording/processing permission, optionally separate private GitHub storage permission. This safely activates only its matched timer after current synthetic proof. If no mounted UUID exists, inspect hardware rather than guessing an ID. No device-specific hardware verification has been claimed.
2. Leave Ubuntu signed in/locked and powered. Open **Fieldnotes — Morning Review**; initial stable-file import may take 2–4 minutes. Verify true device format, timestamps, grouping and no media modification. Start with an authorized5–15minute sample and manually compare audio/transcript/knowledge; retain everything for the first shifts. No unattended clinical accuracy claim.
3. If needed, run the separate FIRST_RECORDING evaluation against a retained source to compare Qwen3.5/reference/recollections. It intentionally remains local-only. Fix observed real errors before relying on unreviewed notes.
4. Public candidates need owner privacy/authorization/content-hash approval; existing publish helper+Cloudflare handles reviewed export. Never let that approval requirement block private processing.
5. For future synthetic reruns, omit `--sync-private`, or use a **separate synthetic private repository checkout** with that flag. The normal master is reserved for real data and scripts refuse using it as a synthetic target. Do not undo the separation or delete synthetic history.

Useful commands (desktop launchers are preferred for the owner):

```bash
cd /home/quinten/vet-knowledge-library
uv run --project pipeline --extra evaluation python scripts/register-recorder.py --stage
uv run --project pipeline --extra evaluation python scripts/register-recorder.py
systemctl --user status vet-fieldnotes.timer vet-fieldnotes.service
journalctl --user -u vet-fieldnotes.service --since today
# Local-only synthetic regression; choose a new empty output directory:
uv run --project pipeline --extra evaluation python scripts/test-unattended.py \
  --audio-directory ~/.local/share/vet-fieldnotes-validation/local-ai-r2/pipeline7-audio \
  --directory ~/.local/share/vet-fieldnotes-validation/NEW-UNUSED-DIRECTORY
# Only disable/stop Fieldnotes if necessary; preserve all source files:
systemctl --user disable --now vet-fieldnotes.timer
systemctl --user stop vet-fieldnotes.service
```


## Final verification addendum

Implementation commit **8f9ceb7** was pushed and passed [full CI](https://github.com/JoMoma2/veterinary-fieldnotes/actions/runs/41579561954). The actual Qwen-generated synthetic dataset (including literal fallback cards) was separately approved for the ignored local pipeline-demo projection: 5 articles, 2 cases, 7 discussions and 6 cards built and passed four desktop/mobile source-link/search/study browser tests. The final local build was restored to empty production; type/content checks,16 TypeScript tests and four desktop/mobile production/privacy/search browser tests passed.

A final publisher fix uses the existing user-local supported Node wrapper (system Node remains22.22.1) and explicitly forces the production dataset regardless of caller environment. Two tests verify production build selection and rejection of a private publication destination before content export. Total110 Python tests pass. This does not activate a publisher or change approval gates. The final follow-up commit/CI can be found from git log/Actions. No new inference run is needed: processing/storage core hash still matches the private passed activation proof.
