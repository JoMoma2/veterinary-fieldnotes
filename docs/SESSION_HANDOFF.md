# Session handoff — first-recording readiness r3 (2026-11-02)

## Resume here

Checkout `/home/quinten/vet-knowledge-library`. Session started from **1c040d6** (earlier milestone caed084). Use `git log -3` for this session's committed revision. **Do not restart or redesign the website or rerun the model comparison suite. The next useful task is the user's first authorized real recording.** No real recording was available/processed.

Read AGENTS.md, docs/FIRST_RECORDING.md, docs/LOCAL_AI_BENCHMARKS.md and docs/INDEPENDENT_BACKUP.md. Production must remain empty and deployed at https://veterinary-fieldnotes.pages.dev. Never export this pilot into public or demo roots. No USB monitor, deletion policy, clinical cloud synchronization or paid inference is enabled/authorized.

## Completed changes

1. **Complete serialized-prompt budgeting:** `pipeline/vet_pipeline/budget.py` counts actual system/user message content including response schema, source text/IDs and bounded topic index, then reserves output + chat/template + safety. Qwen profiles use checksum-pinned offline tokenizers. Unknown tokenizers use conservative UTF-8 byte counting; configured missing/bad files fail locally. Compatible API adapter no longer appends unbudgeted duplicate schema and explicitly limits output.
2. **Stable proactive partitions:** `extraction.py` persists transcript-SHA/ranges/estimates in `extractions/JOB/chunk-plan.json` before inference. New jobs choose fitting contiguous chunks and prefer explicit late topic boundaries. Recounts actual growing topic context before HTTP. Saved child split decisions survive interruption. Legacy numeric checkpoints/splits retain old source-character boundaries, unchanged successful bytes and old canonical IDs. No canonical schema migration.
3. **Unclassified preservation:** the old 14 excerpts were genuine model omissions, including useful explicit unknowns and context markers. The instruction requests meaningful unknown information; deterministic fallback can label literal unknown clauses without inventing topic/patient/case association. All unclassified accounts remain visible/private. Quality distinguishes omitted/context-only/deterministic sources. Owner reorganization uses the established apply-edits path.
4. **Isolated private real-pilot workflow:** `scripts/evaluate-recording.py` inspect/prepare/transcribe/extract/report. `audio_prepare.py` uses local PyAV/libswresample to make mono16k PCM16 copies, checks duration/hash/stability, never alters original. `evaluation.py` preserves original + normalized audio, immutable ASR, separate corrected reference/recollections/review.csv, model/input/settings/digest-specific results and checkpoints. Offline escaped `review.html` provides audio/timestamp links, discussions/fact types/cases/article targets/cards/manual findings. No public server, external assets, inference, publication or upload is needed to review.
5. **Privacy guards:** private pilot, backup, key and restore paths reject any actual Git checkout, including private master. Additional ignores provide defense in depth. Pilot requires installed local GGUF metadata on loopback Ollama:11434, refuses cloud-backed models, disables remote backup/paid/remote inference/model auto-download/retention/USB roots for its own config. Existing global/service configs untouched. ASR/input snapshots cannot be silently edited; references require explicit manually-corrected status.
6. **Independent backup preparation:** user-local rclone1.75.2, project-specific private config/setup helper and example Drive config. Existing immutable encrypted backup system gains safe exact-version download with SHA/authenticated-decryption/library validation, no overwrites/deletions. Cloud guard checks recovered canonical record origins as well as jobs. Two-version synthetic transfer/restore drill prepared for any configured provider. User confirmed **no existing credentials**; do not re-ask for tokens. They must run the documented interactive Drive OAuth setup.
7. **Documentation/tests:** FIRST_RECORDING.md has exact commands; INDEPENDENT_BACKUP.md covers own desktop OAuth client, drive.file scope, seven-day Testing refresh-token caveat, recovery key/client/account custody. Updated benchmarks/readiness/architecture/README/AGENTS. CI installs optional PyAV evaluation dependencies, with no model downloads.

## Measurements and limitations

One targeted Qwen3 run reused the r2 **374 s saved ASR transcript**, not new audio:

- Extraction **199.387→125.581 s (~37% less)**; extraction + projection125.983 s.
- Six planned requests, zero oversized calls, all `stop`. Actual prompt tokens3095,3704,2709,2550,3650,2003; local estimates49tokens higher each. Context8192/output4096/safety128.
- Classified **158→161 of172**, unclassified **14→11**. All172 retained in accounts. Model source coverage is not semantic accuracy. Prompt and planning both changed, so this is not a pure chunk-size ablation.
- AMBER contradiction retained, explicit CEDAR follow-up/vitals linked; unrelated FIP teaching no longer created a case. ASR seeder/cedar labels remain separate conservatively. Actual IV fluids sometimes mislabeled proposed; lactate sometimes owner-report; unknown outcome sometimes outcome. Duplicate blood-sample topics remain. **Study cards fell39→3.** Do not claim extraction quality solved or unattended clinical readiness.
- Result13articles/3cases/34discussions/3cards; repeated fixtures mean counts alone prove little. No further synthetic tuning is needed before real review.

