# Session continuation — local AI, 2026-11-02

## Start here

User requested actual local GPU transcription/extraction benchmarks, then explicitly narrowed this session to essential progress and a reliable handoff because of the remaining token budget. Continue the existing architecture. Do not redesign or add review agents. No paid inference. Read AGENTS.md and LOCAL_AI_BENCHMARKS.md; the earlier AI_ENVIRONMENT.md diagnostic snapshot is historical.

The public website is https://veterinary-fieldnotes.pages.dev, native public GitHub deployment, production main. Keep it empty of clinical information and synthetic records. Public app: `/home/quinten/vet-knowledge-library` → `JoMoma2/veterinary-fieldnotes`. Existing private master: `/home/quinten/vet-knowledge-master` → `JoMoma2/veterinary-fieldnotes-master`; **it was not modified in this local AI session**. Earlier synthetic remote-durability tests remain intact. Do not upload these new workspaces or real data by default. Independent cloud backup/rclone remains unconfigured.

## Completed / working

- Read required handoff docs; checked GPU idle and no loaded Ollama models before expensive work.
- Preserved working AMD/Mesa/ROCm/Ollama, installed model tags and all MMM/FCC configurations. FCC remains active. MMM explicitly depends on Qwen3; do not remove/replace it.
- Built whisper.cpp Vulkan using locally extracted development tools, without root package installation.
- Confirmed actual Vulkan0 inference on RX 7900 XTX with tiny.en; measured wall time, WER, GPU samples and timestamp overrun.
- Integrated `whisper-cpp` into the durable transcription stage. Existing Faster-Whisper remains default/fallback. Paths/threads/device/timeouts configurable; no model auto-download.
- Added timestamp padding bounds with audit metadata and strict errors for larger overruns. Adapter requires mono 16 kHz PCM16 WAV.
- Ran actual Qwen3 30B extraction benchmarks on all three fixture transcripts, including retrieval, additive-update and conservative case rules. GPU offload confirmed in Ollama journal; measured ~133 generated tokens/s in detailed attempts. Clinical extraction **quality is insufficient**, despite mechanical execution.
- Improved slug schema/prompt rules and included the extraction schema in actual prompt content. Added diagnostics retention for invalid structured/JSON responses. Do not weaken evidence validation to make results pass.
- Generated WAV corpus from existing synthetic fixture texts (`--corpus pipeline`). Ran real WAV→Vulkan→Qwen→private structured output. Two of three files completed; four saved discussions/one article build in the test website.
- Deliberately SIGINT-interrupted our own CLI while the third file extracted. Resumed without retranscription; both prior successes and all seven checkpoint hashes were unchanged. After bounded retries, third file remains failed rather than committing unsupported references.
- Added authorized real-audio manifest support: explicit origin + permission reference; recollection notes are not scored as verbatim WER.
- Restored final `dist` to empty production; no synthetic production content, recorder service, or deletion policy enabled.

## Installation / paths

```
AI root: /home/quinten/.local/share/vet-fieldnotes-ai
source:  AI root/whisper.cpp-v1.9.5
binary:  source/build-vulkan/bin/whisper-cli
models:  AI root/models/ggml-tiny.en.bin
packages: AI root/debs/*.deb
toolchain: AI root/toolchain/usr
private trial root: /home/quinten/.local/share/vet-fieldnotes-validation/local-ai-20261102
```

Pinned whisper.cpp v1.9.5 commit: `d1be6fde11ac6e0407606b4e42fe72d34add8037`. The binary reports 1.9.5-dev internally. GCC 15.2 already existed. CMake 4.2.3, Ninja 1.13.2, glslc/libshaderc1 2026.1, Vulkan development headers 1.4.341, SPIRV headers, libjsoncpp26/librhash1 were extracted from Ubuntu packages under the prefix, never installed globally. About 21.4 MB package downloads. No sudo password available; local extraction avoided needing one.

Rebuild with scoped environment (not global shell/service configuration):

```bash
AI_ROOT="$HOME/.local/share/vet-fieldnotes-ai"
env PATH="$AI_ROOT/toolchain/usr/bin:/usr/bin:/bin" \
  LD_LIBRARY_PATH="$AI_ROOT/toolchain/usr/lib/x86_64-linux-gnu" \
  cmake --build "$AI_ROOT/whisper.cpp-v1.9.5/build-vulkan" --target whisper-cli -j 4
```

