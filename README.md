# Fieldnotes — Veterinary Knowledge Library

Study questions require [independent medical reference verification](docs/MEDICAL_FACT_CHECKING.md) before real publication; transcript grounding alone is insufficient.

For the organized owner-local installation, open `~/FieldNotes/Start.html`. See [Local folder layout](docs/LOCAL_LAYOUT.md) for source, reports, retained recordings and configuration.

A local-first veterinary learning system: authorized recordings become source-linked discussions, case records, additive knowledge notes, and pre-generated study questions. Private processing and public publication are separate.

**Current state:** a working static website, resumable Python pipeline, synthetic end-to-end workflow, tested encrypted backup/restore, and configurable USB/systemd, GitHub, and Cloudflare integrations. Production starts with **zero** articles, cases, shifts, discussions, or questions. No cloud clinical upload, recorder deletion, or background service is enabled. The empty production website is live at https://veterinary-fieldnotes.pages.dev; the private GitHub archive contains synthetic durability-test records only.

## Open the website

Use Node **24 LTS** (or Node ≥22.23.4) and npm ≥9.6.5. Older Node releases will not run the pinned Astro version. This host initially had Node 22.22.1. `./scripts/local-node.sh` supplies a user-local Node 24 toolchain when needed, without replacing system Node or changing shell setup. For example: `./scripts/local-node.sh ci` and `./scripts/local-node.sh run dev`.

```bash
cd /home/quinten/FieldNotes/app
npm ci
npm run dev
```

Open **http://localhost:4321**. The default production library has useful empty states.

To explore the separate, entirely fictional demonstration library:

```bash
npm run demo
```

Stop an existing development server before switching datasets. In an agent environment, Astro may start it in the background: `npx astro dev stop`. For a foreground process use `npm run dev -- --ignore-lock`. On this host, use `./scripts/local-node.sh run dev` (or `run demo`) if system Node is still too old.

Build and view full Pagefind search:

```bash
npm run build
npm run preview
# Demonstration build instead:
LIBRARY_DATASET=demo npm run build
npm run preview
```

Development mode has a local text-search fallback; production preview uses the generated Pagefind index. The public site is static, registration-free, and has no database, telemetry, external fonts, accounts, or visitor progress storage. Study state lives only in page memory.

## A complete synthetic pipeline demonstration

Install [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv can manage Python). No API account or model download is needed for the default workflow:

```bash
uv sync --project pipeline --python 3.12 --extra dev
npm run demo:pipeline
LIBRARY_DATASET=pipeline-demo npm run build
npm run preview
```

This imports three synthetic timestamped transcripts, extracts six discussions, links one case across recordings, creates four articles, adds follow-up information without losing the first note, preserves contradictory owner reports, quarantines an invalid question, creates three valid questions, applies synthetic-only review, and exports to `fixtures/generated/public`. It also encrypts, restores, and compares a backup. Temporary private data and test keys are removed after the demonstration. The generated public dataset is ignored by Git. **Production content is untouched.**

Mock extraction responses are deliberately authored fixtures. Their success verifies software behavior, not the reasoning quality of a real AI model.

## Content layout

```text
content/public/              # Approved production export ONLY; initially empty except category registry
  topics.json                # Stable topic IDs, editable display names; categories are extensible
  articles/*.md              # JSON-compatible YAML frontmatter + Markdown
  cases/*.json               # Evidence labels, source discussions, explicit null unknowns
  shifts/*.json              # Recording metadata, processing status, timezone
  discussions/*.json         # Detailed accounts and recording-relative segments
  questions/*.json           # Pre-generated question data; no inference in the browser
fixtures/demo/public/        # Polished fictional browsing examples
fixtures/pipeline/           # Synthetic transcripts, expected markers, deterministic mock outputs
fixtures/generated/public/   # Ignored, generated end-to-end demonstration export
src/lib/schemas.ts           # Versioned Zod data contracts, shared by website and tests
schemas/*.schema.json        # Generated portable JSON Schema for Python and other tools
pipeline/vet_pipeline/       # Local processing application
config/                     # Non-secret configuration examples
automation/                 # Uninstalled Ubuntu user systemd units
docs/                       # Decisions, operation/recovery guide, tests and status
```

The website selects a dataset with `LIBRARY_DATASET=production|demo|pipeline-demo`. It never accepts an arbitrary private content path. Synthetic records in the production root cause a build failure. No private workspace is included in builds, assets, source maps, search data, or preview content.

### Add or update a knowledge article

For curated public-only education, add a Markdown file to `content/public/articles/` with frontmatter matching `schemas/article.schema.json`. Use a permanent ID such as `a-urinary-observations`; titles may change, IDs must not. Set real educational content to `origin: authorized-record`, and attach required public review metadata only after the necessary authorization/privacy review. Empty `sourceDiscussionIds` is allowed for independently authored notes; do not invent discussions to fill it. Use accurate references for external medical explanations.

For pipeline-managed content, edit a **copy** of the local Markdown/JSON projection and use `apply-edits`; do not edit the generated `library/current` directory in place. Changes require a fresh review and export. See [operations](docs/OPERATIONS.md). `npm run check` validates every record and cross-reference before building. `npm run schemas` refreshes portable schemas after changes to the TypeScript contracts.

### Source linking

