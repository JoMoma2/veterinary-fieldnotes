# Local AI results — resumed development, 2026-11-02

**Whole-shift speaker correction /5-repeat filter (2026-11-08):** initial online matching was ineffective (215local voice groups ->214labels). New isolated joint grouping uses cached segmentation, one additional97MiBTitaNet CPU embedding candidate, and owner-confirmed reference anchors. Final map120unverified groups,17spanning files; known-owner reference agreement is supervised, NOT automatic recognition accuracy. Local speech detection/false splits/merges remain limitations. Exact normalized5+consecutive runs are now masked from extraction/evidence (40runs in selected shift); raw audio/transcripts remain intact. Final reports: ~/Fieldnotes-private-review/Shift-wide-speakers-20261108/Results.html. New Qwen work waits automatically for the prior run.235Python tests pass; no public publication/clinical upload/default voice-service activation. See SHIFT_WIDE_SPEAKERS.md / latest handoff.

**Speaker/medical-study test launched (2026-11-08):** same78recordings/72saved parsed transcripts, no Whisper rerun or live-library/publication change. New private CPU speaker phase uses small public ONNX models in an isolated Python3.12environment, then whole-night Qwen proposes evidence-linked role hypotheses and medical-only self-contained questions. No permanent client/staff roster; optional staff persistence deferred. Obvious case-trivia filter and removal of forced cloze cards supplement the prompt, not clinical validation.224Python tests pass. Results refresh in ~/Fieldnotes-private-review/Speakers-and-medical-questions-20261108/Results.html. Worker runs independently; final completion/quality requires actual inspection and owner review. See SPEAKERS_AND_STUDY.md / latest SESSION_HANDOFF.md.

**Whole-night A completed; focused-evidence B running (2026-11-08):** A saved its index and all5details with39241–40415actual input tokens,2831.773s total saved inference time, peak22187MiBGPU. After strict audited citation projection:44facts,8lessons,5questions;3accepted cited narratives/2unaccepted drafts. These are provenance/output counts, not medical accuracy. Full context fitted, but inaccurate evidence quotations and attention omissions remain. Do not claim the context change fixed extraction.

B retains exactly the same full-night transcript/index/runtime and adds budgeted duplicate original passages near the detail task. Fresh detail calls compare citation fidelity without shortening context or adding review agents. First input budget42331tokens,20duplicated blocks,32768output room within81920. B runs after A rather than concurrently; actual completed results are in the private focused-evidence/ directory. The owner-facing landing links both versions.209Python regression tests pass. See WHOLE_SHIFT_CONTEXT.md / latest SESSION_HANDOFF.md; older “still running” checkpoints below are historical.

**First real80Kresults:** whole-night index actually consumed39241input tokens and completed in482.857s, generating4788tokens including reasoning; peak22166MiBGPU, minimum55096MiBavailable systemRAM.5episode proposals were saved; identity validation rejected9items, retaining1named/4unassigned episodes. First detailed request consumed39834input tokens and completed in463.979s with4934generated tokens. These are execution/provenance metrics, not medical accuracy. All-night context fit without truncation.

Added high-recall literal-name/owner-alias source hints after finding that broad context alone still omitted some candidate mentions. Hints are candidates, never automatic identity links. Unique case/space and exact same-recording citation restoration recovers valid source bindings while keeping raw model replies and prior projections unchanged in history. First readable detail now contains an89-word cited account,16facts,2lessons and2cards; further details were still running at this checkpoint. Do not attribute results solely to context or promote to production before owner review.

**Whole-night context experiment started (2026-11-07):** owner prioritizes quality and explicitly authorized up to~8h, much larger context and related changes on the latest batch only. Selected78recordings/72parsed transcripts:~34866plain tokens,324compact source blocks,~39241whole-prompt tokens.52transcripts are eligible evidence,20flagged transcripts are context-only,6raw-only outputs stay available for review. No Whisper calls or live-library edits. Final profile81920context,32768generated tokens (reasoning+answer), native thinking mode, temperature.6/top_p.95/top_k20/min_p0,40GPUlayers with RAM offload and2mper-request keep-alive. All available parsed-night text is supplied to every detail pass.

