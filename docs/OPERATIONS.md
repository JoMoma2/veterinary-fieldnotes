# Operation, configuration, and recovery

Run commands from the application checkout with a current Node release and uv. Keep local config, credentials, private workspaces, and backup keys outside the repositories.

## Configure the private pipeline

```bash
mkdir -p ~/.config/vet-fieldnotes
chmod 700 ~/.config/vet-fieldnotes
cp config/pipeline.example.toml ~/.config/vet-fieldnotes/pipeline.toml
chmod 600 ~/.config/vet-fieldnotes/pipeline.toml
uv sync --project pipeline --python 3.12 --extra dev
```

Defaults use mock extraction, refuse clinical inputs to mock, disable inference charges and remote processing, disable model downloads, and disable deletion. Use a separate workspace for each synthetic/real dataset. `--authorization-ref` records the actual authority for capture/processing; it is not permission to publish or use cloud storage.

### Import prepared transcripts

JSON contract:

```json
{
  "segments": [
    {"start": 0.0, "end": 15.2, "text": "An authorized, timestamped transcript segment."}
  ]
}
```

Offsets must be finite, ordered, nonnegative, and increasing within each segment. Optional recording `capturedAt` and `clockConfidence`, and per-segment `clockTime`/`clockConfidence`, preserve explicitly established clock data. Use offset-qualified ISO timestamps. Do not declare a device clock verified without checking it. A synthetic mock transcript also needs a known `fixtureKey`; see the fixtures.

```bash
uv run --project pipeline vet-pipeline --workspace /tmp/vet-synthetic ingest \
  fixtures/pipeline/transcripts/01-first.json \
  --shift s-2026-10-22 --date 2026-10-22 --origin synthetic --authorization-ref synthetic-test
uv run --project pipeline vet-pipeline --workspace /tmp/vet-synthetic run
uv run --project pipeline vet-pipeline --workspace /tmp/vet-synthetic status
```

`status` is private operator output and includes import metadata. Do not post it publicly. `run` reports safe job/stage/error information without logging model response bodies. Check `events.jsonl` and `quarantine/` inside the workspace for failures or malformed questions. After fixing a problem:

```bash
uv run --project pipeline vet-pipeline --workspace /PATH/PRIVATE retry r-RECORDING_ID
uv run --project pipeline vet-pipeline --workspace /PATH/PRIVATE run
```

Automatic retries stop at the configured maximum. `--force-retry` bypasses the delay, not the attempt limit. `retry` explicitly resets the limit after operator correction. A model/config change does not silently discard a valid saved extraction checkpoint. Preserve the old checkpoint and deliberately remove only the affected extraction checkpoint if re-extraction is necessary; keep the transcript and recording hash. Do not repeat an already committed recording to revise a note—use owner edits.

### Ollama

Select a locally installed candidate model in `provider.model`, set `kind = "ollama"`, and use `http://127.0.0.1:11434`. Start the owner-managed Ollama service separately. Remote Ollama hosts require `allow_remote=true` and HTTPS. Explicit clinical third-party authorization is also required for remote clinical requests. No candidate model is installed or selected by this repository.

### Compatible inference APIs

Set `kind = "openai-compatible"`, the actual base URL ending in `/v1`, a candidate model, and an environment variable name for the key. Set `allow_paid=true` only when API use is authorized, and `allow_remote=true` for a remote endpoint. Clinical requests additionally need `backup.allow_clinical_remote=true` under an actual applicable authorization. This shared switch authorizes third-party handling; do not enable it for private clinical material merely because encryption or a private repository exists. A Codex/Claude subscription does not grant API usage.

Compatible JSON-mode requests use `/chat/completions`. Ollama uses `/api/chat` with a JSON schema. Both adapters have bounded request timeouts and no hidden retry loops. Unsupported endpoint features or invalid output become resumable extraction failures. Strict JSON mode may require adaptation for individual services.

### WAV transcription

```bash
uv sync --project pipeline --python 3.12 --extra audio --extra dev
```

Set `transcription.model` to a tested local model path or name, plus the appropriate device/compute type. Model downloads remain disabled until `allow_model_download=true` is deliberately set. WAV import validates complete PCM frames, copies without altering the original, hashes content, and preserves unverified filesystem metadata. No exact filename or recorder directory layout is assumed. Each file resumes separately.

