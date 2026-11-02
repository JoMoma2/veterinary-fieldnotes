# Continuation handoff — local AI r2, 2026-11-02

## Current state

Continue `/home/quinten/vet-knowledge-library`. Do not rebuild/redesign the website. Starting commit was `799f344`; code milestone is **`caed084`**, followed by the final configuration/documentation commit (see `git log`). The user authorized Large V3 and the two requested alternative local models; those downloads are complete. No account authorization is needed to repeat local synthetic tests.

Read AGENTS.md and LOCAL_AI_BENCHMARKS.md. **Local WAV processing now completes, but clinical unattended readiness is not established.** Production must remain empty. Public repo is `JoMoma2/veterinary-fieldnotes`; private master `/home/quinten/vet-knowledge-master` was not modified. Native Pages URL: https://veterinary-fieldnotes.pages.dev. No real data, paid API, USB service/deletion, global Ollama, MMM/FCC, driver or ROCm changes occurred.

## Completed

- Installed checksum-verified **Whisper Large V3 f16** using the existing whisper.cpp Vulkan backend. No new system build dependencies needed.
- Downloaded/ran **Qwen3.5 9B Q4_K_M** and **Gemma3 12B Q4_K_M**, preserving existing Qwen3 and all global defaults.
- Compared all three extraction models on seven identical synthetic transcripts with the same final compact contract/settings. Actual outputs and human-readable reports retained locally.
- Implemented `grounded-v2`, a model wire adapter that leaves permanent version-1 schemas intact. Code assigns evidence/record IDs, offsets, flashcard answers and links. Model facts require source quotations. Detailed accounts preserve selected source wording, avoiding unsupported medical paraphrases.
- Limited deterministic repairs to unique casing/whitespace spans and conservative uncertainty/type/topic fixes. No drug spelling, number, negation or medical-fact guessing. Unsupported material is preserved unclassified, visibly requiring review.
- Cases use explicit supported labels, conservative continuation and negative-relationship checks; anonymous cases cannot link across files. Legacy case IDs survive recovery. Substantive topic filtering/acronym reuse reduces observed bad bindings, but does not fully solve semantic deduplication.
- Added bounded context-aware chunk sizing and adaptive **output-limit splits**, at most two levels; completed children/parent split decisions are durable checkpoints. Added source-quality/stage timing logs.
- Added four richer synthetic transcript/gold files, including drugs/abbreviations, contradictions, ambiguous speaker/patient, equipment, practical workaround and a positive confirmed-diagnosis/outcome control.
- Added timed audio generation, real-audio authorization/report-location gates, strict inspectable fact/source/type screens, `.md` review reports and a resumable synthetic-only full-pipeline benchmark helper.
- Actual seven-WAV pipeline saved results, deduplicated re-imports, exported only to ignored pipeline-demo and displayed in the website. A 6.2-minute waveform completed after token-limit splitting; unclassified sources were retained.
- Actually SIGINT-interrupted a successful child checkpoint and resumed without retranscription or repeated child inference. Three existing checkpoint hashes unchanged.
- Added deterministic adapter/recovery tests and desktop/mobile generated-data source navigation/search/flashcard tests; included the latter in CI using mock fixtures, with no AI required in CI.

## Key measurements (not clinical accuracy certification)

- Large V3: **166.62 s / 420 reference words in 12.77 s**, normalized WER **3/420 (0.71%)**. Tiny: 71/420 (16.90%). Whole-GPU peak about 5.26 GB for isolated Large. All 13 controlled utterance starts matched; max coarse segment-start error 0.049 s, not word/ER timing validation.
- Critical remaining ASR errors: maropitant → **Meripitant**; the additional ELM case label became **cat KCLM training**. Never silently repair these by medical plausibility. Capitalization/hyphens in explicit labels are often lost.
- Final seven-transcript comparison: Qwen3 **44.22 s, 36/51 strict typed-clause matches, 18 cards**; Qwen3.5 **62.10 s, 41/51, no cards**; Gemma **78.22 s, 35/51, 26 cards**. All retained 51 clauses in source accounts and had the expected conservative case counts. Source copying is not semantic accuracy; inspect type, grouping and question quality.
- Qwen3 generation ~139–140 tokens/s; Qwen3.5 ~91–92; Gemma ~64–66. Short isolated text probes at context 8192 report full model GPU residency: **19.37 / 5.83 / 8.35 GB** respectively. Whole-GPU peaks may include desktop/residual buffers; do not use them as model allocations.
- Seven WAVs: **180.00 s audio → 73.72 s**, 11 articles / 3 cases / 1 shift / 17 discussions / 6 cards; 55 classified sources, zero unclassified.
- Uninterrupted long workload: **374.00 s → 229.06 s**, including two oversized-response failures and smaller retries; 14 articles / 7 cases / 1 shift / 38 discussions / 39 cards; 158 classified / 14 unclassified. Repeats known synthetic material twice, so throughput only, not independent quality evidence.
- Nominal 4/8/12 recorded-hour illustration with 100-file allowance: **1.7–2.5 / 3.4–5.0 / 5.0–7.4 h**. With 2× planning contingency: **3.4–5.1 / 6.7–10.0 / 10.0–14.9 h**. No 12-hour clinical-shift guarantee. Actual recorded speech differs from work-shift duration.

