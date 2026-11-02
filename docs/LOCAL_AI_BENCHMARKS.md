# Local AI installation and benchmark results — 2026-11-02

GPU transcription is now built and integrated. The existing Qwen3 runs locally on the GPU, but **the tested extraction settings are not ready for unattended clinical knowledge capture**. No real clinical data was processed. Production remains empty.

## Installed tools and model

All new tools are under `~/.local/share/vet-fieldnotes-ai`, outside both repositories. No system package, graphics driver, ROCm runtime, Ollama model configuration, MMM/FCC setting, service, or deletion policy was changed.

- whisper.cpp release **v1.9.5**, commit `d1be6fde11ac6e0407606b4e42fe72d34add8037`. It prints 1.9.5-dev internally despite the release tag.
- Executable: `~/.local/share/vet-fieldnotes-ai/whisper.cpp-v1.9.5/build-vulkan/bin/whisper-cli`. Keep its adjacent shared libraries.
- Build: GCC/G++ 15.2, Release, Ninja, `GGML_VULKAN=ON`, four build workers.
- Ubuntu packages were **downloaded and extracted locally**, without sudo or dpkg installation: cmake 4.2.3, cmake-data, ninja-build 1.13.2, glslc/libshaderc1 2026.1, libvulkan-dev 1.4.341, spirv-headers, libjsoncpp26, librhash1. Archives: `debs/`; extracted prefix: `toolchain/usr/`.
- GPU smoke model: `models/ggml-tiny.en.bin`, 77.7 MB (74.1 MiB), SHA256 `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`.
- **Large V3 f16 is not downloaded.** Its verified size is 3,095,033,483 bytes; authorization was requested and no reply had arrived at wrap-up. Do not infer approval from elapsed time. Qwen3.5/Gemma downloads and optional quantization comparisons were deferred under the user's budget instruction.
- Existing Ollama 0.34.0 and `qwen3:30b` are unchanged. Hardware remains Ryzen 7800X3D / 64 GB DDR5 / RX 7900 XTX 24 GiB / kernel 7.0.0-38-generic. About 1.7 TB disk space was free.

The local build uses the existing Mesa Vulkan runtime. Its development dependencies do not replace the installed runtime. [Official Vulkan build guidance](https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support).

## Measured transcription

The backend explicitly reported `whisper_backend_init_gpu: using Vulkan0 backend`; Vulkan enumeration identifies device 0 as the 7900 XTX. Dedicated GPU activity/VRAM increased while the integrated GPU stayed idle.

| Synthetic clip |    Audio | Wall time including CLI/model load | Real-time factor | Word error rate |
| -------------- | -------: | ---------------------------------: | ---------------: | --------------: |
| History        | 14.438 s |                            0.843 s |           0.0584 |           33.3% |
| Uncertainty    | 12.087 s |                            0.302 s |           0.0250 |           6.45% |

Peak sampled whole-GPU VRAM was 1.19 GB, including the desktop baseline. The half-second sampler can miss short peaks. These numbers measure **tiny.en**, not Large V3. They do not predict Large V3 speed or ER accuracy. Tiny misrecognized “grooming,” “obstruction,” and “peritonitis”; “infectious peritonitis” became “infectious paradise.” Do not use it for clinical processing.

The original history timestamp ended 0.122 seconds beyond the WAV duration. The adapter now bounds only trailing overruns of at most one second, preserves the original end in `transcriptionBackend.timestampAdjustments`, and rejects larger overruns or starts beyond the recording. The benchmark reports raw adjustments and bounded-offset checks. Ordered/in-bounds offsets are **not** proof of timestamp alignment accuracy; speech-boundary annotation remains to be done.

## Measured extraction and quality

Qwen3's service logs confirm **49/49 layers offloaded to ROCm0**, about 17,524 MiB weights and 768 MiB KV at the 8,192 context configuration. Peak sampled whole-GPU usage was about 20.98 GB decimal (19.54 GiB), with 97–99% busy samples. Models were not forcibly unloaded and MMM/FCC were not restarted.

With thinking disabled, representative detailed attempts took **14.68, 12.98, and 13.76 seconds** for the three fixture transcripts, including approximately 2.2 seconds of model loading per request. Generation was **132.7–135.5 tokens/second**. The third response was rejected. Speed is not useful capture accuracy.

Observed issues across attempts:

- Invalid identifiers, lowercased case keys that no longer matched evidence, unsupported quote spans, and references copied from retrieved records.
- Unknowns emitted as strings rather than null; owner reports confused with classroom observations.
- Separate FIP teaching attached to the wrong case/topic, unsourced explanatory claims, and an unsupported statement that no safety concerns applied.
- Missing case records and study questions, duplicate article topics, and copied prior article text instead of a useful addition.
- A final schema-grounded run was structurally accepted for all three inputs, but **the first returned completely empty arrays, and none created articles or questions**. This is a failed completeness result, not a successful benchmark.
- One request with thinking enabled, 12,288 context and 6,144 output-token limit, failed JSON decoding after 49.7 seconds. It does not establish that thinking is worse; the initial diagnostic did not retain the malformed response/token metrics. Benchmark failures now retain raw output and provider timing when available.

The prompt/schema now constrain slug IDs, state exact-case evidence/null/uncertainty rules, forbid copying prior records as current evidence, and include the extraction schema in the actual model prompt as well as the decoder's `format`. Ollama recommends this grounding step. It still needs quality work and model comparison. [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