Initial configure used `-G Ninja -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF`, `-DCMAKE_PREFIX_PATH=<toolchain>/usr`, `-DVulkan_INCLUDE_DIR=<toolchain>/usr/include`, `-DVulkan_LIBRARY=/usr/lib/x86_64-linux-gnu/libvulkan.so.1`.

Tiny model SHA256: `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`. Downloaded from the official ggerganov whisper.cpp Hugging Face repository, pinned revision `5359861c739e955e79d9a303bcbc70fb988958b1`. **Tiny is only an integration smoke model**, not a medical model.

## Unfinished / blockers / important failures

1. Large V3 f16 download is pending authorization. An async question asked whether to download 3.1 GB, versus defer. No reply had arrived at wrap-up; do not treat elapsed time as approval. New extraction model downloads were deferred per token-budget instruction.
2. Qwen3 results have substantial omissions, wrong attribution, case/topic confusion, bad references and missing study records. Initial invalid IDs and case-key casing errors were caught; later prompt/schema grounding still did not solve quality. Final non-thinking benchmark's first response was all empty arrays. A structurally valid benchmark is **not a quality pass**.
3. One thinking-enabled request failed JSON decoding after 49.725 seconds (12,288 context, 6,144 output tokens). That old failure did not preserve raw text/metrics; the diagnostic retention code was improved afterward. Do not assume the exact failure cause. The temporary thinking config exists outside Git only.
4. WAV job `r-d646e02ab3dab9de08f42f85` in `wav-workspace` is at `extract`, attempts=3. Rejections: source quote/offset mismatch on attempts 1/2; unknown discussion reference on attempt 3. Its transcript and input are retained. Earlier successful jobs: `r-ec44379c4b553d4040ba1205` and `r-51d74c759bf79ba375a5eff1`. Do not reset/retry indefinitely without addressing the cause.
5. Actual timestamp alignment and veterinary accuracy remain unvalidated. A 0.122 s padded timestamp overrun was found and bounded. An in-bounds timestamp is not alignment accuracy.
6. No Large V3 or high-quality full-shift throughput measurement; overnight capability remains unproven. See report for explicitly limited arithmetic illustration.
7. No new models, paid calls, real data, USB monitoring, deletion, drivers or global config changes. No independent backup-provider credentials configured.

## Results and artifacts

Private trial root contains:

- `audio/manifest.json`: two basic espeak-ng clips; `pipeline-audio/manifest.json`: three fixture-derived WAVs.
- `tiny-vulkan.json`: actual GPU transcription output/resources; 14.438 s in 0.843 s (WER 33.3%), 12.087 s in 0.302 s (WER 6.45%). Max sampled whole-GPU VRAM 1.19 GB; includes desktop baseline.
- `qwen3-30b.json`, `qwen3-30b-contract-v2.json`, `qwen3-30b-contract-v3.json`, `qwen3-30b-final.json`: ordered exploratory prompt revisions. Do not combine them as a single identical-instruction accuracy score. Final schema-in-prompt benchmark predates the new report hash salt/metadata field; its request used schema grounding, but that file's hash follows the older metadata algorithm.
- `qwen3-30b-thinking.json`, `qwen-thinking.toml`: failed one-input probe; not a recommended preset.
- `text-workspace/`: six discussions/two articles, no cases/questions, bad associations; do not publish.
- `wav-workspace/`: two completed jobs/one failed at retry bound, four discussions/one article, no case/question records.
- `interruption-checkpoints.json`, `wav-resume.log`, `wav-retry.log`, `wav-final-retry.log`: recovery evidence.
- `local-tiny.toml`: tested local backend paths + request-only Qwen settings.
- `whisper-build.log`, `text-website-build.log`, `wav-website-build.log`, `production-build.log`, `production-browser.log`.

Only sanitized synthetic metrics are committed in `docs/validation/local-ai.json`. Full reports, models, WAVs and private workspaces are excluded. Ignored `fixtures/generated/public` currently contains the partial WAV test export. Final `dist/build-info.json` says production, all medical record counts zero.

## Tests performed

- **52 Python tests pass** (prior 46 plus six new cases); subprocess adapter, timeout checkpoint preservation, bounded timestamp overrun, authorization gates, schema grounding and rejected-response diagnostics covered.
- **16 TypeScript tests pass**, Astro checks 0 errors/warnings, production content validation empty.
- Test exports build: transcript-only 17 pages/233 links; partial WAV 14 pages/178 links. These prove display/schema compatibility, not extraction completeness.
- Final production build: **8 pages/87 links**, no private sentinels, source maps or audio; medical counts zero.
- **4 desktop/mobile production browser audits pass**, including search and empty states.
- Real tiny Vulkan inference, real Qwen3 inference and actual CLI interruption/recovery executed. Full three-file WAV semantic/structural acceptance **did not pass**.

