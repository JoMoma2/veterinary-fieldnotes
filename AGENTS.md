# Veterinary Fieldnotes: continuing agent instructions

## Objective

Build and maintain a low-intervention veterinary knowledge acquisition system that can run after authorized ER shifts for years. It is a processing/archive/study system, not only an encyclopedia. The user explicitly expanded the original Phase 1 request to implement the full system as far as hardware, credentials, permissions, and testing allow. Favor simplicity, reliable checkpoints, and portable data.

## Non-negotiable constraints

- Never invent clinical facts, diagnosis, treatment, results, outcomes, or uncertain patient connections. Null unknowns must stay visible. Preserve practical/unconventional details with circumstances and limitations; do not imply safety.
- Capture/process real information only when authorized. Recording permission is distinct from inference, third-party storage, and publication permission. Removing names alone is insufficient privacy review.
- Production is initially empty. Synthetic examples live only in separate `fixtures/demo` and `fixtures/pipeline` datasets; generated demo output is ignored. Do not fill production with invented content.
- No raw audio, temporary transcripts, secrets, backup keys, actual private ledgers, or confidential records in the application repository or website build. Do not erase recorder originals. Retention is disabled initially and can delete only checked workspace copies after explicit configuration.
- No visitor accounts, tracking, progress persistence, paid resource creation, or unapproved API charges. No inference from the visitor browser.
- Do not create elaborate multi-agent review orchestration. One extraction provider is sufficient. No paid subscriptions imply API rights.
- Do not deploy a demonstration build. The deployment helper checks both current dataset and recorded build metadata.

## Checkout and architecture

Application: `/home/quinten/vet-knowledge-library`; separate private scaffold: `/home/quinten/vet-knowledge-master`.

Public app uses Astro 7.4.4 + strict TypeScript + shared CSS + small vanilla browser scripts. Full-text Pagefind indexes the built HTML. The notebook visual style is in `src/styles/global.css`, not scattered styling abstractions. `src/lib/schemas.ts` defines version-1 Zod contracts; `npm run schemas` exports JSON Schema to `schemas/` for Python.

`LIBRARY_DATASET=production|demo|pipeline-demo` picks only known public roots. `readLibrary` validates records and references; `publicProjection` filters records/links/recording metadata and strips approval identities. It never reads arbitrary private paths. `content/public` rejects synthetic records.

The Python application under `pipeline/vet_pipeline` uses a local private SQLite ledger (WAL/FULL), transactional canonical records, SHA256 import deduplication, file locks, per-stage/per-chunk checkpoints, and portable Markdown/JSON projection once per run. Local projections are bounded to two; encrypted backup versions provide history. Default workspace is outside Git at `~/.local/share/vet-fieldnotes`. Public site needs no runtime DB.

Pipeline stages are transcribe → extract → commit → done. Recording/library commit is idempotent via applied IDs. Successful work survives other failures. Extraction uses configurable mock/Ollama/compatible providers, exact source-quote validation, targeted local FTS retrieval, append-only article updates, and conservative evidence-bound case linking. Unsupported/uncertain links stay separate. Invalid study questions are quarantined independently.

Publication approvals bind exact record hashes, reviewer/time/authorization/privacy review. Actual clinical export requires a separate explicit flag. Nightly processing never auto-approves real records. Owner edits through `apply-edits` preserve permanent IDs and invalidate review on changed records. Public source routes use immutable IDs: `/discussions/<id>/` and `/shifts/<id>/#<discussion-id>`.

Backups are immutable named encrypted archives, verified at creation, safe restore to new directories, optional rclone upload with remote byte verification. Recovery rebuilds deduplication and case continuity in a fresh workspace. Remote storage needs explicit clinical authorization. See `docs/OPERATIONS.md` for setup/recovery, and `docs/ARCHITECTURE.md` for decisions/limits.

## Development commands

Node ≥22.23.4, preferably 24. The original system Node was 22.22.1; `./scripts/local-node.sh` bootstraps/uses a user-local toolchain without altering shell/global configuration. Use it as an npm wrapper if needed.

- `npm ci`, `npm run dev`: empty production library, localhost:4321.
- `npm run demo`: fictional browsing dataset. Stop an existing dev server before changing dataset (`npx astro dev stop` in agent background mode).
- `npm run check`, `npm test`, `uv run --project pipeline pytest pipeline/tests`.
- `npm run demo:pipeline`: synthetic full import/consolidation/export/backup/restore.
- `LIBRARY_DATASET=pipeline-demo npm run build`: validates generated output against website contracts.
- `LIBRARY_DATASET=demo npm run build && npm run test:e2e`: all UI formats and source links.
- `npm run build && E2E_EMPTY=1 npm run test:e2e`: empty production UI and no demo leakage.
- `uv sync --project pipeline --python 3.12 --extra audio --extra dev`: optional Faster-Whisper.
- `uv run --project pipeline --extra audio python scripts/audio-smoke.py`: generated speech smoke (initial download flag only when authorized).

Astro auto-backgrounds in detected agent contexts. Playwright's server uses `--ignore-lock` for foreground execution. Do not rebuild `dist` while browser tests/QA serve it. Stop owned preview sessions at handoff. Pagefind works after `build`; dev search uses a non-private fallback.

## Current development status

The website, synthetic processing/consolidation workflow, quote/reference validation, encrypted backup/recovery, and independent failure handling are implemented and tested. Production has no articles/cases/shifts/discussions/questions. GitHub repositories were created under JoMoma2; consult `docs/STATUS.md` for publication/CI status. Cloudflare credentials, rclone authorization, actual recorder configuration, and final model selection remain absent. No systemd service is installed or enabled, no real clinical data was processed, and no paid API was called.

Latest local verification: 16 TypeScript unit tests, 32 Python tests including a 105-file batch, 12 populated-demo browser tests, 1 empty-production browser test, type checking, all three dataset builds, internal links/anchors, safe encrypted restoration, and genuine local Faster-Whisper inference on generated speech. See `docs/TESTING.md`. Update counts if adding tests.

## Next priorities / limitations

1. Connect free Cloudflare Pages to the public repository with production-only dataset settings; no credentials are currently configured.
2. Benchmark actual candidate extraction/transcription models locally and on authorized representative transcripts. Mock output does not establish AI accuracy. Tiny speech-smoke model made wording errors and is not a clinical recommendation.
3. Test recorder mounts, timestamps, PCM/WAV behavior, voice-activation gaps, and correct shift assignment when hardware arrives. The current watcher groups by import date unless overridden; automatic overnight/multi-shift classification is unverified.
4. Dry-run the user systemd service and test a complete real authorized shift before enabling timers or retention. Confirm user-manager availability after logout.
5. Measure full-library validation, retrieval rebuilding, append-only note growth, memory, and 12-hour workload throughput at realistic scale before claiming years of unattended readiness.
6. Preserve ID stability and backward data compatibility. Introduce explicit migrations for future schema/ledger changes. Initial tests assert production is empty; replace that initial-state assertion deliberately when approved production records are added.

Do not claim cloud integration is live or real-model medical accuracy is established just because adapter tests pass. Do not rerun successful model stages after an upload failure. Keep documentation and these handoff instructions current.