The benchmark preserves output, timing and rejection reasons even for rejected structured responses. Lexical screening remains only a review aid. No useful-capture percentage is claimed.

## Full pipeline and interruption drill

Generated three local WAVs from the existing synthetic transcript fixtures (30.466, 21.952 and 10.824 seconds). They cover the returning case, unrelated FIP teaching, pump instructions, and the unverified classroom workaround.

The real path ran WAV import → Vulkan tiny.en → real Qwen3 → structured validation → private library projection. Two files completed; the process was deliberately interrupted with SIGINT during the third file's extraction. A fresh CLI invocation resumed that file without retranscribing. All seven pre-existing checkpoint hashes and both successful jobs remained unchanged. The model failed quote/reference validation on three bounded attempts, so the remaining job stays visibly failed at extraction. This is an unresolved model-output failure, not a successful complete-shift test.

The partial successful output exported **only to the ignored pipeline-demo dataset** and built successfully: 1 article, 4 discussions, 1 shift, 0 cases, 0 questions; 14 HTML pages and 178 internal links/anchors validated. A separate transcript-only run saved six discussions/two articles but missed all case/study records and included bad associations. Neither is suitable public medical content. The final local build was switched back to empty production.

## Overnight capacity

A reliable Large V3/clinical-quality estimate is **not established**. For scale only: the representative attempted extraction above used 41.42 seconds for text corresponding to 63.24 seconds of generated speech. Combining that ratio with the tiny smoke RTF gives roughly 0.70 processing hours per recorded hour: about **2.8 / 5.6 / 8.4 hours for 4 / 8 / 12 speech hours**, before additional retry and workload variation. This arithmetic includes failed/poor extraction, combines small different synthetic samples, and uses the wrong transcription model for the eventual target. It is not accepted overnight capacity.

Benchmark longer 5–15 minute passages, silence/noise, several files, and all required outputs with Large V3 before making an overnight claim. Measure total wall time, model loads, chunk counts, output tokens, retries and retrieval separately; 100 voice-activated files add startup cost. Keep Whisper and extraction sequential on this shared GPU. An eight-hour sleep window may be plausible, but has not been demonstrated.

## Repeat and resume

Run from `/home/quinten/vet-knowledge-library`. Full private reports, audio and workspaces are under:

```
/home/quinten/.local/share/vet-fieldnotes-validation/local-ai-20261102/
```

Important files: `tiny-vulkan.json`, `qwen3-30b*.json`, `text-workspace/`, `wav-workspace/`, `interruption-checkpoints.json`, `local-tiny.toml`, `wav-resume.log`, `wav-final-retry.log`, and build/test logs. Do not commit these directories or upload future real equivalents.

```bash
# Check other workloads first; do not unload another application's models.
curl -s http://127.0.0.1:11434/api/ps
cat /sys/class/drm/card1/device/gpu_busy_percent

# Use a NEW output directory for each generated corpus.
uv run --project pipeline python scripts/generate-benchmark-audio.py \
  --corpus pipeline --output /PRIVATE/new-audio

uv run --project pipeline python scripts/benchmark-transcription.py \
  --manifest /PRIVATE/new-audio/manifest.json --backend whisper-cpp \
  --executable /ABSOLUTE/build-vulkan/bin/whisper-cli \
  --model /ABSOLUTE/ggml-large-v3.bin --output /PRIVATE/audio-report.json

uv run --project pipeline vet-pipeline --config config/benchmarks/qwen3-30b.toml \
  benchmark fixtures/pipeline/transcripts/01-first.json \
  fixtures/pipeline/transcripts/02-followup.json \
  fixtures/pipeline/transcripts/03-workaround.json --output /PRIVATE/qwen-report.json
```

Copy `config/benchmarks/local-vulkan.example.toml` outside Git, replace executable/model paths, then use normal `ingest` and `run` commands. The adapter requires mono PCM16 WAV at 16 kHz; convert only a local workspace copy when needed, keeping originals. Default Faster-Whisper remains available. The pipeline does not download models automatically.

## First authorized real-audio workflow

1. Establish recording/processing authorization. Keep audio, transcript and benchmark reports outside both repositories; choose a fresh real-only workspace. Local inference does not authorize remote storage or publication.
2. Start with 5–15 minutes, not a shift. Make notes from recollection before inspecting AI output. Include uncertain diagnoses/outcomes and equipment terminology.
3. A real benchmark manifest uses `origin: "authorized-record"`, `recordings: [{id, file, reference?, referenceKind?, terminology: []}]`. Paths resolve relative to the manifest. Use `referenceKind: "recollection"` for memory notes; it intentionally receives **no WER score**. Only a corrected verbatim `referenceKind: "human-transcript"` supports WER.
4. Run the transcription command above with `--origin authorized-record --authorization-ref YOUR_LOCAL_PERMISSION_REFERENCE`. Nothing is sent to a cloud inference provider. Inspect word substitutions, speaker ambiguity and timestamp alignment manually; annotate reference boundaries before claiming timestamp accuracy.
5. Run extraction benchmark with its corresponding origin/reference flags. Compare source facts, missing details, inventions, classifications, case links, additions and study answers. Keep deterministic source validation strict; do not approve a response just to make the pipeline finish.
6. Leave USB monitoring, deletion, real publication and clinical cloud storage disabled. Connect/test an independent encrypted backup before relying on the machine for long-term records.
