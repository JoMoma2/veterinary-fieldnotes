# Private whole-shift transcription comparison

`scripts/compare-shift-asr.py` compares retained WAVs without extraction, knowledge-library updates, publication or cloud saving. Select an isolated workspace containing exactly one shift. All generated data must stay outside every Git checkout. This tool does not activate USB polling or retention cleanup.

Quality is the selection criterion. Runtime and GPU memory are diagnostic/overnight-capacity measurements, never an automatic quality ranking. No reference transcript means no measured word-accuracy score. Review omissions and invented text separately, including confirmed noise-only passages, drug terminology, negations, numbers and units.

## Comparison matrix

The initial matrix has twelve variants:

- Whisper Large V3, Granite Speech 4.1 2B, Qwen3-ASR 1.7B, Parakeet TDT 0.6B v3 and Cohere Transcribe: each on the same denoised copies, with speech gating off/on.
- Whisper on unfiltered normalized audio, with no speech gate.
- Granite with speech gating and an explicit generic medical vocabulary list. Vocabulary support is checked; a missing capability fails visibly rather than silently ignoring the list.

New weights use F16, not aggressive low-bit quantization. The CPU Silero v6.2 detector uses threshold0.5, minimum speech250ms, minimum silence300ms and padding200ms. These are experimental settings, not verified detection accuracy. Excluded intervals remain playable and are labelled "speech not detected", never confirmed silence.

All variants use windows up to30seconds with one-second overlap across splits. Overlaps stay visible; words are not silently merged or rewritten. This is a controlled windowed comparison, not each upstream model's full long-audio inference recipe. Earlier full-recording Whisper output is shown separately when available. Models without native timestamps get explicitly labelled input-window bounds; no exact word alignment is invented. Speaker identification is outside this comparison.

Original imported WAVs and earlier transcripts remain unchanged. Normalized and filtered copies, window checkpoints, raw Whisper responses, native raw text, rejected attempts and readable Markdown are retained privately. Rendering never edits the source workspace. Unexpected original/model/runtime hashes stop the affected operation.

## Local runtime and installation

Use a separately built [transcribe.cpp](https://github.com/handy-computer/transcribe.cpp) shared Vulkan runtime, pinned by commit and binary hash. This is a third-party port, not the upstream PyTorch runtime; unexpected quality needs comparison against the upstream implementation. The current development build was tested at commit`5700f12`. Bindings come from that same checkout and are imported without changing the main environment's installed packages. Select the discrete RX7900XTX explicitly; refuse CPU/iGPU fallback. Whisper uses the existing installed whisper.cpp executable and weights.

The installer plans approximately14.1GB of public converted weights, including a small VAD model. Check free space and authorization before downloading. It pins Hugging Face revisions, validates LFS SHA256/length and keeps partial downloads outside Git:

```bash
cd ~/FieldNotes/app
pipeline/.venv/bin/python scripts/install-asr-comparison-models.py \
  --directory ~/FieldNotes/ai/models/asr-comparison --plan-only
# After authorizing these downloads:
pipeline/.venv/bin/python scripts/install-asr-comparison-models.py \
  --directory ~/FieldNotes/ai/models/asr-comparison
```

Models: [Granite](https://huggingface.co/ibm-granite/granite-speech-4.1-2b), [Qwen-ASR](https://github.com/QwenLM/Qwen3-ASR), [Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), [Cohere](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026). Converted artifacts and licenses are linked in the pinned runtime's model documentation. Downloading public weights never sends recordings to the model host.

## Prepare, run and review

```bash
pipeline/.venv/bin/python scripts/compare-shift-asr.py prepare \
  --workspace /PRIVATE/NEW_COMPARISON \
  --source-workspace /PRIVATE/ONE_SHIFT_WORKSPACE \
  --config ~/FieldNotes/config/pipeline.toml \
  --models ~/FieldNotes/ai/models/asr-comparison \
  --runtime ~/FieldNotes/ai/transcribe.cpp \
  --authorization-ref OWNER_LOCAL_AUTHORIZATION
pipeline/.venv/bin/python scripts/compare-shift-asr.py run --workspace /PRIVATE/NEW_COMPARISON
# Display-only rebuild:
pipeline/.venv/bin/python scripts/compare-shift-asr.py report --workspace /PRIVATE/NEW_COMPARISON
```

A preparation interruption before `session.json` exists requires preserving the incomplete directory and preparing a fresh one. Once the session exists, resume with `run`, not `prepare`. Model/settings changes require a new comparison.

Use the existing private loopback review server for `review/asr-comparison.html`. This page has links to recording pages, two model selectors, original/denoised playback and timestamp buttons. Its only executable script is explicitly authorized by a CSP hash; transcription text is escaped. No external assets are loaded. Keep capability URLs and all real-session artifacts out of Git. Readable transcripts also appear under `readable/VARIANT/recording-NNN.md`. Results appear per completed recording; refresh to update.

The ordinary Morning Review selection and original library are not changed. Put the separate browser launcher in the hub's reports directory and link it from the local start page. Actual session paths, service names and counts belong only in private maintenance continuation notes.

## Recovery and shared resources

Variants run sequentially, with one model loaded per child worker. Admission never evicts Ollama models or restarts other services. Between calls the suite allows its own recent GPU busy measurement to settle; persistent activity, new Ollama use or insufficient memory defers the comparison with exit75 without spending an inference attempt.

Successful windows survive worker restarts. Failed windows get one bounded retry, preserving rejected attempts; a repeatedly interrupted window is held while later windows continue. Native calls have cancellation/watchdog limits. Variant workers are isolated so a native crash does not terminate all comparisons. The supervisor permits a bounded variant retry, preserves successes and reports terminal failures. Pending downloads defer safely. An optional systemd sleep inhibitor lasts only while the comparison runs.

Run under a user systemd service with `Restart=on-failure` and a conservative retry delay for unattended operation. Do not start a second supervisor for the same workspace. Source retention and all clinical upload/publication gates remain unchanged.

Local HTML launchers can navigate to the private HTTP report with browser cross-site metadata. The viewer permits only capability-protected top-level GET navigation to review HTML. Cross-site fetches, iframes, audio/JSON loads, arbitrary Origin headers and non-loopback Host headers remain blocked. Test the actual file launcher through to playback; direct HTTP checks alone miss this failure. Restart only the affected read-only viewer with `--reuse-state` after applying viewer changes, preserving its capability URL.