```bash
uv run --project pipeline --extra audio vet-pipeline --config ~/.config/vet-fieldnotes/pipeline.toml \
  ingest /PATH/RECORDER/*.WAV --shift s-YYYY-MM-DD --date YYYY-MM-DD \
  --origin authorized-record --authorization-ref YOUR_ACTUAL_AUTHORIZATION
uv run --project pipeline --extra audio vet-pipeline --config ~/.config/vet-fieldnotes/pipeline.toml run
```

An optional genuine synthetic-speech smoke test uses a local espeak-ng shared library:

```bash
uv run --project pipeline --extra audio python scripts/audio-smoke.py --download-model
```

The download is a small open model, not paid inference. Later runs can omit the download flag. This uses `tiny.en` solely to check WAV decoding, inference, and offsets. It is **not** a recommended clinical model: the session's generated speech test had wording errors.

### Benchmark models

Make a separate config per model. First use synthetic transcripts; later use authorized transcripts in a private location. For actual authorized data add `--origin authorized-record --authorization-ref YOUR_PERMISSION`; the same remote/paid/clinical authorization gates apply.

```bash
uv run --project pipeline vet-pipeline --config /PATH/candidate.toml benchmark \
  fixtures/pipeline/transcripts/01-first.json fixtures/pipeline/transcripts/02-followup.json \
  --output /PRIVATE/candidate-report.json
```

Each report preserves elapsed time, output-validity result, expected/forbidden marker checks, complete private output, and manual review fields for useful capture, misses, invented details, terminology, case linking, and safe updates. Marker matching is a smoke check; review outputs and run the consolidation integration scenario for each candidate. Do not infer “90% accuracy” from marker counts. No cloud API benchmarking is executed by default.

## Edit and review knowledge

Copy `WORKSPACE/library/current/` to a separate editing folder. Edit article Markdown, JSON facts, or topic display names; permanent article/case/discussion IDs stay unchanged. Topic categories can be reorganized if every reference is updated and the graph remains valid.

```bash
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE apply-edits --source /PRIVATE/EDITED_LIBRARY
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE review-template /PRIVATE/review.json
```

Suggested category names/descriptions are reviewed entries too; categories referenced by published records must be approved. For each approved entry in the review file, the authorized reviewer must verify content, authorization, sufficient de-identification including combinations of details, and medical interpretation; then set `approved=true`, `privacyReviewed=true`, reviewer, ISO timestamp, and an actual `authorizationRef`. The supplied hash binds that exact record. Keep this review file private. It is not included in the public export. Any content change requires new review.

For synthetic testing only:

```bash
uv run --project pipeline vet-pipeline --workspace /tmp/vet-synthetic approve-synthetic /tmp/synthetic-review.json
uv run --project pipeline vet-pipeline --workspace /tmp/vet-synthetic export \
  --review /tmp/synthetic-review.json --target fixtures/generated/public
```

`approve-synthetic` refuses any real record. Production builds reject synthetic records in `content/public`. Real publication uses the same export command with a manually completed review file, target `content/public`, and explicit `--allow-clinical` after applicable authorization and privacy review. It is not a blanket legal or medical approval.

For an authenticated public repository, the explicit publication helper exports, checks, builds, and commits only `content/public`. Add `--push` to trigger the connected Cloudflare deployment:

```bash
uv run --project pipeline python scripts/publish-approved.py \
  --workspace /PRIVATE/WORKSPACE --review /PRIVATE/review.json \
  --checkout /PATH/vet-knowledge-library --allow-clinical --push
```

The nightly importer never grants publication approval. Successful private processing does not wait for public review.

## GitHub

Current storage: **private GitHub primary remote, local secondary copy, Cloudflare approved public hosting**. Independent cloud backup is deferred and optional; no rclone credentials or encryption key are needed for this path.

Two repositories are prepared: `veterinary-fieldnotes` (public) and `veterinary-fieldnotes-master` (private). The private archive now contains synthetic durability-test records only. Synchronization includes an integrity/recovery manifest and verifies the remote commit. It refuses to replace committed records with an empty/incomplete local archive. Run setup for another account as needed:

```bash
gh auth login
python3 scripts/github-setup.py --owner YOUR_ACCOUNT                 # plan only
python3 scripts/github-setup.py --owner YOUR_ACCOUNT --create --push
```

The helper verifies existing visibility instead of changing it, keeps Git identity in each local checkout, stages known application paths, and refuses common credential/raw-audio patterns. Review repository access and branch protection according to the intended collaboration policy. No public editing UI exists.

Authorized private synchronization is separate:

```bash
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE \
  --config /PRIVATE/pipeline.toml sync-master --checkout /PATH/vet-knowledge-master
```

