# Current status — 2026-11-02

## Operational locally

- Responsive Astro website with knowledge articles, clinical cases, detailed shift discussions, source pages/anchors, categories, Pagefind search, and five study formats. No accounts, tracking, or persisted performance.
- Empty production content and separate fictional browsing/pipeline datasets, selected by environment without application edits.
- Schema-validated transcript/WAV ingestion, hash-based duplicate prevention, local Faster-Whisper adapter, configurable mock/Ollama/compatible extraction, per-file/per-chunk checkpoints, bounded retries, detailed archives, conservative case linking, additive canonical-topic updates, and isolated study-question quarantine.
- Transactional local canonical records, regenerable portable Markdown/JSON, owner-edit import with stable IDs, and publication approvals bound to exact content.
- Encrypted versioned local backups, safe restore, workspace recovery, independent upload retry queue, remote-byte verification adapter, and configurable guarded retention disabled by default.
- Configurable USB discovery/scan, Ubuntu user timer/service templates, GitHub setup/master synchronization/reviewed-publication helpers, and free Cloudflare Pages configuration/deployment guard.

## Remote repositories

- Public application: https://github.com/JoMoma2/veterinary-fieldnotes
- Private master scaffold: https://github.com/JoMoma2/veterinary-fieldnotes-master

Both are pushed on `main`. The initial GitHub Actions verification passed, including all three website datasets and both browser suites. The public repository contains application code, synthetic fixtures, and an empty production library. The private repository contains only the README/ignore scaffold. No actual records, credentials, keys, temporary transcripts, or audio were uploaded.

## Awaiting configuration or external dependencies

- Cloudflare Pages account connection. Neither API credentials nor local Wrangler OAuth is configured; no live site deployment occurred.
- Independent remote backup provider/rclone OAuth. No real or synthetic library backup has been uploaded to a cloud provider by this session.
- Final extraction and transcription model choice; representative authorized benchmarking. No paid API was called. The tiny audio-smoke model is not a clinical recommendation.
- Actual recorder in approximately three days: mount matching, authorization reference, file structure, WAV format, reliable timestamps/shift assignment, and throughput tests.
- Review of actual capture, processing, cloud storage, and public publication permissions before handling real material.
- Installation/enabling of the user systemd service and deliberate retention configuration after end-to-end restore and hardware trials. Neither is active.

## Next recommended work

Connect the empty production site to free Cloudflare Pages, then benchmark candidates and test the real recorder in a separate authorized local workspace. Measure an entire shift before enabling unattended operation. Use this foundation to evaluate quality and reliability; do not assume production readiness for unattended clinical processing from the synthetic tests alone.
