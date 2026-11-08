# First authorized recording: local pilot

The organized installation lives in `~/FieldNotes/`; see [Local layout](LOCAL_LAYOUT.md). Historical path values in saved artifacts are translated internally. Old shell paths no longer exist; use the current layout for commands and new work.

For the existing two-sample sensitivity pilot, use the **self-contained viewer** at `~/Fieldnotes-private-review/small-recorder-settings-test.html`. It embeds both short clips and their transcripts so Firefox does not need access to other hidden local files. Navigation and timestamp playback stay within that file. To regenerate a private pilot viewer, use `scripts/render-pilot-report.py PRIVATE_PILOT --output PRIVATE_REPORT.html`; inputs/outputs must stay outside Git. The generated HTML itself contains clinical audio/text: keep it private. This is bounded to 32 MiB of short-clip audio and is not a solution for embedding an entire shift. Original audio, immutable ASR and reference files remain separate and unchanged.

## Rerun retained WAVs as a separate local ASR comparison

USB media is unnecessary once the original WAVs are imported. The owner-authorized whole-batch test uses `scripts/benchmark-retained-asr.py`, independently of the short manually referenced pilot below. It **does not** extract knowledge, modify the existing library/transcripts, call external inference or publish/upload anything. Keep source/output/config outside Git and use a new private output directory for each configuration. Copy the existing local Vulkan example to a private profile and set `max_text_context=0` and `temperature_fallback=false` in its `[transcription]` section for the current candidate. Existing profiles/defaults remain unchanged.

```bash
cd /home/quinten/vet-knowledge-library
uv run --project pipeline --extra evaluation python scripts/benchmark-retained-asr.py \
  --source-workspace ~/.local/share/vet-fieldnotes-live \
  --output ~/.local/share/vet-fieldnotes-evaluations/NEW-RETAINED-ASR-COMPARISON \
  --config /PRIVATE/candidate.toml \
  --authorization-ref LOCAL-RETEST-AUTHORIZATION-REFERENCE
```

Open the output's `index.html` for progress, individual original/working audio, full baseline/candidate text and timestamp/repetition warnings. Refresh after each recording. Resume with identical arguments: completed artifacts are hash-checked and reused; changed settings/source/model require a new directory. Resource deferrals return 75 and can be retried later; no other application's model is unloaded. Invalid model timestamps keep the entire raw output marked for review. A recovered raw output without a completed parse is explicitly review-required. Results remain unreviewed even when repetition is reduced; this procedure alone does not measure speech or clinical accuracy. The current transient batch unit/report are recorded in SESSION_HANDOFF.md.

**After the first real ASR incident:** prioritize a clearly understandable 30–60 s passage before another long run. Listen to both the original and normalized/working copy: if only the working copy sounds wrong, investigate decoding/resampling; if both are unintelligible, assess recorder placement/settings; if speech is clear but text is repetitive, isolate the ASR failure. These are diagnostic paths, not conclusions. Write a faithful manual reference, mark uncertain words as uncertain, and compare actual speech against output rather than accepting repetition-free JSON as accurate. Preserve every old transcript/raw Whisper output. The automatic pipeline now holds severe ASR repetition/invalid timing for review and warns on already derived notes. Use a separate pilot workspace to compare corrections; do not erase applied-recording checkpoints or silently replace existing canonical notes.

For the staged automatic USB service and desktop registration/review, use [USB_AUTOMATION.md](USB_AUTOMATION.md). This document remains the separate local-only model-comparison/reference workflow; it deliberately disables synchronization even if the supplied config enables it.

Use a **5–15 minute, appropriately authorized WAV**, in a new private workspace. Recording permission, local processing permission, cloud storage permission and publication permission are separate. This workflow uploads nothing, approves nothing, starts no USB service and deletes no recording. It rejects workspaces inside any Git checkout, including the private master. Keep all names, references, corrections and reports outside Git.

## Prepare once

From `/home/quinten/vet-knowledge-library`:

```bash
uv sync --project pipeline --extra dev --extra evaluation --frozen --inexact
# Installed already on this computer; use only to provision a replacement machine.
uv run --project pipeline python scripts/install-tokenizers.py
mkdir -p ~/.config/vet-fieldnotes
chmod 700 ~/.config/vet-fieldnotes
cp -n config/benchmarks/local-vulkan.example.toml ~/.config/vet-fieldnotes/pilot.toml
cp -n config/benchmarks/qwen35-9b.toml ~/.config/vet-fieldnotes/pilot-qwen35.toml
chmod 600 ~/.config/vet-fieldnotes/pilot*.toml
```

`pilot.toml` uses installed Whisper Large V3 f16/Vulkan and Qwen3 30B. The comparison file uses installed Qwen3.5 9B Q4. Its default transcription settings are irrelevant: transcribe once with `pilot.toml`, then use both models on the same saved transcript. These are request overrides, not Ollama global settings. Verify model/executable/tokenizer paths after moving computers. No automatic weight download is enabled.

Before inference, check shared workloads:

```bash
curl -fsS http://127.0.0.1:11434/api/ps
cat /sys/class/drm/card1/device/gpu_busy_percent
pgrep -af 'MMM|FCC|whisper-cli|ollama runner'
```