`--push` sends the prepared commit. Actual clinical cloud synchronization also requires config `backup.allow_clinical_remote=true` **and** `--allow-clinical`. The helper verifies private remote visibility and copies permanent content plus sanitized processing status only. It never copies the database, raw audio, temporary transcripts, or credentials. First use synthetic data to test it. This is the primary remote archive under the current storage plan; Cloudflare holds only the approved public subset.

### Private master synchronization

Use a dedicated private `main`-branch checkout, with working owner Git/`gh` authentication. Do not put raw audio, temporary transcripts, credentials or the SQLite ledger in it. Copy settings into the existing private pipeline TOML (do not duplicate TOML sections):

```toml
[github]
enabled = true
checkout = "/home/quinten/vet-knowledge-master"
allow_clinical = false
retry_seconds = 60
max_retry_seconds = 3600
verify_interval_seconds = 3600

[backup]
remote = ""
allow_clinical_remote = false
```

These settings permit synthetic synchronization only. After separately authorizing clinical GitHub storage, the owner must deliberately set **both** `github.allow_clinical=true` and legacy-named `backup.allow_clinical_remote=true`. The latter name does not require an independent backup account. Publication permission remains separate. No clinical storage permission is enabled by the examples or this project update.

With synchronization configured, both `run` and `nightly` process local recordings first, then commit/push completed canonical knowledge and verify the exact remote commit:

```bash
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE \
  --config ~/.config/vet-fieldnotes/pipeline.toml run
# Or process queued work and configured recorder mounts; no backup key required:
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE \
  --config ~/.config/vet-fieldnotes/pipeline.toml nightly
```

`WORKSPACE/master-sync/state.json` records pending status, snapshot hash, attempts, next retry time and verified commit; `master-sync/events.jsonl` records class-only errors without Git stderr/credentials. A push failure leaves the local canonical library, inference checkpoints and any prepared Git commit intact. Subsequent invocations retry with no new recordings and no repeated inference. Each invocation makes at most one attempt; delays start at60s and cap at1h, remaining pending across long outages. Unchanged successful snapshots are reverified hourly; new knowledge is synchronized immediately. Processing errors in one recording do not prevent successful records from being synchronized. Pending sync returns nonzero so scheduler/operator logs expose it; future timer invocations continue retries. No automatic service is activated here.

For an immediate operator retry, bypassing the waiting interval:

```bash
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE \
  --config ~/.config/vet-fieldnotes/pipeline.toml sync-master \
  --checkout /home/quinten/vet-knowledge-master --push
# Add --allow-clinical only after authorization, alongside the config storage gate.
```

Use one active canonical workspace/writer per master checkout. On authentication/visibility/branch conflicts, inspect local configuration and reconcile deliberately; the system never force-pushes, resets history, or erases local work to fix a rejected push. Recovery remains `git clone` the private master, validate its `archive` manifest and run `recover-library --source /PATH/CLONE/archive` into a new workspace. Existing synthetic fresh-clone and lost-local-data tests cover this path. The private pilot evaluation tool explicitly disables all synchronization even if the supplied config enables it.

## Cloudflare Pages

No paid service is needed for the static website. Connect the public repository in Cloudflare **Workers & Pages → Create → Pages → Import a Git repository**. Select:

- Production branch: `main`
- Build command: `npm run build`
- Output directory: `dist`
- Environment: `NODE_VERSION=24`, `LIBRARY_DATASET=production`, `ASTRO_TELEMETRY_DISABLED=1`

Set the same production dataset for preview builds. Do not attach a private master repository or add private workspace content/secrets to build contexts. Native Pages Git integration rebuilds on approved-content commits. `wrangler.toml` and `_headers` are supplied. CI verifies production, demo, and pipeline behavior without deploying demonstration output.

Alternatively, after creating the free Pages project, configure `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and optional `CLOUDFLARE_PROJECT_NAME` outside source control. Then `npm run build && npm run deploy`. The deployment helper refuses a non-production build, even if the shell dataset is changed afterward. It does not create a paid resource. Do not add tokens to command arguments, repository files, or logs. This installation is now connected with protected local Wrangler OAuth. The production Pages site is https://veterinary-fieldnotes.pages.dev; native Git builds need no long-lived token stored in GitHub.

## Encrypted backups, remote storage, and restore

**Optional future path.** These tools remain available, but are not a normal-processing or operational-readiness requirement. Leave `backup.remote` empty and omit `nightly --key/--backup-directory` unless deliberately opting in.

Create a key once, outside the repositories. Keep a separate secure copy of the key; the encrypted backup cannot be recovered without it.

```bash
uv run --project pipeline vet-pipeline backup-key ~/.config/vet-fieldnotes/backup.key
uv run --project pipeline vet-pipeline --workspace /PRIVATE/WORKSPACE backup \
  --key ~/.config/vet-fieldnotes/backup.key --destination /PRIVATE/LOCAL_BACKUPS