## Installations and artifacts

```
AI root: ~/.local/share/vet-fieldnotes-ai
whisper source: AI root/whisper.cpp-v1.9.5
executable: source/build-vulkan/bin/whisper-cli
weights: AI root/models/ggml-large-v3.bin and ggml-tiny.en.bin
user-local compiler tools: AI root/toolchain/usr (from previous session)
current private trial root: ~/.local/share/vet-fieldnotes-validation/local-ai-r2
previous trial root: ~/.local/share/vet-fieldnotes-validation/local-ai-20261102
```

Large SHA256: `64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2`; whisper commit `d1be6fde11ac6e0407606b4e42fe72d34add8037`. Ollama model digests/memory are recorded in `docs/validation/local-ai-r2.json`. No extremely large additional candidates, quantization variants, HIP SDK or driver updates were installed.

Private trial root contains:

- `*-selected-v2.json` and `.md`: final fair seven-transcript model comparison. All three have measured contract hash `7d0fbd2e3f5717d6fc102feb34dd5dfce5c48a5a6b1bc298369439902f6d1e89`. Subsequent small species-word-boundary/chronological-order fixes changed projector source hash but not the inference instructions. Older `*-comparison`, `*-final` and `qwen-grounded-*` are exploratory prior revisions; do not mix scores as identical-contract runs.
- `large-basic.json`, `large-pipeline.json`, `large-timed.json`, `tiny-timed.json`: actual transcription output/errors/resources/alignment. `timed-audio/` holds the six-clip fair audio comparison.
- `pipeline7-audio/manifest.json`: seven WAV full-pipeline corpus. `long-audio/manifest.json`: repeated 374 s stress waveform.
- `full-workspace/pipeline-benchmark.json`: seven-WAV run; `long-fresh-workspace/pipeline-benchmark.json`: uninterrupted adaptive long-run timing. Inputs/transcripts/extractions/quality and SQLite ledger retained.
- `long-workspace/`: initial failed long job, then actual split/SIGINT recovery. Final stage done. `adaptive-recovery.json`, `long-interrupted.log`, `long-resumed.log` provide evidence. Do not use this interrupted run for throughput.
- `local-large-qwen.toml`: historical exact local config; keep unchanged because benchmark helper binds its hash to session metadata.
- `model-vram.json`: one-token model-residency probes; no application config was altered.
- `pipeline-build.log`, `pipeline-browser.log`, `long-build.log`, `long-browser.log`: actual-model website export tests. The seven-file build verified 40 pages/617 links; the long build 68 pages/1057 links. Four desktop/mobile generated-data tests passed for each.

Full artifacts stay outside Git. Only sanitized synthetic metrics were committed. Ignored `fixtures/generated/public` contains the long test export. Never deploy it. Historical checkpoints intentionally retain their old outputs; the last chronological sorting fix affects new jobs, not already committed artifacts. Do not erase checkpoints just to change a benchmark result.

## Commands

From project checkout:

```bash
# Check shared GPU work before running inference. Do not unload others' models.
curl -s http://127.0.0.1:11434/api/ps
cat /sys/class/drm/card1/device/gpu_busy_percent

# Use new output/workspace paths for a new model, corpus or configuration.
uv run --project pipeline python scripts/generate-benchmark-audio.py \
  --corpus pipeline --timed --output /PRIVATE/new-audio
uv run --project pipeline python scripts/benchmark-local-pipeline.py \
  --manifest /PRIVATE/new-audio/manifest.json --config /PRIVATE/local.toml \
  --workspace /PRIVATE/new-workspace --export-test
LIBRARY_DATASET=pipeline-demo ./scripts/local-node.sh run build
E2E_PIPELINE=1 ./scripts/local-node.sh run test:e2e

# Permanent default must finish as empty production.
LIBRARY_DATASET=production ./scripts/local-node.sh run build
E2E_PUBLIC=1 ./scripts/local-node.sh run test:e2e
```

`config/benchmarks/local-vulkan.example.toml` is the recommended copied configuration for a reviewed pilot. It uses the installed home-relative paths; verify those paths. The ordinary ingest/run CLI supports real WAVs and timestamped JSON, whereas the integration helper intentionally accepts **synthetic local Ollama only** and only exports to fixtures/generated/public.

