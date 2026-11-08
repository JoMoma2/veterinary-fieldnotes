# AI environment diagnosis — 2026-11-02

**Verified model-variant update (2026-11-07):** `/api/show` for local `qwen3:30b` reports general.finetune=Thinking, general.version=2507, size30B-A3B, Q4_K_M, and context_length262144. The alias is the thinking-only2507variant, not the original switchable Qwen3 described by older assumptions. Its unconditional thinking prefix is expected; requesting thinking=false is not a validated inference mode. The isolated whole-night experiment uses native thinking output plus the author's sampling guidance, without changing the alias/template or global service. A synthetic81920-context/40-GPU-layer allocation probe returned structured unknown association,4.78s, peak22130MiB GPU; actual report metrics are measured per real request. See WHOLE_SHIFT_CONTEXT.md.

**Current update (resumed session):** Large V3 f16 is installed and benchmarked on the existing Vulkan backend. Qwen3.5 9B and Gemma3 12B are installed alongside unchanged Qwen3. Compact grounded-v2 extraction, full synthetic WAV processing and bounded long-recording recovery now work. Clinical readiness is not established. Read [LOCAL_AI_BENCHMARKS.md](LOCAL_AI_BENCHMARKS.md) and [SESSION_HANDOFF.md](SESSION_HANDOFF.md) for current results. The diagnostic snapshot below predates these installations; no system driver/ROCm/Ollama/MMM/FCC configuration was replaced.

These were diagnostics and project-local benchmark preparations. No GPU drivers, kernel packages, ROCm installations, Ollama service configuration, installed models, or MMM/FCC configuration were changed. No large model was downloaded. One existing small model generated one synthetic diagnostic token; it expired normally afterward.

## Confirmed hardware and runtime

| Item                            | Observation                                                                              |
| ------------------------------- | ---------------------------------------------------------------------------------------- |
| CPU                             | AMD Ryzen 7 7800X3D, 8 cores / 16 threads                                                |
| OS                              | Ubuntu 26.04.1 LTS, Resolute Raccoon                                                     |
| Running kernel                  | `7.0.0-38-generic`                                                                       |
| RAM                             | 64 GB DDR5 owner-confirmed; Linux exposes about 60 GiB usable                            |
| Dedicated GPU                   | AMD Radeon RX 7900 XTX, Navi 31 / gfx1100, 24 GiB VRAM                                   |
| Other graphics                  | Ryzen integrated graphics; do not select it for transcription                            |
| Graphics driver                 | Kernel `amdgpu`, Mesa RADV 26.0.8; Vulkan device enumeration succeeds                    |
| Vulkan                          | Loader 1.4.341, dedicated GPU API 1.4.335                                                |
| Ollama                          | Client/server 0.34.0, active system service as user `ollama`, loopback `127.0.0.1:11434` |
| ROCm SDK                        | No `/opt/rocm`, `hipcc`, `rocminfo`, `rocm-smi`, or system ROCm packages found           |
| Bundled inference runtime       | Ollama includes ROCm 7.2.70201 HIP/HSA/BLAS libraries and a Vulkan backend               |
| whisper.cpp/build prerequisites | No whisper.cpp executable, CMake, Ninja, GLSL compiler, or HIP development SDK detected  |

AMD's current ROCm 10.1 matrix supports Ubuntu 26.04.1 GA kernel 7.0 and gfx1100. That establishes a supported potential SDK installation; it does **not** mean ROCm 10.1 is installed here, or that the working bundled runtime must be replaced. [AMD compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html).

## GPU acceleration: measured, not inferred

Before the probe, Ollama `/api/ps` was empty. An existing `llama3.2:latest` model received a one-token synthetic request with a 2,048-token context and 15-second keep-alive. It completed in about 1.37 seconds including model load. `/api/ps` reported `size == size_vram == 2,317,730,446` bytes. Service logs explicitly recorded ROCm0 as the 7900 XTX and **29/29 layers offloaded to GPU**. After normal expiration `/api/ps` was empty again.

Historical service logs also show Qwen3 30B offloaded **49/49 layers**, about 17,524 MiB of model buffers plus roughly 3,072 MiB KV cache for the historical configuration. This supports existing GPU compatibility, not a veterinary accuracy or current throughput claim. No service restart, backend switch, forced unload, or global environment override was used.

## Existing Ollama inventory

| Tag                | Parameters / quantization  | Stored size (decimal GB) | Role                                                               |
| ------------------ | -------------------------- | -----------------------: | ------------------------------------------------------------------ |
| `qwen3:30b`        | 30.5B MoE, Q4_K_M          |                    18.56 | Existing capable benchmark baseline; explicitly used by MMM source |
| `llama3:latest`    | 8B, Q4_0                   |                     4.66 | Existing legacy comparison                                         |
| `llama2:7b`        | 7B, Q4_0                   |                     3.83 | Legacy; do not select as the clinical default                      |
| `llama2:latest`    | Same digest as `llama2:7b` |                    Alias | Not a second independent model                                     |
| `phi3:mini`        | 3.8B, Q4_0                 |                     2.18 | Small legacy comparison                                            |
| `llama3.2:latest`  | 3.2B, Q4_K_M               |                     2.02 | Small compatibility probe, not a clinical selection                |
| `tinyllama:latest` | 1B, Q4_0                   |                     0.64 | Mechanical testing only                                            |

Seven tags represent six distinct model digests. Qwen3's stored defaults include temperature 0.6, top-p 0.95, top-k 20. Its advertised trained context is 262,144 tokens; that is not a safe memory budget for this workstation. Benchmark configs explicitly request 8,192 context tokens and bounded output. Model defaults and service settings remain unchanged. Full digests and read-only hardware inventory are in `docs/validation/hardware.json`.