New private-pilot smoke used **41.130625 s synthetic medication WAV**: Large V3 **2.578 s**; Qwen3 **10.685 s**; Qwen3.5 **15.198 s**. Each model completed one article/case/discussion, **zero cards**. Cached replay reused the same run. Browser checks at390/1440px verified audio duration/playback, two model sections, no overflow and zero HTTP requests. No new ASR accuracy/clinical score was measured; r2's known drug/case-label errors remain relevant.

Two encrypted synthetic versions uploaded/downloaded/restored exactly using **rclone local adapter**, with source workspace/local backups renamed unavailable. Version hashes/decryption/library equality passed. This is **not independent cloud validation**. Independent provider and off-machine key custody remain unverified. No clinical cloud storage authorization exists. Earlier private-master GitHub synthetic recovery evidence remains unchanged.

Sanitized data: docs/validation/readiness-r3.json. Historical r2 throughput estimates remain conditional; a saved-ASR timing cannot replace a full-shift benchmark.

## Installed components and locations

Unchanged hardware: Ryzen7 7800X3D, RX7900XTX24GiB,64GiB, Ubuntu26.04.1, Ollama0.34 GPU. MMM depends on qwen3:30b; FCC also uses this environment. Do not stop/restart/unload others' work or change global Ollama, drivers or ROCm.

Unchanged weights/executables:

```
~/.local/share/vet-fieldnotes-ai/whisper.cpp-v1.9.5/build-vulkan/bin/whisper-cli
~/.local/share/vet-fieldnotes-ai/models/ggml-large-v3.bin
~/.local/share/vet-fieldnotes-ai/models/ggml-tiny.en.bin
Ollama: qwen3:30b; qwen3.5:9b-q4_K_M; gemma3:12b-it-q4_K_M
```

New metadata/tools (no new model weights):

```
~/.local/share/vet-fieldnotes-ai/tokenizers/qwen3/tokenizer.json
  SHA aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4
~/.local/share/vet-fieldnotes-ai/tokenizers/qwen35/tokenizer.json
  SHA 5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42
~/.local/share/vet-fieldnotes-tools/rclone  (v1.75.2, official checksum verified)
```

`source.json` beside tokenizer files records pinned upstream revisions/checksums. `scripts/install-tokenizers.py` provisions only ~24MB public metadata, explicitly; runtime never downloads tokenizers. Pyproject now directly depends on tokenizers0.23.x, and optional `evaluation` includes PyAV16.x without requiring Faster-Whisper. `uv.lock` updated. User-local rclone release archive/checksums remain in its tools directory. One browser-check command accidentally used npm exec node and populated an npm cache with an unnecessary Node prerelease; it did not change project/global toolchains or repository dependencies. Subsequent checks use the established Node24 wrapper/runtime.

Private artifacts (all synthetic) under `~/.local/share/vet-fieldnotes-validation/readiness-r3/`:

- `budget-comparison/`: planned Qwen3 long extraction, quality/budgets, transcript, canonical records and ledger.
- `pilot-smoke/`: original/normalized synthetic WAV, transcript/reference, model results, editable-library snapshots, offline report.
- `adapter-drill/restore-drill.json`: two-version local rclone restoration evidence. `unavailable-source-workspace`, `unavailable-local-backups`, `replacement` retained. Its disposable key is `adapter-drill-recovery.key` outside the test workspace; **not off machine**.
- `adapter-remote/`: local rclone test destination; not a cloud account. `local-backup-test.toml` used only this adapter.

Earlier artifacts remain at `local-ai-r2/` (seven WAVs/full workflow/SIGINT/model comparison) and `local-ai-20261102/`. Do not erase/re-plan historical artifacts to change results.

## Verification and stopping state