Direct comparison:

```bash
uv run --project pipeline vet-pipeline --config config/benchmarks/qwen3-30b.toml benchmark \
  fixtures/pipeline/transcripts/01-first.json fixtures/pipeline/transcripts/02-followup.json \
  fixtures/pipeline/transcripts/03-workaround.json fixtures/pipeline/transcripts/04-medication.json \
  fixtures/pipeline/transcripts/05-continued.json fixtures/pipeline/transcripts/06-ambiguous.json \
  fixtures/pipeline/transcripts/07-known-outcome.json --output /PRIVATE/qwen-report.json
```

Use qwen35-9b.toml or gemma3-12b.toml for alternatives. Per-request overrides do not edit global model defaults. Keep Whisper/LLM sequential; the multi-file run reached 23.88 GB decimal whole-GPU usage. Do not assume another GPU process can safely coexist.

## Tests and remaining limitations

Latest Python regression count is **75** (52 prior + 23 new). TypeScript remains **16**; type/content checks pass. Real synthetic-data browser navigation/card/search tests pass on desktop/mobile. CI now also runs four generic pipeline-data tests on deterministic mock export; demo, empty-production and public-production suites remain intact. Final production build/audits and CI/push outcome should be verified in the session's final report.

Important open issues:

1. ASR can still corrupt drug names, negation or patient labels despite low overall synthetic WER. Real speech/noise/overlap is untested. No speaker diarization or reliable recorder clock/mount behavior has been validated.
2. Evidence labels and medical context are not fully reliable. Source accounts retain details, but this is not model-level 90% semantic capture. Structured typed-fact matching and question quality need adjudication.
3. Long recordings may need unclassified excerpts/review. Output splitting costs time and can fragment related discussions. Chunk checkpoints depend on transcript/config boundaries; use a fresh workspace when changing input limits/model configurations. Resume existing jobs with their original config.
4. Topic names remain uneven; exact/acronym matching is not full semantic consolidation. Append-only source notes protect knowledge but need curation as volume grows. Unrelated/uncertain cases remain deliberately separate; speaker/case ambiguity cannot be solved by guessing.
5. First real WAV must be mono 16 kHz PCM16 for this Vulkan adapter; convert a workspace copy if needed, preserving originals. Faster-Whisper fallback remains available. Do not assume actual recorder format.
6. No independent backup provider/key custody configured, no clinical third-party storage authorization, no USB monitoring/deletion activation. Private master remote synthetic-durability evidence remains valid but unchanged this session.

## Next steps in priority order

1. Review the human-readable selected-v2 reports and source errors before new experiments. Use Qwen3 provisionally for a **manually reviewed 5–15 minute authorized real pilot**, not unattended clinical publication. Qwen3.5 deserves comparison on that same material; its typed score/memory are promising but it generated no cards.
2. Establish recording/processing authorization. Use a new real-only private workspace. Write recollections before viewing AI output, then create a corrected human transcript/reference and approximate utterance annotations. Audio benchmark requires matching `origin="authorized-record"` plus `--authorization-ref`; recollection notes are not scored as WER. Real reports are forbidden inside the public repo. Nothing should be uploaded externally.
3. Inspect every medication, dose/unit, negation, uncertain diagnosis/outcome and case label. Preserve original ASR, put owner corrections in a separate reviewed reference; do not automatically rewrite plausible medical words. Evaluate actual source associations and useful questions, not just JSON validity or lexical scores.
4. Improve grouping/classification/topic retrieval using observed real failures. Budget the entire serialized wire request, not only source characters: the long parents used 7,055/6,415 prompt tokens plus a 4,096 output cap in an 8,192 window. They were rejected; accepted children fit. Consider shorter proactive chunks/source-count limits with a durable per-job chunk plan to avoid wasted oversized requests, but measure case-continuity effects before changing defaults. The two-level adaptive splitter is a bounded fallback, not a substitute for testing chunk sizes. A thinking-enabled compact-contract ablation may be useful later; only the previous **legacy** thinking attempt failed, so no compact thinking-quality claim is established.
5. Test the actual recorder's PCM/sample rate, mounts, file timestamps, voice-activation gaps and overnight grouping. Then benchmark representative hours/100+ files and library growth, rather than extrapolating these short repeated fixtures.
6. Configure an independently authorized encrypted backup provider, off-machine key custody and restoration before depending on the machine for clinical knowledge. Only afterward consider enabling the service/timer/retention with separate authorization. Originals are never automatically erased.

Do not restart MMM/FCC/Ollama, replace models/drivers/ROCm, enable services/deletion, publish test data, or introduce multi-agent review stages. All code is portable and the public website architecture is unchanged.