Local metadata identifies the installed tag as Thinking-2507; old thinking-off assumptions are not valid for that variant.80Kallocation/synthetic ambiguity probe passed (unknown association,4.78s, peak22130MiB GPU). The real full-night run is separate and was still running at this documentation checkpoint; do not present allocation probes as medical validation or claim context alone caused an improvement. Source-linked readable synthesis, explicit tentative/unassigned patient associations and optional meaningful questions are evaluated together. Full details: WHOLE_SHIFT_CONTEXT.md and SESSION_HANDOFF.md.

**Owner feedback — 2026-11-07:** despite good intelligible-speech ASR by informal listening, real knowledge extraction/card utility is reported extremely poor, with incoherent or nonmedical recall examples. Existing throughput, JSON validation and exact-source checks do not measure educational value. Owner requested a same-configuration rerun for examples and specifically deferred AI fixes. Old complete outputs were archived; fresh extraction checkpoints/library start empty while29parsed transcripts are reused. No claim of improved quality is warranted. Prioritize semantic relevance/card usefulness in the next authorized development session.

**Owner listening follow-up / runtime promotion (2026-11-06):** owner found high-pass improved the audio/transcript and combined gentle denoise improved both further. They informally estimate98–99% words on the target clips; this remains **unmeasured**, with no manually corrected WER reference and no full-shift accuracy claim. Owner explicitly requested the full retained-source private run. Only the private live configuration was promoted to denoise+context0/fallbackfalse; general defaults stay unchanged. New integration tests verify filtering/checkpoint retention through the full synthetic library/candidate workflow. See handoff for real-run observation, not this historical benchmark table, for completion status.

## Clothing-rustle filtering comparison — 2026-11-06

The owner informally estimates90–95% words correct outside clothing rustle on the recent pilot; this is listening feedback, **not measured WER**. They identified the first entire180s clip as rustle-heavy. Tested that same clip using existing LargeV3/Vulkan, context0/fallbackfalse, with three audio preparations. All inference was local and GPU acceleration confirmed.

| Preparation | ASR seconds | Segments | Max exact phrase count | Consecutive max | Heuristic hold |
| --- | ---: | ---: | ---: | ---: | --- |
| Unfiltered | 6.310 | 50 | 6 | 6 | No |
| 80Hz two-pole high-pass | 5.313 | 39 | 4 | 2 | No |
| Same high-pass +6dB FFT denoise | 5.941 | 40 | 2 | 1 | No |

No manually corrected reference exists; **do not interpret fewer segments/repeats as improved speech or veterinary-term accuracy**. The first denoised experiment, before correcting its25ms delay, produced28 consecutive repeats; its raw output/audio remain retained separately. Filtering and slight boundary changes can harm recognition. Final delay-compensated filtered audio retains exact sample count, with synthetic impulse tests verifying near-start/middle/end alignment. No production filter/settings were enabled. Private report and next owner comparison steps: [AUDIO_FILTER_REVIEW.md](AUDIO_FILTER_REVIEW.md).182Python tests pass.

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

The current Vulkan adapter requires mono 16 kHz PCM16 WAV. Convert a local copy if necessary, never the recorder original; exact hardware file format and clock/mount behavior are still unverified. Inspect **all drug names, doses, units, negations and patient labels**, not only low-confidence-looking words. Do not fix ASR by guessing. Publication/privacy review remains mandatory. Real recorder trials, authorized private GitHub storage/recovery and full-shift quality validation still precede unattended service/deletion activation. Independent backup/key custody is deferred and optional under the current GitHub/local storage policy.

## First-recording readiness revision (r3, 2026-11-02)

This revision prepares a reviewed real pilot rather than extending the synthetic model search. No new model weights, driver/runtime changes, service restarts, clinical input or external inference occurred. Small pinned offline tokenizer metadata was installed (Qwen3 ~11.4 MB, Qwen3.5 ~12.8 MB), plus user-local rclone 1.75.2 (~30 MB release archive, official checksum verified). Existing Large V3 and all installed LLMs remain unchanged.

### Whole-prompt planning and measured effects

Grounded-v2 budgets the **actual serialized system/user messages**, including response schema, source identifiers/text, relevant topic naming index, role/template allowance, full output-token reservation and safety space. Pinned local tokenizers avoid an English-character heuristic. If no tokenizer is configured, a conservative UTF-8 byte bound is used. Missing/bad configured tokenizers fail before inference; no runtime tokenizer download occurs. Compatible API requests no longer append an unbudgeted duplicate schema and now set their reserved output limit explicitly.