- **92 Python tests** pass (`uv run --project pipeline --extra evaluation pytest pipeline/tests`), including seventeen readiness tests; prior failure isolation/checkpoint/backup tests preserved.
- **16 TypeScript tests**, Astro/content check pass; production remains zero medical records.
- Empty production build:8pages/87internal links/anchors; no private sentinel/audio/source maps.
- Empty-state browser test1pass; public desktop/mobile/search/privacy tests4pass locally; regenerated mock pipeline export and four desktop/mobile source/search/card browser tests pass.
- Real synthetic pilot + cached replay + offline browser audio/privacy/layout checks pass.
- Existing SIGINT/recovery regression tests remain; this session did not need another disruptive live interruption.
- Independent cloud restoration **not performed**: no credentials, confirmed by user. Follow setup guide, then synthetic drill.
- CI and post-push live production audit: see final verification addendum below / current GitHub Actions run. Do not assume local checks prove a future push deployed.

No service/retention was enabled. No real data, API charges, model downloads, private-master edits or global configurations changed. Stop only processes created for tests; preserve MMM/FCC/Ollama. Final local dist must remain production.

## Exact next steps

1. User supplies a 5–15 minute authorized WAV and local processing authorization reference. Read FIRST_RECORDING.md, check shared GPU utilization; do not interfere with MMM/FCC. Prepare one new private root outside both repositories.
2. Record recollections before looking at AI output. Run Large V3 once, Qwen3 and Qwen3.5 sequentially on identical ASR. Open offline report. Commands below; replace source/date/reference.
3. Listen/correct `reference.json` without editing immutable ASR or guessing medical terms; mark manually-corrected. Repeat models with `--input reference`. Record actual missed/incorrect/invented/source/case/topic/study problems in review.csv, refresh report. No auto-publication or upload.
4. Fix only observed real-data failures. Prioritize evidence labels, patient continuity, topic duplication and card usefulness. Current source quotes/JSON validation alone cannot certify these. Avoid another large download or model-review swarm.
5. User authenticates Drive in their terminal with `./scripts/configure-backup.sh`; follow INDEPENDENT_BACKUP.md. Copy backup example outside Git, run synthetic `backup-drill.py` against the authenticated remote, preserve historical objects and test an off-machine recovery key. No clinical storage until separately authorized.
6. Actual recorder: format/mount/clock/voice-activation/overnight grouping tests, then representative duration/100+file quality and throughput. Only later consider explicitly authorizing unattended watcher/retention.

```bash
cd /home/quinten/vet-knowledge-library
uv sync --project pipeline --extra dev --extra evaluation --frozen --inexact
mkdir -p ~/.config/vet-fieldnotes
chmod 700 ~/.config/vet-fieldnotes
cp -n config/benchmarks/local-vulkan.example.toml ~/.config/vet-fieldnotes/pilot.toml
cp -n config/benchmarks/qwen35-9b.toml ~/.config/vet-fieldnotes/pilot-qwen35.toml
chmod 600 ~/.config/vet-fieldnotes/pilot*.toml
pilot_root="$HOME/.local/share/vet-fieldnotes-evaluations/first-real-001"
recording_source='/ACTUAL/RECORDER/FILE.WAV'
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py inspect "$recording_source"
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py prepare "$recording_source" \
  --workspace "$pilot_root" --date YYYY-MM-DD --authorization-ref LOCAL-AUTHORIZATION-REFERENCE
# Write recollections.md now.
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py transcribe "$pilot_root" \
  --config ~/.config/vet-fieldnotes/pilot.toml
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py extract "$pilot_root" \
  --config ~/.config/vet-fieldnotes/pilot.toml --input asr
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py extract "$pilot_root" \
  --config ~/.config/vet-fieldnotes/pilot-qwen35.toml --input asr
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py report "$pilot_root"
xdg-open "$pilot_root/review.html"
```

## Verification addendum

Milestone **ab11b16** was committed/pushed to public `main`; [GitHub Actions run 41551661479](https://github.com/JoMoma2/veterinary-fieldnotes/actions/runs/41551661479) passed the full production/mock/demo/browser workflow. Cloudflare's native Git deployment updated `build-info.json` to that exact commit with dataset `production` and all five record counts zero. Four live public desktop/mobile/search/privacy browser tests passed against https://veterinary-fieldnotes.pages.dev (not only a local build). Logs remain `/tmp/fieldnotes-live-browser.log`; earlier local checks in `/tmp/fieldnotes-*.log` are disposable.

A final small recovery fix recreates only a missing draft reference after an interruption between ASR metadata and template creation, preserving any existing corrected reference. Its regression test passes within the same92-test suite. Reports explicitly label timing as the recorded invocation, excluding earlier checkpointed work. The final follow-up commit's CI/deployment should be checked by its `git log` SHA; the session final report records that result. No inference/preview/background benchmark is left running, and the final local dist is empty production. Ollama `/api/ps` showed no benchmark model loaded. Independent backup credentials remain an owner setup task, as confirmed by the user.
