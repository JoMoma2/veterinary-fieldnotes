# Operational readiness — 2026-11-02

| Area | Verified state | Remaining prerequisite |
|---|---|---|
| Public website | https://veterinary-fieldnotes.pages.dev — native Git build and automatic push deployment succeeded | Desktop/mobile public audits passed |
| Production data | Empty: zero articles, cases, shifts, discussions, or questions; demo data lives in separate fixtures | Actual content requires authorization and content-bound privacy review |
| Git deployment settings | Public `JoMoma2/veterinary-fieldnotes`, production `main`, Node 24, `LIBRARY_DATASET=production`, `dist`, automatic production deployments enabled | Branch previews are deliberately disabled |
| Private master synchronization | Real synthetic GitHub push, interrupted-push retry, local archive deletion repair, and fresh-clone recovery passed | Clinical cloud storage remains disabled pending separate authorization |
| Recovery | Replacement workspace rebuilt knowledge, recording hashes, and case continuity from GitHub without using the source workspace | Retain GitHub account access; independent provider is still needed |
| Independent encrypted backup | Encryption/integrity and local backup restoration passed | No rclone remote/provider authentication is configured; the test key is local and is not disaster-proof key custody |
| Hardware | Ryzen 7 7800X3D, 8 cores/16 threads; RX 7900 XTX 24 GiB; owner-confirmed 64 GB DDR5; Ubuntu 26.04.1, kernel 7.0.0-38-generic | No driver/kernel/SDK changes required for the working Ollama probe |
| Local inference | Ollama 0.34.0 GPU acceleration confirmed: ROCm0, 29/29 layers, full VRAM residency in a short synthetic probe | Clinical extraction quality has not been benchmarked |
| ROCm | Bundled Ollama ROCm 7.2 libraries work; no system HIP development SDK found | Do not replace them to install transcription tooling |
| Transcription candidates | whisper.cpp Large V3 f16 with existing Vulkan stack first; HIP/gfx1100 and q5_0 comparisons later; Faster-Whisper CPU fallback | No whisper.cpp binary/compiler toolchain/Large V3 model is installed; an isolated build/acquisition needs approval |
| Extraction candidates | Existing Qwen3 30B Q4 baseline; Qwen3.5 9B Q4 and Gemma3 12B Q4 for comparison | No new models downloaded or selected; run comparisons when MMM/FCC are idle |
| Benchmarks | Sequential extraction/retrieval/update benchmark, quality-review screens, prompt/config identity, hardware sampling; synthetic audio WER/RTF/timestamp benchmark prepared | Real authorized conversations and recordings are needed for clinical capture/terminology/throughput evaluation |
| USB and retention | Service remains uninstalled/disabled; automatic recording deletion remains disabled | Real recorder, mount/file/clock tests, full-shift trials, independent recovery/key checks |

## Evidence

- `docs/validation/remote-durability.json`: synthetic-only GitHub synchronization and loss/recovery drill; private remote commit included for reproducibility.
- `docs/validation/hardware.json`: read-only hardware and installed-model inventory, without credentials or private configuration.
- `docs/AI_ENVIRONMENT.md`: detailed compatibility diagnosis, MMM/FCC dependency findings, candidate rationale, and benchmark commands.
- Verified public deployment: `docs/validation/deployment.json` records the automatic `github:push` deployment and empty production counts.
- Browser suite: `E2E_PUBLIC=1 E2E_BASE_URL=https://veterinary-fieldnotes.pages.dev npm run test:e2e`; covers desktop/mobile, empty sections, Pagefind results/no matches, and inaccessible private paths.

## Before the first real recording

1. Establish recording/processing authorization and separate permissions for remote inference, private cloud storage, and public publication. A successful synthetic drill does not grant those rights.
2. Benchmark real-model extraction and transcription on representative, authorized material. Check omissions, invented details, clinical terminology, uncertainty labels, case links, and additive updates; lexical scores alone are insufficient.
3. Acquire/build the chosen transcription backend in an isolated project location; keep current GPU drivers, ROCm/Ollama, and MMM/FCC settings intact unless separately approved.
4. Test recorder WAV format, mount detection, voice-activation gaps, clock metadata, and overnight/multiple-shift grouping. Measure a full shift on this hardware.
5. Connect a separately authorized independent backup provider and retain a recoverable key copy off this computer. Test remote retrieval and restoration.
6. Only after those checks, consider enabling the timer and guarded workspace retention. Recorder originals are never automatically erased.

Cloudflare agent setup was completed from its official prompt: 19 Cloudflare skills installed in `~/.agents/skills`, Codex MCP registered in `~/.codex/config.toml` and OAuth authenticated, existing project Wrangler retained and pinned locally. Restart/new agent initialization loads the newly registered MCP tools. The optional beta `cf` CLI was not installed because this project already uses Wrangler.