New jobs persist contiguous source ranges in `extractions/JOB/chunk-plan.json` before inference. The plan is immutable and transcript-hash bound. Existing numeric checkpoint/split files retain the historical partition, so completed results are not repacked or recomputed. If growing topic context no longer fits a saved range, the preflight guard creates durable child splits before HTTP; bounded output-limit splitting remains a fallback. A single oversized source segment fails with an understandable request for finer verified source offsets/larger context rather than silently truncating it.

One targeted run reused the **same saved 374-second ASR transcript** as r2, with Qwen3 30B and the new planner/instruction:

| Measurement | Prior r2 | Readiness r3 |
| --- | ---: | ---: |
| Extraction time | 199.387 s | 125.581 s |
| Oversized attempted requests | 2 | 0 |
| Classified / unclassified source segments | 158 / 14 | 161 / 11 |
| Generated study cards | 39 | 3 |

Six proactive requests completed with `stop`. Estimated/actual prompt counts were 3144/3095, 3753/3704, 2758/2709, 2599/2550, 3699/3650, 2052/2003; each reserved 4096 response tokens plus 128 safety in an 8192 window. Extraction plus file projection took 125.983 seconds. The ~37% extraction-time decrease includes avoiding failed oversized requests. **This was not a new end-to-end audio timing or an isolated chunk-size ablation:** both the planner and a classification instruction changed. It is one repeated synthetic workload, not proof of medical accuracy or full-shift throughput.

Manual inspection found AMBER's conflicting grooming history preserved and CEDAR follow-up/vitals linked to its explicit earlier case. Separate FIP teaching produced no new case (the old run had an inappropriate FIP discussion case). ASR's seeder/cedar label mismatch remained deliberately separate. Smaller chunks did **not** solve all associations or consolidation: two blood-sample-unknown article targets remain, evidence kinds sometimes confuse actual IV fluids with proposed treatment or label lactate as owner-report, and card output declined sharply. New output has 13 articles, 3 cases, 34 discussions, 3 cards. Case counts alone are not accuracy scores; the waveform repeats fixtures twice. Review actual meanings/source links before acceptance.

### Unclassified-source investigation

The original 14 sources were genuinely absent from accepted model accounts, rather than discarded by quote validation. They included explicit missing results/diagnosis/outcome, a blood sample with no results, and context/teaching/continuation markers. The instruction now asks for clinically meaningful unknowns while avoiding unsupported topic/case assignments. All source segments still survive verbatim, even when unclassified. Literal unknown clauses can be tagged deterministically as `unknown` while remaining context-unassigned; no article, case or question is inferred from that fallback. New quality reports distinguish model omissions, context-only citations and deterministic unknown scaffolding. This fallback fired on none of the new run's remaining 11 excerpts; it is tested separately.

Model-classified source coverage improved **158→161 of 172**, and unclassified segments declined **14→11**. This measures accepted source coverage, not semantic completeness: copied source text or a syntactically valid fact may still have an incorrect evidence kind or grouping. Unclassified material remains visible/highlighted in the private timeline and editable via the existing ID-preserving owner-edit path.

### Private pilot workflow and smoke

See [FIRST_RECORDING.md](FIRST_RECORDING.md) for exact commands. `scripts/evaluate-recording.py` accepts a WAV ≤15 minutes, preserves original/hash/timestamps, converts only a workspace copy, saves immutable ASR plus a separate manual reference, runs installed local Qwen models with identical input, and renders an offline `review.html` with audio/source links, model outputs, recollections and owner findings. Model/input/settings/digest identify independent result workspaces. References must be explicitly marked corrected before WER or reference extraction; memories are never scored as verbatim ground truth. Workspaces/keys/backups are rejected inside Git, including the private master. Real input is not routed into demo exports, cloud models, remote storage or publication.

