# Architecture and decisions

## Boundaries

1. **Application repository (public):** website, pipeline code, schemas, synthetic test fixtures, and explicitly reviewed production exports. No actual recordings or private processing data.
2. **Local private workspace:** job ledger, copied audio, transcripts, model outputs, quarantined questions, canonical record transactions, and two regenerable local Markdown/JSON projections. Default `~/.local/share/vet-fieldnotes`, created owner-only.
3. **Private master repository:** a separate initially empty scaffold. Later, authorized permanent records and sanitized processing status may be synchronized. A private GitHub repository is still third-party storage and is not automatically authorized for clinical content.
4. **Independent encrypted backups:** historical immutable `.vkb` files, optional rclone remote, and a separately retained secret key. No audio or temporary transcripts in backups.
5. **Public website:** only the dedicated reviewed export root. Builds reject synthetic production records, omit non-public records and inaccessible references, and disable source maps. Review identities/authorization details stay private.

## Technology

- Astro 7.4.4 / TypeScript / scoped shared CSS / browser JavaScript. No runtime server, frontend framework, or database is needed for visitors. CSS design tokens keep the notebook-style interface easy to change. Native vector illustration avoids external assets.
- Pagefind 1.6.0 runs after static generation; development fallback is separate. Search indexes complete article/case/discussion content, not duplicate archives.
- Versioned Zod 4 contracts generate JSON Schema consumed by Python. JSON Schema cannot encode all custom refinements, so Python additionally validates cross-references and answer relationships. Website validation remains a final gate.
- Python 3.12 recommended; stdlib SQLite, file locks, atomic filesystem replacement, jsonschema, httpx, cryptography. uv.lock pins dependencies. Faster-Whisper is optional. PyAV is pinned below 17 after a genuine smoke test exposed an API incompatibility with PyAV 19.

## Job and data durability

SHA256 content hashes identify independent import units. Names and recorder paths do not determine uniqueness. IDs use the first 24 hash characters; the full hash remains unique in SQLite and travels with recording metadata. Reconnecting a device deduplicates files. Changing metadata or file bytes creates a new recording, by design.

Stages: `transcribe → extract → commit → done`. Each successful stage checkpoints before the next. Chunk extraction has its own saved outputs. Failed files increment bounded attempts with exponential retry delays; they do not discard successful files. The workspace lock prevents concurrent writers; SQLite WAL and FULL synchronization protect committed records. A crash after a library commit but before the job's `done` checkpoint is detected through `applied_recordings` and does not duplicate additions.

Canonical records and applied-recording IDs commit in one SQLite transaction per file. Portable Markdown/JSON is materialized once per run using atomic pointer replacement. Only the current and preceding local projections remain. They are regenerable views, not the backup history. This avoids one complete filesystem snapshot for every recording. Independent encrypted backups and authorized Git history preserve older versions.

A failed file projection is reported independently; `run` regenerates it without repeating inference. A failed remote backup upload only retries the encrypted artifact, never extraction. The schema and important application invariants are validated before permanent commits and before backup/export.

## Evidence and reconciliation

Every extracted discussion has grounded quotes with source offsets. Validation checks exact quotation text and original segment offsets. This catches fabricated citations, **not all fabricated interpretations**; real-model quality still requires benchmarking and human publication review.

Evidence types distinguish direct observations, owner reports, suspicions, confirmed diagnoses, actual/proposed treatment, outcomes, AI explanations, externally verified statements, and unknowns. Extraction cannot label its own statements externally verified. Actual measurements, treatment, and outcomes must never be completed from typical textbook expectations.

Article IDs come from canonical `topicKey` values. Retrieval uses a local SQLite FTS index, eight matches maximum and a configured character budget. It is rebuilt from current records; only targeted matches enter the model request. Knowledge additions append with date and source links. Earlier useful content remains. Synonyms can still create duplicates if the model ignores retrieved canonical keys; review and owner edits are the correction path. Semantic merging of an established library is deliberately not automatic.

Case keys must occur verbatim in a grounded transcript quote. Automatic continuation is scoped to a shift and additionally requires explicit continuation wording in the cited evidence. A reused label without that evidence becomes a separate candidate case. Generic topic recurrence does not merge patients. Conflicting diagnosis/outcome accounts are retained in uncertainties and the canonical value becomes unknown. This is intentionally conservative; natural, vague cross-shift references await evaluation on real data. No fuzzy patient matching is claimed.

## Publication

Suggested category names and descriptions require their own approval, so private topic suggestions cannot leak through a public category registry. Approvals bind a reviewer, timestamp, authorization reference, privacy review, record ID, and SHA256 of the exact record. A subsequent change makes that approval stale. The synthetic-only approval command refuses real records. Actual publication requires a manually completed approval file and explicit `--allow-clinical`.

The exporter copies only approved records, prunes unavailable references, excludes cases/questions with no approved discussion, and removes recording metadata that has no public discussion. The site repeats filtering and generates backlinks. Arbitrary free text is not automatically de-identified: review must include titles, accounts, facts, Markdown, timestamps, and identifying combinations. Removing names alone is insufficient. A hidden source link in approved Markdown fails internal-link verification if it points to an unavailable route.

Approval of source discussions is distinct from approval of the article derived from them. An approved article can stand alone with no public source list. Review does not stop nightly private processing. Publication runs explicitly against approved material; it is not part of the recorder watcher.

## Backups and retention

Backups contain Markdown/JSON permanent records and a manifest, authenticated encryption using Fernet, unique versioned filenames, SHA256 for every archive member, and a validation pass. Corrupt or unsafe archives never replace a working destination. Restores require a new path. `recover-library` rebuilds a fresh ledger and canonical records from a restored permanent library, preserving completed hashes and case-key mappings. In-flight audio/transcripts are excluded from cloud backup: re-import incomplete work from originals when required.

Optional rclone copy uses immutable object naming and verifies downloaded encrypted bytes. No remote deletion/sync is implemented. A failed upload stays pending; it has a separate retry budget. Default retention is disabled. An explicitly enabled cleanup only removes workspace copies after commit, retention age, required backup checks, and absence of unresolved quarantine holds. It never deletes recorder media. Local backup corruption blocks cleanup. Keep the backup key outside every repository and retain an independent secure key copy.

## Limits to address before long unattended use

No paid API/model is selected. No exact recorder, GPU, clock reliability, or 12-hour processing speed is assumed. The architecture is tested with 105 independently queued recordings, not two years of accumulated medical material. Retrieval-index rebuilding, full-library validation, and append-only note growth should be measured against a larger realistic library before deployment at scale. No medical fact-check agent or elaborate multi-agent process is required.
