# Local AI results — resumed development, 2026-11-02

**The complete local processing path now works on synthetic WAVs. It is not ready for unattended clinical use.** Large V3 substantially improves transcription, and source-grounded extraction prevents several previous failure modes. Classification, grouping, topic naming, ASR drug/case-name errors, and long-recording quality still need real-world evaluation.

No real clinical material, paid inference, driver/runtime/service changes, USB activation, or automatic deletion occurred. MMM/FCC and existing Ollama defaults were preserved. Previous-session results remain in `validation/local-ai.json`; current sanitized evidence is in [validation/local-ai-r2.json](validation/local-ai-r2.json).

## Installed and verified

| Component                    | Installed configuration                                                                                              |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Transcription                | Existing isolated whisper.cpp v1.9.5, Vulkan0 on RX 7900 XTX                                                         |
| Strong transcription weights | Whisper Large V3 f16, 3,095,033,483 bytes; SHA256 `64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2` |
| Previous smoke weights       | tiny.en f16 retained; not recommended clinically                                                                     |
| Extraction baseline          | Existing `qwen3:30b`, Q4_K_M, unchanged                                                                              |
| New alternatives             | `qwen3.5:9b-q4_K_M` (6.55 GB installed), `gemma3:12b-it-q4_K_M` (8.16 GB installed)                                  |
| Dependencies                 | Existing user-local build/Python tools reused; no additional system installation                                     |

