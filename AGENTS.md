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

Application: `/home/quinten/vet-knowledge-library`; separate private master checkout: `/home/quinten/vet-knowledge-master`.

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

The website, synthetic processing/consolidation workflow, quote/reference validation, encrypted backup/recovery, and independent failure handling are implemented and tested. Production has no articles/cases/shifts/discussions/questions. GitHub repositories were created under JoMoma2; consult `docs/STATUS.md` for publication/CI status. Cloudflare Pages is deployed at https://veterinary-fieldnotes.pages.dev with native public GitHub integration, production dataset, and branch previews disabled. Wrangler OAuth and Codex Cloudflare MCP are authenticated; 19 Cloudflare skills are installed in ~/.agents/skills. The private master now contains only synthetic remote-durability test records and recovery manifests. rclone authorization, recorder configuration, and final model selection remain absent. No systemd service is installed or enabled, no real clinical data was processed, and no paid API was called.

Latest local verification: 16 TypeScript unit tests, 92 Python tests including a 105-file batch, 12 populated-demo browser tests, 1 empty-production browser test, 4 desktop/mobile production-audit tests, type checking, all three dataset builds, internal links/anchors, safe encrypted restoration, and genuine local Faster-Whisper inference on generated speech. See `docs/TESTING.md`. Update counts if adding tests.

## Next priorities / limitations

1. Keep the native Cloudflare Pages deployment on the production dataset; confirm automatic pushes and use the production browser audit after deployment. See docs/OPERATIONAL_READINESS.md for current evidence.
2. Read docs/AI_ENVIRONMENT.md before any local AI changes. CPU is Ryzen 7 7800X3D; GPU is RX 7900 XTX 24 GiB; Ollama bundled ROCm 7.2 acceleration works. MMM explicitly depends on qwen3:30b; FCC is active. No driver/SDK/service/model/config changes without authorization. Benchmark actual candidate extraction/transcription models locally and on authorized representative transcripts. Mock output does not establish AI accuracy. Tiny speech-smoke model made wording errors and is not a clinical recommendation.
3. Test recorder mounts, timestamps, PCM/WAV behavior, voice-activation gaps, and correct shift assignment when hardware arrives. The current watcher groups by import date unless overridden; automatic overnight/multi-shift classification is unverified.
4. Dry-run the user systemd service and test a complete real authorized shift before enabling timers or retention. Confirm user-manager availability after logout.
5. Measure full-library validation, retrieval rebuilding, append-only note growth, memory, and 12-hour workload throughput at realistic scale before claiming years of unattended readiness.
6. Preserve ID stability and backward data compatibility. Introduce explicit migrations for future schema/ledger changes. Initial tests assert production is empty; replace that initial-state assertion deliberately when approved production records are added.

Do not claim cloud integration is live or real-model medical accuracy is established just because adapter tests pass. Do not rerun successful model stages after an upload failure. Keep documentation and these handoff instructions current.

## Current local AI state — resumed 2026-11-02

Read `docs/SESSION_HANDOFF.md` and `docs/LOCAL_AI_BENCHMARKS.md` before further AI changes. Code milestone caed084 adds grounded-v2; the old 799f344 handoff's download authorization blocker is resolved. Large V3 f16 and Qwen3.5 9B/Gemma3 12B Q4 models are installed. The user authorized these free local downloads. No driver/ROCm/service/global model configuration changes, paid calls, real data, USB activation or deletion occurred. MMM/FCC are preserved.

`provider.extraction_protocol="grounded-v2"` is the default real-provider wire adapter; mock fixtures and optional legacy mode retain the canonical extraction format. Programmatic evidence IDs/offsets/references, exact or uniquely case/whitespace-mapped fact quotes, conservative case links and source-derived accounts prevent observed invented references/paraphrases. Canonical content schemas are still version 1. Source-recall flashcards use facts as answers. Topic retrieval supplies only a bounded naming index, not old clinical prose. Existing source/case IDs remain stable; do not weaken source validation.

Output-token exhaustion now creates persisted two-child splits (max depth 2) and independent child checkpoints. Context/output budgets constrain source chunks. Completed children are reused after interruption; no source material is deleted. Unclassified excerpts are retained without invented clinical interpretation, and run results expose review-required quality counts. Stage and provider timing live in private workspace quality/events logs. New discussions sort by source offset; old artifacts are not silently rewritten.