A discussion's permanent route is `/discussions/<id>/`. It also appears at `/shifts/<shift-id>/#<discussion-id>`. Articles list `sourceDiscussionIds`; discussions list `articleIds` and `caseIds`. Public projection derives backlinks from either end and removes references to non-public records. Only approved discussions and their recording metadata are exported. Reorganizing article prose or changing its title does not change source addresses.

Timestamps retain recording IDs, file metadata/hash, and offsets separately. Filesystem modification times are unverified. Voice-activation gaps are never reconstructed by summing audio durations. Explicit reliable clock metadata can be preserved; missing time remains unknown.

### Study question storage

Questions are individual JSON records, using `multiple-choice`, `multiple-select`, `flashcard`, `open-ended`, or `scenario`. Store an explanation and approved source references. Multiple choice uses one correct answer plus 3–9 reviewed distractors; each session samples three and shuffles all four. Multiple select checks an exact answer set. Written answers and scenarios reveal a stored model answer for self-assessment. Topics support Select All / Deselect All, with separate format filters. Nothing is saved across visits.

## Intended AI pipeline

```text
Configured recorder / transcript import
 → copied, hashed independent recording jobs
 → local Faster-Whisper timestamps (or direct transcript ingestion)
 → one configured extraction model + targeted local retrieval
 → structured, quote-grounded validation
 → transactional private library commit + portable Markdown/JSON projection
 → private GitHub commit/push with durable retry state (when configured)
 → optional encrypted versioned backup
 → explicit content-bound authorization and privacy review
 → filtered public export → website rebuild/deployment
```

The private workspace uses SQLite for durable local job and record transactions, not a hosted database. Portable content files are regenerated once per run. Completed stages are not repeated after a later failure. Successful files survive other failures; retries are bounded and logs omit provider response bodies. Models append sourced additions to existing canonical article IDs; they cannot overwrite earlier prose. This conservative additive approach may accumulate repetitive sections; semantic cleanup and alias curation need review.

Configurable providers: deterministic synthetic mock, Ollama, and OpenAI-compatible `/chat/completions` APIs. API credentials come from environment variables. External API use is disabled unless explicitly configured, and clinical third-party processing/storage requires separate authorization. An FCC service can use the compatible adapter only if its actual endpoint supports that protocol; no unsupported FCC API is assumed.

See [OPERATIONS.md](docs/OPERATIONS.md) for command examples, model configuration, benchmarking, backups, GitHub, publication, and systemd setup.

## Verification

```bash
npm run check
npm test
uv run --project pipeline pytest pipeline/tests
LIBRARY_DATASET=demo npm run build
npx playwright install chromium      # once, if a browser is not already installed
npm run test:e2e
npm run build
E2E_EMPTY=1 npm run test:e2e
```

The initial empty-production assertion is intentional; adapt it when genuinely approved production material is introduced. Browser tests run against the built output. Do not rebuild `dist` during a browser test. [TESTING.md](docs/TESTING.md) records tested behavior and limits.

## Continue development

Read [AGENTS.md](AGENTS.md), [architecture decisions](docs/ARCHITECTURE.md), and [current status](docs/STATUS.md). Next: inspect the [operational readiness report](docs/OPERATIONAL_READINESS.md), benchmark candidate local extraction/transcription models on authorized material, configure recorder matching when the hardware arrives, and dry-run USB import and service operation. Real-model factual accuracy, 12-hour throughput, recorder clock behavior, and long-term unattended reliability remain to be measured. No 90% capture guarantee is made.

Local GPU transcription setup, measured Qwen3 limitations and authorized real-audio benchmark instructions are in [docs/LOCAL_AI_BENCHMARKS.md](docs/LOCAL_AI_BENCHMARKS.md). Continue from [docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md). Large V3 and the complete local synthetic WAV pipeline now work. Grounded source accounts, case/article updates and recall cards are implemented; clinical-quality validation on real authorized audio remains unfinished.

For the first **private, authorized 5–15 minute recording**, follow [FIRST_RECORDING.md](docs/FIRST_RECORDING.md). It provides copy/format inspection, local conversion, Large V3 transcription, identical-input Qwen3/Qwen3.5 comparison, corrected-reference evaluation and an offline audio-linked review page. These tools reject Git-contained workspaces and external/cloud-backed inference. Current storage is **private GitHub primary remote + local secondary copy + Cloudflare approved public hosting**. Independent-provider backups are deferred and do not block processing. Optional encrypted backup/restoration tools remain documented in [INDEPENDENT_BACKUP.md](docs/INDEPENDENT_BACKUP.md).


Private GitHub synchronization is configured in `[github]` of the private pipeline TOML; see [OPERATIONS.md](docs/OPERATIONS.md#private-master-synchronization). When enabled, `run` and `nightly` commit/push completed knowledge, verify the remote commit, and persist pending failures with capped retry delays. A failed push never resets completed transcription/extraction or removes local results. Clinical storage still needs both explicit authorization gates. The private real-recording evaluation tool deliberately keeps all synchronization disabled.


For plug-in operation, see [USB_AUTOMATION.md](docs/USB_AUTOMATION.md). Disabled production units, Large V3/Qwen3 configuration and the **Fieldnotes — Register Recorder / Morning Review** launchers are staged locally. Register the actual recorder once by UUID/serial and supply local-processing authorization; a separate explicit choice controls clinical GitHub storage. The recorder is currently absent, so production activation remains pending. All imported originals, normalized copies, complete transcripts and extraction checkpoints are retained, with cleanup locked off. The background synthetic timer/recovery tests passed using real models; physical USB behavior and clinical accuracy still need real validation.