A **41.130625-second synthetic medication WAV** exercised the new path: Large V3 took **2.578 s**, Qwen3 **10.685 s**, Qwen3.5 **15.198 s**. Both completed and each saved one article/case/discussion, **zero study cards**. Cached replay reused the Qwen3 result. Offline desktop (1440 px) and mobile (390 px) browser checks showed both models, working normalized audio, no horizontal overflow and **zero HTTP requests**. This validates usability/integration, not a fresh accuracy estimate or speaker/timestamp accuracy. No real recording was available.

Sanitized metrics: [validation/readiness-r3.json](validation/readiness-r3.json). Full synthetic/private artifacts: `~/.local/share/vet-fieldnotes-validation/readiness-r3/`. Existing r2 overnight estimates remain conservative illustrations; do not substitute a saved-transcript run for a new full-shift measurement. The next useful quality evidence is an authorized real pilot, not another model download.

## Unattended USB integration evidence

The local AI components were exercised by a real **background systemd user timer** reading a simulated removable directory, with no manual pipeline command after attachment. No physical recorder or clinical recording was used. Three synthetic runs verified private GitHub pushes; the synthetic master archive was subsequently preserved separately and the production archive reserved for authorized real knowledge. The final local-only rerun tested the current source-recall fallback after this separation.

Final run:4 WAVs/79.268 s audio, Large V3 Vulkan confirmed for all files, Qwen3 grounded extraction;5 articles/2cases/7discussions/6cards;115.101 s including deliberate SIGINT, timer delays/reconnection and reporting;45.015 s worker time. Three cards were deterministic exact-quote clozes, counted separately in quality files; the model authored the remaining cards. This fallback is source recall, not medically verified educational inference. Unclassified excerpts never create fallback cards. No semantic-capture percentage is inferred.

Three saved transcript/extraction hashes survived interruption unchanged; reconnection created no duplicate jobs; stereo32k normalization preserved original bytes; a future-year recorder mtime did not stall import; all audio/transcripts retained. The earlier repeated-topic run updated8existing articles but Qwen emitted no cards, motivating the labeled fallback. Comparisons between repeated runs are not fair independent accuracy/model-speed comparisons.

Offline390/1440px checks validated actual4.66 s timestamp seeking, audio playback, article/source anchors and no external HTTP. Full private artifacts are `~/.local/share/vet-fieldnotes-validation/usb-automation-r1` through`r4`; sanitized metrics are [validation/usb-automation.json](validation/usb-automation.json). See [USB_AUTOMATION.md](USB_AUTOMATION.md) and SESSION_HANDOFF.md. Physical USB mounting/clock behavior, ER noise and clinical semantic quality remain unverified. No new model weights/system AI settings were changed.
# Real-recording ASR quality incident — 2026-11-05

The first real batch exposed severe repeated-phrase ASR patterns in all six long recordings (a dominant normalized phrase repeated 1,310–2,177 times per file). Four jobs completed structurally, while three exhausted transcription retries: two had zero-length segments, and one ended approximately 1.025 s beyond the normalized source. All raw Whisper outputs and original/working audio were retained. Successful JSON, exact source quotes and completed note commits do not measure correspondence to actual speech. The owner's impression of approximately 5% useful capture is not a benchmark score and cannot yet be attributed to recording quality alone.

Two 45 s isolated excerpts using the same local Large V3 Vulkan backend gave mixed results: 3.72 s for a beginning clip with eight repetitions of one phrase, and 1.84 s for a clip from within the long-run loop with three unique segments and no repetition flag. No manually corrected reference exists yet. This does not demonstrate hallucination-free decoding, veterinary accuracy, or that short chunking solves the problem. Sampled waveform levels were nonzero with generally low hard clipping; this cannot distinguish intelligible speech from environmental noise. Private clips remain outside Git under the evaluations/asr-loop-check directory recorded in SESSION_HANDOFF.md.

Deterministic screening now flags severe between/within-segment repetition and invalid timestamps. Affected new jobs enter `review`, retain complete output and do not generate knowledge automatically. Existing notes are preserved with source-quality warnings. Three exhausted jobs were moved to review; six recordings are flagged.157 Python tests verify holds, independent file processing, raw retention, HTML escaping and warning propagation. Next benchmark: owner listens to original versus normalized audio, writes a faithful reference for an understandable 30–60 s segment, then compares controlled short-window/VAD candidates. No new weights, paid inference, automatic source deletion or whole-shift reprocessing was used.
# Controlled decoding settings comparison — 2026-11-05