Commands from application checkout:

```bash
uv run --project pipeline pytest pipeline/tests -q
./scripts/local-node.sh run check
./scripts/local-node.sh test
LIBRARY_DATASET=production ./scripts/local-node.sh run build
E2E_PUBLIC=1 ./scripts/local-node.sh run test:e2e
```

## Exact next steps, in priority order

1. Read any reply to the pending 3.1 GB question. If authorization arrives, download **only Large V3 f16** into the isolated models directory. Use official pinned URL, a temporary `.part` file, checksum verification and atomic rename. Expected file size 3,095,033,483 bytes and SHA256 `64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2` from Hugging Face LFS metadata. Recheck metadata if using a different revision.

```bash
# Only after authorization. Stop on error; no driver/ROCm changes.
set -e
MODEL_ROOT="$HOME/.local/share/vet-fieldnotes-ai/models"
curl --fail --location --retry 2 --output "$MODEL_ROOT/ggml-large-v3.bin.part" \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/ggml-large-v3.bin
printf '%s  %s\n' 64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2 \
  "$MODEL_ROOT/ggml-large-v3.bin.part" | sha256sum --check
mv "$MODEL_ROOT/ggml-large-v3.bin.part" "$MODEL_ROOT/ggml-large-v3.bin"
```

2. Check `/api/ps` and GPU usage; defer heavy work when MMM/FCC use the GPU. Do not stop them or force-unload their models. Run Large V3 benchmark on existing `audio/manifest.json`, then the pipeline corpus; command in LOCAL_AI_BENCHMARKS.md. Record dedicated GPU evidence, full load/wall/RTF/resources, terminology errors and timestamp adjustments. Replace the tiny path in a **copied** local TOML, preserving its historical config.
3. Improve/compare extraction on fixed transcripts before trusting audio notes. Inspect raw rejected outputs and distinguish omissions, invalid schema, ungrounded quotes, bad topic associations and bad study answers. The model sees both schema and contextual memory now, but can still copy context. Consider a compact, clearly separated prompt/grounded examples rather than adding many more overlapping paragraphs. Keep exact evidence checks and conservative case linking. Test the current input first with no retrieved context, then with context, to isolate contamination. Do not mistake keyword hits for semantic accuracy.
4. If budget/authorization allows, verify availability/size and compare Qwen3.5 9B Q4_K_M and Gemma3 12B Q4_K_M with identical final instructions. Existing configs are prepared, not downloaded. Do not alter existing model defaults or assume a larger model wins.
5. Repeat full WAV pipeline in a fresh synthetic workspace. Require six detailed discussions, correct related-case continuity, additive existing-topic update, useful valid questions, preserved uncertainty and faithful equipment/workaround content. Test interruption again. Synthetic export goes only to `fixtures/generated/public`; build with `LIBRARY_DATASET=pipeline-demo`, then restore production.
6. To retry the existing failed job after fixing its cause: `uv run --project pipeline vet-pipeline --workspace <trial-root>/wav-workspace retry r-d646e02ab3dab9de08f42f85`, then `... --config <new-config> run`. Successful earlier files should remain untouched. For model comparisons prefer a fresh workspace; old checkpoints intentionally retain old outputs.
7. Benchmark longer representative workloads and derive 4/8/12 recorded-hour estimates including startup, retrieval, token counts and bounded failures. Do not extrapolate tiny throughput to Large V3.
8. First authorized real benchmark: 5–15 minutes, local-only fresh real workspace, explicit permission reference. Capture recollections first, then correct a verbatim reference for WER and mark timing boundaries. The manifest/CLI support this without application edits. Recollection alone is not a word-accurate reference. Review all claims/case links before any publication.
9. Independent encrypted backup provider/key custody and actual recorder format/mount/clock checks still precede unattended services or deletion. Do not enable them during benchmarking.

## Clean stopping / source control

Changes are application code, synthetic test support and documentation only. No private-master modification is necessary. Push the public app commit; its native Pages build uses production. Keep all heavy/private artifacts outside Git. Verify `git status`, CI and production build metadata after pushing. All owned benchmark/preview processes should finish before stopping; leave Ollama/FCC services alone. The final user report should provide the resulting commit and any remaining deployment/check issue.