```

Backups contain permanent library content, case continuity mapping, and hashes needed for completed-recording deduplication. No raw audio or temporary transcripts are included. Each version has a unique filename and authenticated encryption. Creation verifies decryption and every file hash before recording success.

If opting into independent backups later, install/configure rclone with a separately authorized provider (`rclone config`, select Google Drive or another provider). OAuth remains in rclone's local protected configuration. Set `backup.remote="gdrive:vet-fieldnotes-encrypted"`; then run `upload`. rclone copies immutable encrypted files and the application verifies remote bytes. There is no remote delete, mirror, or historical pruning. A failed upload only consumes its own bounded retry budget. After fixing a persistent upload failure, run `retry-upload BACKUP_ARTIFACT_ID` to reset only its upload attempt limit. Do not delete/recreate the recording job.

Restore into a new folder:

```bash
uv run --project pipeline vet-pipeline restore /BACKUPS/VERSION.vkb \
  --key ~/.config/vet-fieldnotes/backup.key --target /PRIVATE/restored-library
uv run --project pipeline vet-pipeline --workspace /PRIVATE/new-workspace recover-library \
  --source /PRIVATE/restored-library
```

Existing destinations/workspaces are refused. Corrupt ciphertext, path traversal, duplicate members, hash mismatches, malformed data, and broken references abort before replacing working data. `recover-library` restores canonical records, completed hashes, and case linkage to a new ledger. Re-import unfinished recordings from retained originals. The original computer is not required except for the separately stored key and configured software.

Cleanup is dry-run by default (`cleanup`). Enable `[retention] enabled=true` only after successful backup/restore trials, configure the required remote success and age, then use `cleanup --apply`. A completed job with unresolved quarantined study output remains on hold. Only disposable copies under the private workspace are eligible. The original recorder is never erased. Nightly automation reports a dry run while retention is disabled; once explicitly enabled, it applies only eligible workspace cleanup after all checks.

## Recorder and unattended Ubuntu service

See [USB_AUTOMATION.md](USB_AUTOMATION.md) for the actual staged setup, first-shift instructions and test evidence. Production now uses `vet-pipeline unattended`, which enforces exact registered UUID/serial matching, source-preservation locks, local inference, per-stage shared-GPU deferral, temporary sleep inhibition, resumable jobs, private synchronization and offline morning reports. The older `scan`, `run` and `nightly` commands remain available for explicit operator workflows; the unattended service adds the above guards.

The owner-only configuration is `~/.config/vet-fieldnotes/pipeline.toml`; the production workspace is `~/.local/share/vet-fieldnotes-live`. Units and application launchers are installed **disabled** while the recorder is absent. Open **Fieldnotes — Register Recorder** after connecting it; activation requires a matching UUID, local recording/processing authorization and the current code's passed synthetic test. Clinical GitHub storage is a separate explicit consent/reference, public approval remains separate, and retention/deletion remain locked off. Do not bypass registration by manually enabling an unmatched timer.

**Fieldnotes — Morning Review** opens the local `review/index.html`. It contains full retained audio/transcripts, timestamp playback, extracted discussions, article/source links, cases, study material, unclassified excerpts, timing/status and unapproved publication candidates. It uses no listening web server or external resources.

Polling is approximately every2minutes; automatic file stability uses observations across polls, rather than trusting the recorder's clock. Incomplete/changing WAVs are deferred individually. Queued work resumes after login/restart even if the recorder is unplugged. `Linger=no` remains unchanged: keep Ubuntu signed in (screen lock is fine); signed-out/headless activation is unverified. The service holds a temporary sleep inhibitor during active work where session policy permits, never changes global power settings, and never restarts/unloads MMM/FCC/Ollama.

## Current local AI compatibility and benchmarks

Read [AI_ENVIRONMENT.md](AI_ENVIRONMENT.md) before changing local AI tooling. The existing Ollama installation already accelerates on the 7900 XTX through bundled ROCm. There is no system HIP compiler. Preserve MMM/FCC dependencies and use the project-specific request settings in `config/benchmarks`. No model download or driver/SDK change is part of benchmark execution. Use `scripts/remote-durability-drill.py` with a new protected work directory to repeat the synthetic GitHub recovery exercise. It never publishes to the website or enables clinical storage.