## MMM and FCC compatibility

- MMM's launcher describes Ollama as its final fallback. Active inference code contains explicit Qwen3 30B planner/review handling and a localhost Ollama provider. Removing/changing Ollama or `qwen3:30b` can affect MMM. No running MMM `automaton/dist/index.js` process was found at the inspection time; this does not remove that configuration dependency.
- FCC is actively listening on loopback port 8082. Its current configured default model aliases route to external providers. Its code also supports the local Ollama endpoint. This establishes potential shared use, rather than evidence that FCC is currently performing local inference.
- The existing FCC processes have a working directory under a moved/Trash copy of the FCC-Testing folder. The current `~/FCC-Testing` directory is empty. No process was restarted or path repaired; verify the intended launch directory separately before future FCC maintenance.
- Do not modify MMM/FCC files, API credentials, provider routes, service defaults, or model tags for Fieldnotes experiments. Run experiments sequentially, check active models first, and do not force-unload another application's model.

## Recommended transcription comparison

1. **whisper.cpp Vulkan + Whisper Large V3 f16** is the first stability-oriented GPU candidate: the existing Mesa RADV stack already recognizes the correct GPU, and this route avoids installing or replacing ROCm.
2. **whisper.cpp HIP/ROCm + Large V3 f16**, targeted at `gfx1100`, is a useful comparison after an isolated SDK/build environment is explicitly approved. The existing bundled Ollama libraries are a runtime, not a complete development SDK.
3. Compare **Large V3 q5_0** with f16 for memory and terminology tradeoffs; do not assume quantization preserves every clinical term.
4. Keep the existing **Faster-Whisper CPU int8** adapter as a fallback/reference. Its installed prebuilt CTranslate2 package does not establish AMD GPU acceleration. A custom HIP build would be a separate maintenance commitment.

The whisper.cpp documentation lists large-model weights around 2.9 GiB and memory around 3.9 GB; actual GPU working memory and decoding settings must be measured. Avoid simultaneous Large V3 and Qwen3 30B loads until measured headroom supports them. [Official whisper.cpp backend/build guidance](https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support), [CTranslate2 prebuilt hardware support](https://opennmt.net/CTranslate2/hardware_support.html).

No installation/build commands were executed. A later isolated build can use `-DGGML_VULKAN=1`, or `-DGGML_HIP=1 -DAMDGPU_TARGETS=gfx1100`, with a pinned whisper.cpp revision and deliberately selected development dependencies. Do not replace the global Ollama runtime to build Whisper.

## Recommended extraction comparison

- **Qwen3 30B Q4_K_M:** existing baseline with demonstrated full GPU offload. Do not assume it wins quality or latency.
- **Qwen3.5 9B Q4_K_M:** newer, smaller candidate (~6.6 GB download) with substantial memory headroom; not installed or downloaded.
- **Gemma 3 12B Q4_K_M:** a different model family for a useful quality comparison; not installed or downloaded.
- Consider Qwen3.5 27B Q4 only if the first comparisons justify the larger memory/load cost. Avoid 35B-plus models as a first experiment on this shared 24 GiB GPU.

These are candidate fits, not clinical-quality endorsements. See [Qwen3.5 tags](https://ollama.com/library/qwen3.5/tags), [Gemma 3 tags](https://ollama.com/library/gemma3/tags). Current download sizes and runtime requirements must be rechecked before installation.

## Repeatable project benchmarks

`config/benchmarks/*.toml` contains per-request extraction settings: loopback only, no paid API calls, bounded context/output/time, sequential input processing, and keep-alive zero. This does not rewrite another application's defaults.

```bash
uv run --project pipeline vet-pipeline --config config/benchmarks/qwen3-30b.toml benchmark \
  fixtures/pipeline/transcripts/01-first.json \
  fixtures/pipeline/transcripts/02-followup.json \
  fixtures/pipeline/transcripts/03-workaround.json \
  --output /PRIVATE/qwen3-30b-benchmark.json
```

This real-model run is **prepared, not executed**. The benchmark records model digest inventory, prompt-contract hash, per-request generation settings, elapsed time, Ollama token/load timing, host CPU/RAM/GPU samples, exact-source validation, terminology/unknown-state screens, targeted retrieval, case count, and preservation of earlier article content. It retains human review fields for semantic completeness, invented details, terminology, linking, and update quality. Copied quotes are excluded from completeness screening. Lexical screens are not certified accuracy scores.

The corpus generator emits mono 16-bit PCM at 16 kHz for whisper.cpp compatibility. Its resampling is limited to generated test speech; recorder media is never modified. Synthetic audio generation and transcription comparison are independent of the nightly service:

```bash
uv run --project pipeline python scripts/generate-benchmark-audio.py --output /PRIVATE/new-synthetic-audio
uv run --project pipeline --extra audio python scripts/benchmark-transcription.py \
  --manifest /PRIVATE/new-synthetic-audio/manifest.json --backend faster-whisper \
  --model tiny.en --threads 2 --output /PRIVATE/tiny-baseline.json
# After an approved local whisper.cpp build and model acquisition:
uv run --project pipeline python scripts/benchmark-transcription.py \
  --manifest /PRIVATE/new-synthetic-audio/manifest.json --backend whisper-cpp \
  --executable /PATH/whisper-cli --model /PATH/ggml-large-v3.bin \
  --threads 4 --output /PRIVATE/large-v3-vulkan.json
```

The cached tiny.en mechanical run completed both synthetic clips, with WER approximately 0.389 and 0.129. Those errors reinforce that it is not a selected medical model. Generated speech is not noisy ER speech; no real-world capture target or 12-hour throughput is established. `config/benchmarks/transcription-plan.json` records the unexecuted Large V3 comparisons.