The DRM card number can change. If another job is using the GPU, wait or coordinate; do not stop/unload its models or restart services. Run transcription and extraction sequentially. Qwen3 can occupy most VRAM. The tools require already installed local GGUF models on loopback Ollama port 11434 and reject cloud-backed models; no paid or external inference is supported here.

## Copy, inspect and normalize

After the recorder has finished writing, identify the actual WAV path using the file manager or `lsblk -o NAME,LABEL,FSTYPE,MOUNTPOINTS`. Do not assume its directory layout or that filesystem modification time equals recording start time. Never move/delete files from the recorder. The following variables are examples; replace the source, date and authorization reference:

```bash
cd /home/quinten/vet-knowledge-library
recording_source='/media/quinten/RECORDER/path/recording.WAV'
pilot_root="$HOME/.local/share/vet-fieldnotes-evaluations/first-real-001"
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py inspect "$recording_source"
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py prepare "$recording_source" \
  --workspace "$pilot_root" --date YYYY-MM-DD --authorization-ref LOCAL-AUTHORIZATION-REFERENCE
```

`prepare` copies the original to `audio/original.wav`, checks hashes/source stability, and locally converts a **separate** copy to mono 16 kHz PCM16 at `audio/normalized.wav` using PyAV/libswresample. Both copies remain. Format, size, duration, filesystem time, source hashes and owner-selected date are recorded in `session.json`; clock confidence stays unknown. Conversion fails on truncated/inconsistent audio, more than 15 minutes or an existing target. Choose a new root after a failed preparation; do not overwrite partially prepared evidence. No application changes are needed for another supported WAV format.

Write `$pilot_root/recollections.md` **before reading the ASR or extraction**. Include what you recall, what matters, uncertainties and approximately where discussions occurred. Recollections are fallible observations, not a verbatim transcript.

## Transcribe and compare models

```bash
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py transcribe "$pilot_root" \
  --config ~/.config/vet-fieldnotes/pilot.toml
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py extract "$pilot_root" \
  --config ~/.config/vet-fieldnotes/pilot.toml --input asr
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py extract "$pilot_root" \
  --config ~/.config/vet-fieldnotes/pilot-qwen35.toml --input asr
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py report "$pilot_root"
xdg-open "$pilot_root/review.html"
```

The report opens as an offline local file, with original/normalized audio players, timestamp links, ASR, model-specific detailed discussions/fact labels, cases, article targets and study questions. No web deployment or public dev server is involved. Each result includes model digest, input hash, request settings, timing and checkpointed private library. A changed transcript/model/settings produces a separate result. Re-running a completed command reuses its output; interruption preserves completed transcription and chunk files. Incomplete jobs return failure with paths to retained results. Pending bounded retries retain their ledger schedule; if exhausted, inspect the result's `workspace/events.jsonl`/ledger and use `vet-pipeline retry JOB_ID` with that workspace before re-running `extract`. Do not erase checkpoints to obtain another score.

## Correct the reference, then isolate extraction errors

Never edit `transcript.json` or the audio copies. Listen and edit **`reference.json`**, preserving the `segments` structure and recording-relative `start`/`end` seconds. Leave uncertain sounds marked as uncertain in the text rather than guessing a drug or diagnosis. Keep corrections faithful to the recording; do not add remembered facts to this reference. When checked, change `referenceStatus` from `draft-not-corrected` to `manually-corrected`.

Run the same two `extract` commands with **`--input reference`**, then regenerate the report. It now shows separate ASR/reference results, a textual diff and normalized word error rate. WER is a lexical measure, not medical correctness. Corrected references are versioned by content hash; old model results retain their own input snapshots.

Edit `review.csv` (ordinary spreadsheet/CSV editor). Fields are `model,input,category,reference,observed,source_start,comment`. Use categories `missed`, `incorrect`, `invented`, `terminology`, `source-link`, `case-link`, `topic`, `study`, `other`. Put the expected fact/evidence in `reference`, the model behavior in `observed`, and the relevant seconds in `source_start`. Re-run `report` after editing. Review **actual meaning and source association**, not only valid JSON or copied keywords.

Check especially medication names/doses/units, negation, owner versus clinician statements, actual versus proposed treatments, contradictory histories, missing diagnoses/outcomes, patient continuity, equipment/workaround limitations and question usefulness. All unclassified excerpts remain in the private timeline, highlighted for review. Exact quotes protect provenance but do not guarantee a correct evidence label or case association.

For later manual organization, each completed result has `editable-library/`. Preserve permanent IDs/source references and edit those portable records, then apply using the existing owner-edit path:

```bash
# Replace RESULT with the result directory printed by extract.
uv run --project pipeline vet-pipeline --workspace "$pilot_root/results/RESULT/workspace" \
  apply-edits --source "$pilot_root/results/RESULT/editable-library"
uv run --project pipeline --extra evaluation python scripts/evaluate-recording.py report "$pilot_root"
```

Do not export this clinical pilot into `fixtures/generated`, `content/public` or either repository. No publication step is part of evaluation. Raw audio/transcripts are not in permanent-library encrypted backups; retain this private pilot securely while evaluating. The current permanent-library strategy is private GitHub primary remote storage plus the local copy; configure and verify authorized private-master sync/recovery separately. This evaluation remains local-only. Independent backups are optional future work, documented in [INDEPENDENT_BACKUP.md](INDEPENDENT_BACKUP.md), and missing credentials do not block this pilot.