Large weights live in `~/.local/share/vet-fieldnotes-ai/models/`. The executable remains `~/.local/share/vet-fieldnotes-ai/whisper.cpp-v1.9.5/build-vulkan/bin/whisper-cli`, pinned commit `d1be6fde11ac6e0407606b4e42fe72d34add8037`. Its internal version string says 1.9.5-dev. Model checksum was verified before atomic rename. [Official weight repository](https://huggingface.co/ggerganov/whisper.cpp/tree/5359861c739e955e79d9a303bcbc70fb988958b1), [Vulkan backend guidance](https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support).

All three extraction models ran on Ollama 0.34.0. Free-model availability/sizes were checked before acquisition. [Qwen3.5 tag](https://ollama.com/library/qwen3.5:9b-q4_K_M), [Gemma tag](https://ollama.com/library/gemma3:12b-it-q4_K_M).

## Transcription: measured accuracy and speed

Six generated recordings total **166.62 seconds / 420 reference words**. They include clinical uncertainty, contradictory histories, equipment instructions, drugs, abbreviations and an unconventional classroom prop. Synthetic espeak-ng speech is substantially easier and less varied than actual overlapping/noisy ER conversation.

| Model                 | Total wall time including per-file load | Weighted normalized WER | Real-time factor |
| --------------------- | --------------------------------------: | ----------------------: | ---------------: |
| Large V3 f16 / Vulkan |                                 12.77 s |       3/420 = **0.71%** |           0.0766 |
| tiny.en / Vulkan      |                                  2.73 s |     71/420 = **16.90%** |           0.0164 |

Large V3 took 1.33–2.78 s for the individual 11–41 s clips. Two earlier basic clips and the first two pipeline clips had zero normalized word errors; that does not imply perfect transcription. The initial sample's improved accuracy made additional model downloads unnecessary for this session.

Important actual errors and observations:

- **Maropitant became “Meripitant.”** It was retained exactly as transcribed; no medically plausible correction was silently substituted.
- Large V3 recognized norepinephrine, buprenorphine, ECG, CBC, ALT and BUN in the tested clip. Tiny missed several of these, producing forms such as “Norpine Freen” and “Tentma-Prenorphine.”
- Other Large errors included singular/plural wording and the possessive in Addison's. Normalized WER ignores punctuation/capitalization and is not a drug-safety score.
- In the additional full-pipeline known-outcome recording, **“case ELM-TRAINING” became “cat KCLM training.”** Loss of the case label prevented confident linkage to that expected identifier. It stayed source-grounded/unlinked rather than being corrected by guessing.
- Hyphens/capitalization in other explicit case labels disappeared, e.g. AMBER-TRAINING → amber training. Only case/whitespace/separator variants of an explicit label may normalize for identity; spelling substitutions are not merged.

The backend reported `whisper_backend_init_gpu: using Vulkan0 backend`; device enumeration and dedicated-GPU activity identify the 7900 XTX. Peak sampled whole-GPU VRAM during isolated Large tests was about **5.26 GB**, including the desktop. Half-second samples may miss instantaneous peaks.

Known synthesis-buffer boundaries were recorded for the utterances. All 13 Large opening phrases matched uniquely; the largest coarse segment-start difference was **0.049 s**. This is controlled phrase/segment alignment, not validated word timing, speaker diarization, clock time, or ER timestamp accuracy. Padded tail overruns of at most one second are bounded with original ends retained; larger overruns fail. Voice-activation gaps are never inferred as continuous shift time.

## Extraction fixes and their rationale

The former all-in-one response asked the model to invent local IDs, reproduce timestamp numbers, write article bodies, bind cases and construct complex study records. It produced invalid references, omissions and unsupported paraphrases. A new `grounded-v2` **wire adapter** reduces that task while keeping the permanent version-1 content schemas and website unchanged:

- Code assigns evidence IDs to immutable transcript segments. The response schema enumerates only supplied IDs. Code supplies recording IDs, source offsets, discussion/question IDs and final links.
- The model selects/group discussions, names/selects topics, labels evidence facts and proposes recall questions. Fact quotations must match their cited source. A unique casing/whitespace-only mismatch may map back to the exact original span; words, numbers, units and negations are not semantically rewritten.
- Detailed accounts and additive article notes preserve the **selected source wording**, plus typed evidence. Free-form medical paraphrasing was removed after Gemma changed “administration was not documented” into “not given.” Missing documentation is not evidence of non-administration.
- Questions attach directly to evidence facts; code constructs source-recall flashcards, answers and links. This avoids invented question IDs and ambiguous answer indices. Other website study formats remain supported; this adapter currently generates flashcards.
- Existing content enters only as a bounded **topic naming index**, not prior clinical prose. Topic candidates require substantive source overlap; generic “classroom” overlap cannot send ultrasound instructions into a pump article. Unique matching acronym topics can reuse an existing article. This is not a complete semantic deduplicator.
- Explicit case labels must be supported by current sources. Unknown species/diagnosis/outcome stay unknown. Negative or ambiguous relationship statements prevent merging. Anonymous cases never link across recordings. Existing case IDs survive legacy-key recovery; case/space/hyphen variants require continuation evidence.
- Clinically uncertain/proposed quotes cannot simply become confirmed diagnoses/actual treatment via an incorrect label: conservative lexical guards downgrade explicit contradictions. These guards do not replace semantic review.
- Ungrounded/omitted material is retained as a clearly marked **unclassified source excerpt**, without a clinical interpretation, case association or article. Run results expose quality warnings; “done” means saved, not clinically approved. Discussions are sorted chronologically from source offsets.

No second AI reviewer, new database or additional inference service was introduced. The legacy extraction contract remains selectable for comparison. [Ollama's structured-output guidance](https://docs.ollama.com/capabilities/structured-outputs) recommends schema grounding; the compact schema is supplied in both prompt and decoder format.

## Fair model comparison

Seven identical synthetic transcripts contain **51 manually specified factual clauses**. Final comparisons used identical grounded instructions/contract hash, 8,192-token context, 4,096-token output cap, temperature zero, repeat penalty 1.0, presence penalty zero and keep-alive zero. These are request-only overrides. Qwen thinking was disabled; Gemma has no thinking override. Retrieval histories differ according to each model's preceding output, as they would in the actual consolidation workflow.

| Model       | Seven-input wall time | Strict clause/source/type matches | Clauses retained in source accounts | Flashcards | Unclassified source segments |
| ----------- | --------------------: | --------------------------------: | ----------------------------------: | ---------: | ---------------------------: |
| Qwen3 30B   |               44.22 s |                             36/51 |                               51/51 |         18 |                            0 |
| Qwen3.5 9B  |               62.10 s |                             41/51 |                               51/51 |          0 |                            0 |
| Gemma 3 12B |               78.22 s |                             35/51 |                               51/51 |         26 |                            0 |

**These are not medical accuracy percentages.** Source-account retention is deliberately deterministic copying of selected source wording. The stricter fact screen checks whole clauses, correct cited segments and acceptable evidence labels; it undercounts partial clauses and does not detect every semantic error. Human-readable reports show expected clauses, actual facts, accounts, cases and questions. JSON acceptance alone is never a quality pass.

Inspection of the actual outputs found:

- Actual fluids versus proposed norepinephrine/other drug options, missing doses/results, contradictory owner reports, and unknown outcomes survived in the source accounts.
- All three final short-corpus runs had the expected conservative case counts and preserved earlier article text. The separate FIP teaching did not become evidence for AMBER after deterministic association checks. An attempted unsupported model association was rejected and warned about.
- The positive-control ELM case retained the explicitly confirmed diagnosis, catheter placement and discharge; the system is not simply forcing every case field to null.
- Evidence-label mistakes remain: e.g. a numerical result and its missing unit can be combined under “unknown,” or an unidentified speaker can be mislabeled as an owner. A whole-clause count also penalizes shorter quotations that preserve part of a fact.
- Qwen3.5 had the highest strict typed-fact count and excellent memory headroom, but left every question empty despite the instruction. Qwen3 offered the best tested balance of grouping, usable cards and speed. Gemma produced more cards but weaker typed-fact matching and more topic proliferation.
- Topic titles/consolidation remain imperfect, especially after audio segmentation. Source-derived additions are safe append-only notes, not polished automatically rewritten reference articles. Curation remains necessary.

Generation rates were approximately **139–140 tokens/s** (Qwen3), **91–92** (Qwen3.5), and **64–66** (Gemma). A separate one-token text probe at the same context, with brief request-only residency, reported `size == size_vram` for each: **19.37 GB / 5.83 GB / 8.35 GB** respectively. This demonstrates full residency and avoids mistaking host-wide VRAM peaks/residual buffers for a model's allocation. Digests are in the validation JSON. All benchmark loads expired normally; no other application's model was forcibly unloaded.

**Provisional recommendation:** Qwen3 30B grounded-v2 for the first reviewed local pilot. Keep Qwen3.5 9B as a serious alternative for evidence classification/memory headroom; no model is selected as clinically validated.

## Full WAV pipeline and real interruption recovery

| Workload               | Recorded audio | Total wall time | Saved output                                            |
| ---------------------- | -------------: | --------------: | ------------------------------------------------------- |
| Seven independent WAVs |       180.00 s |     **73.72 s** | 11 articles, 3 cases, 1 shift, 17 discussions, 6 cards  |
| One longer WAV         |       374.00 s |    **229.06 s** | 14 articles, 7 cases, 1 shift, 38 discussions, 39 cards |

The long workload repeats the seven known fixtures twice, with gaps: it is a throughput/recovery stress test, not independent accuracy evidence. Its repeated labels are conservatively handled; counts are not an accuracy target. Sources, timestamps, append-only articles, pending privacy approvals and duplicate import checks were exercised. The short trial classified 55/55 source segments. The long trial classified 158/172, retaining 14 as unclassified and marking review required. That is not a measured 90% useful-capture claim.

Stage times: short trial transcription **14.38 s**, extraction **58.86 s**, retrieval **0.03 s**, commit **0.06 s**. Long trial transcription **28.98 s**, extraction **199.39 s**, retrieval **0.004 s**, commit **0.036 s**; its wall time includes two failed oversized responses and their smaller retries. Uploads were not attempted. Projection/export were also exercised; remote publication remains approval-gated.

The oversized long-recording parents had **7,055 / 6,415 prompt tokens** before the 4,096-token output allowance in an 8,192 context. Their combined budgets exceed the window: the current source-character estimate does not fully account for repeated IDs/schema. Both responses hit their cap and were rejected. Accepted child prompts were 3,589–3,958 tokens and fit with their actual outputs. Budgeting the complete serialized request (with a durable chunk plan) is the next efficiency/context-safety improvement; do not change boundaries underneath a pending job.

The longer recording initially exceeded the model output budget. The fix detects output-token exhaustion and persists a two-child split, at most two split levels. Successful children are checkpointed independently. Resume skips the failed oversized parent and completed children. This is one primary model with bounded smaller requests, not AI review orchestration.

A real SIGINT drill interrupted our owned CLI after a successful child checkpoint. A fresh invocation finished; all **three pre-existing checkpoint hashes** (including the transcript) were unchanged. No retranscription or successful-child inference was repeated. Unit tests also verify depth bounds, duplicate imports, per-file isolation, malformed-question quarantine, commit interruption, upload retries and legacy case continuity.

Both synthetic exports built in **pipeline-demo only**. Seven-file output: 40 HTML pages / 617 links. A longer-output build additionally exercises unclassified excerpts. Desktop/mobile browser tests navigate generated article → discussion → exact shift anchor, reveal a stored answer, and search. Production is restored to empty afterward; no test export is deployed.

## Overnight feasibility

Measured complete-workflow factors range from **0.410 to 0.612 wall seconds per audio second**. The slow end includes the actual token-limit failures/recovery. Larger/novel/noisy discussions may differ. The short workload incurs seven cold model/file starts; the longer one incurs more extraction chunks and retry cost, so these measurements must not be treated as perfect linear scaling.

The following illustration scales that observed range and adds approximately **five minutes** for 100 cold-file/request startups (conservative: some startup cost is already included). It excludes clinical review and any unconfigured remote transfer.

| Actual recorded audio | Nominal illustrated time | Planning range with 2× contingency |
| --------------------- | -----------------------: | ---------------------------------: |
| 4 hours               |                1.7–2.5 h |                          3.4–5.1 h |
| 8 hours               |                3.4–5.0 h |                         6.7–10.0 h |
| 12 hours              |                5.0–7.4 h |                        10.0–14.9 h |

A 12-hour hospital shift does not imply 12 hours of captured speech; measure the recorder's actual duty cycle. Four recorded hours look plausible within an eight-hour night on this synthetic workload; eight or twelve hours are not guaranteed. Large V3 and extraction are invoked sequentially. Peak sampled whole-GPU use in the multi-file run was **23.88 GB decimal**, close enough to the 24 GiB budget that other GPU work should be idle. Do not infer that concurrent Whisper/Qwen execution is safe.

## Commands and first real-recording pilot

All full reports/audio/checkpoints remain outside Git under:

```
/home/quinten/.local/share/vet-fieldnotes-validation/local-ai-r2/
```

The reusable synthetic tools are:

```bash
uv run --project pipeline python scripts/generate-benchmark-audio.py \
  --corpus pipeline --timed --output /PRIVATE/new-audio
uv run --project pipeline python scripts/benchmark-local-pipeline.py \
  --manifest /PRIVATE/new-audio/manifest.json --config /PRIVATE/local.toml \
  --workspace /PRIVATE/new-workspace --export-test
LIBRARY_DATASET=pipeline-demo ./scripts/local-node.sh run build
E2E_PIPELINE=1 ./scripts/local-node.sh run test:e2e
# Always finish with production before deployment or public preview:
LIBRARY_DATASET=production ./scripts/local-node.sh run build
```

Copy `config/benchmarks/local-vulkan.example.toml` outside Git and verify its local paths. It uses the measured Qwen3/grounded-v2/Large V3 settings, no remote/paid inference, no retention and no USB watcher. Existing `local-ai-r2/local-large-qwen.toml` reproduces this session; keep historical configs unchanged. Full JSON and `.md` model reports are private inspection artifacts. Real benchmark reports are rejected inside the public application checkout.

For the first **authorized** real pilot, use 5–15 minutes in a fresh real-only workspace. Record recollections first, then compare actual audio, transcripts, source facts, case links, article targets and cards. Correct a verbatim human reference for WER; recollection is not a transcript. A real audio manifest uses `origin: "authorized-record"` and recording entries with `id`, `file`, optional `reference`, `referenceKind: "human-transcript" | "recollection"`, and `terminology`. Pass `--origin authorized-record --authorization-ref LOCAL_PERMISSION_REFERENCE` to `scripts/benchmark-transcription.py`; recollection receives no WER score. Extraction's benchmark CLI supports the same origin/reference gate.

The current Vulkan adapter requires mono 16 kHz PCM16 WAV. Convert a local copy if necessary, never the recorder original; exact hardware file format and clock/mount behavior are still unverified. Inspect **all drug names, doses, units, negations and patient labels**, not only low-confidence-looking words. Do not fix ASR by guessing. Publication/privacy review remains mandatory. Independent cloud backup/key custody, real recorder trials and full-shift quality validation still precede unattended service/deletion activation.