Large V3 Vulkan: 166.6 s synthetic audio in 12.77 s, 0.71% normalized WER vs tiny 16.90%; drug/case-name errors still occurred. Qwen3 baseline with compact contract is provisionally preferred for a reviewed pilot (~140 tokens/s, useful cards), not clinically certified. Qwen3.5 had better strict typed-clause matching/memory headroom but no cards. All three retained source accounts; this is not a semantic-accuracy percentage.

Actual seven-WAV workflow completed in 73.7 s for 180 s audio. A 374 s workload completed in 229 s including bounded splits, retaining 14/172 sources unclassified for review. Actual SIGINT recovery preserved three checkpoint hashes, transcript and good child inference. Independent provider backup and real recorder/ER validation remain prerequisites. Do not claim unattended clinical readiness.

Full private artifacts are under ~/.local/share/vet-fieldnotes-validation/local-ai-r2; historical earlier artifacts under local-ai-20261102. Only sanitized synthetic metrics are in docs/validation/local-ai-r2.json. Source/model/audio data stays outside Git. `scripts/benchmark-local-pipeline.py` is synthetic/local-only and can export only to ignored fixtures/generated/public. Model/corpus/config comparisons require fresh workspaces; retain historical checkpoints/configs.

Latest new checks: 75 Python, 16 TS, type/content validation, real-model test builds and four desktop/mobile generated-data audits. CI also verifies mock pipeline export navigation, existing demo and production suites. Finish local dist as production; never deploy pipeline-demo. Recommended pilot config is config/benchmarks/local-vulkan.example.toml copied outside Git, with verified local paths. See handoff for exact commands, remaining quality issues and prioritized real-audio evaluation.


## First-recording readiness — r3

The next major task is an **authorized real 5–15 minute WAV**, not further synthetic model searches. Read docs/FIRST_RECORDING.md and the current SESSION_HANDOFF.md. No real recording was processed this session. No USB service, retention, clinical upload, driver/runtime/global Ollama/MMM/FCC changes occurred.

New `scripts/evaluate-recording.py` creates private roots outside **every actual Git checkout**, including master. It copies/inspects WAV timestamps/hashes, normalizes a separate mono16k PCM16 copy with optional PyAV (`--extra evaluation`), preserves immutable ASR, keeps manual reference/recollections separate, versions model/input/settings/digest results, and produces offline audio-linked escaped review.html/review.csv. Loopback Ollama:11434 plus installed local GGUF metadata is required; cloud-backed models and remote inference are refused. It does not publish/upload. Corrected references need explicit manually-corrected status. Owner organization uses editable-library + existing apply-edits; IDs/source links stay stable.

New grounded jobs persist `chunk-plan.json` with transcript hash and complete serialized-message budget. Existing checkpoint ranges are preserved. Offline Qwen tokenizers are pinned in config/benchmarks profiles; `scripts/install-tokenizers.py` provisions only ~24 MB metadata, never weights. If absent, a configured tokenizer fails; with no configured tokenizer a conservative byte bound is used. Preflight context growth splits before HTTP. Canonical schemas remain v1. Do not re-plan existing jobs or erase checkpoints just to change scores.

Same saved long synthetic transcript: extraction199.387→125.581 s, six successful planned calls, no oversize attempts, classified158→161/172, unclassified14→11. Context/source retention does not imply semantic correctness: evidence labels remain unreliable, blood-sample topics duplicate, cards39→3. Inspect the actual pilot outputs. All unclassified excerpts remain visible/private; deterministic literal-unknown tagging never infers cases/topics.

User-local rclone1.75.2: ~/.local/share/vet-fieldnotes-tools/rclone. User confirmed no Drive credentials; authenticate via scripts/configure-backup.sh in their terminal using own desktop OAuth client/drive.file scope and private config. docs/INDEPENDENT_BACKUP.md covers refresh-token limitations, immutable synthetic remote restore drill and off-machine key/OAuth/account recovery. Local adapter two-version restore passed; independent cloud and off-machine key custody remain **unverified**. No clinical third-party storage is authorized.

Latest checks: 92 Python tests (`--extra evaluation`),16 TS, type/content checks, empty production build8 pages/87links,1 empty-state and4 desktop/mobile public tests. Actual private synthetic pilot LargeV3 + bothQwens and offline desktop/mobile/audio/no-network checks pass. Full artifacts: ~/.local/share/vet-fieldnotes-validation/readiness-r3; sanitized metrics: docs/validation/readiness-r3.json. Keep final dist production. CI/live verification is recorded in the current handoff/final report.