The existing local Large V3/Vulkan CLI was tested on the same two retained 45 s clips with `-mc 0 -nf` (zero prior-text context and no temperature fallback). Beginning clip: 1.554 s,7segments/6unique phrases/max2repetitions versus baseline8segments/1phrase/max8repetitions. Loop-region clip: 1.965 s,6unique segments/max1repeat versus baseline3unique segments/max1repeat. These are repetition/timing measurements, **not transcription accuracy**; no manually corrected reference exists, more varied text may still be wrong, and the effects of the two settings were not isolated. Raw baseline/candidate outputs, metrics and the isolated TOML profile remain private at the path in SESSION_HANDOFF.md. Nothing was uploaded or overwritten.

The pipeline now supports `transcription.max_text_context` (default -1, CLI default retained) and `temperature_fallback` (default true), with request settings recorded in transcription metadata. Production configuration was not changed.158 Python tests pass. Next: listen to a clear excerpt, transcribe a reference, then compare errors/omissions across the same audio; consider speech detection/short windows only with source-offset preservation. Do not equate repetition screening with clinical correctness or rerun the entire shift before this check.
# Retained full-WAV rerun — owner-authorized 2026-11-05

All seven local originals matched their recorded SHA256 values after USB removal. A separate retained-audio benchmark now runs the existing Large V3/Vulkan model with `max_text_context=0,temperature_fallback=false`, retaining all previous results. The private report compares baseline/candidate text and repetition/timestamp metrics per file; there is no extraction, publication or remote transfer. Session/source/model/settings binding and artifact hashes support safe per-recording resume. 165 Python tests pass. This section records startup only; see the private summary and latest handoff for actual batch results. No corrected reference exists yet, so reduced repetition is not an accuracy percentage or proof of useful clinical capture.
# Completed retained-WAV comparison

All 7 owner-authorized local recordings completed the isolated candidate test. Total decoded audio 22,887.021s; per-recording elapsed work 633.096s; wall time 1,212.312s including resource deferrals. Maximum exact phrase counts (baseline→candidate), recordings1–7:1843→17,2177→18,1310→31,1746→20,1604→48,1628→28,2→2. All six long candidates still require review. Timestamp failures affected baseline recordings 3/4/5 and candidate 3/6, so one previously valid file acquired a zero-length segment. All 7 raw candidates remain available and 5 have validated-structure parsed JSON. This measures repetition/timing behavior, not medical accuracy or useful capture.

All 7 originals, 7 normalized WAVs and 7 baseline raw outputs were hash-verified unchanged. Actual completed resume reused all 26 candidate JSON files without inference. The transient service finished and was removed.165 Python tests passed; private offline report passed desktop/mobile navigation and zero-external-request checks. Sanitized aggregate results are in [retained-asr-20261105.json](validation/retained-asr-20261105.json); clinical outputs remain outside Git. Production defaults/library stayed unchanged, and no extraction/publication/remote saving was performed. A human reference is still needed before promoting settings or comparing knowledge extraction.
# Latest-shift small early/later pilot — 2026-11-06

Two 180 s excerpts from separated latest-shift recordings were tested with the SAME candidate profile (zero prior-text context/no temperature fallback). An apparent long-file/shorter-voice-mode naming transition helped select early/later files; exact device sensitivity change was not independently confirmed. No settings were reversed or adjusted between excerpts. Earlier: 6.578 s,50segments,41unique normalized phrases, maximum 6 repetitions. Later: 7.09 s,33segments,31unique, maximum 2 repetitions. Both had valid timestamps, no automatic repetition flag, and confirmed Vulkan execution. These are screening/runtime metrics, **not speech accuracy or evidence that one recorder setting is better**. Human references remain draft.

The existing private evaluation workflow was reused under the sensitivity-pilot path in SESSION_HANDOFF.md, with separate original copies/normalized audio, immutable ASR, reference templates, CSV review and audio-linked HTML. Only the two chosen full source files were copied locally; all device contents were read-only and no whole-shift import occurred. Morning Report file hashes and zero-record state were verified unchanged, automation remains disabled, and no Qwen/cloud inference ran. Next: owner listens/compares actual words; do not promote a profile or launch the full batch solely because both clips passed repetition screening.
