# Private clothing-rustle comparison

The organized installation lives in `~/FieldNotes/`; see [Local layout](LOCAL_LAYOUT.md). Historical paths in this document still work through compatibility shortcuts. Use the new layout for new work.

Filtering is an experiment on **copies**, never a replacement for original audio.
The owner has now explicitly enabled the combined profile for the retained-source
private run; general defaults remain unfiltered. Public publication is on hold. Reducing contact with the microphone
can be tried alongside filtering; do not change recorder settings preemptively.

Open `~/Fieldnotes-private-review/shirt-rustle-comparison.html` in Firefox.
This self-contained private HTML includes three versions of the same first
three-minute excerpt and the corresponding unreviewed Whisper transcripts:

1. **Unfiltered:** baseline.
2. **Highpass:** 80 Hz, two-pole filter to reduce low-frequency rumble.
3. **Denoise:** that filter plus gentle 6 dB FFT denoising with noise-floor tracking.

Compare the same 10–20 seconds in each player. Listen before reading the text,
then check quiet speech, word endings, drug names, omissions and invented words.
Write down which words are restored or lost. A quieter recording, fewer repeated
phrases, or valid timestamps alone do **not** establish better transcription.
Noise overlapping speech may remain difficult or impossible to recover.

All versions used the same local Large V3/Vulkan candidate decoding profile
(text context 0, temperature fallback off). No Qwen analysis, external inference,
cloud saving or publication occurred. The Morning Report remains empty and the
automatic timer disabled. Nothing on the USB was edited. Prior pilot audio,
transcripts and the production configuration remain unchanged.

Private artifacts and manifests are under
`~/.local/share/vet-fieldnotes-evaluations/rustle-filter-20261106-035123/`.
Each variant has an immutable `transcript.json`; correct the separate
`reference.json` when creating a reference, never overwrite the ASR transcript.
Do not commit generated reports: they contain real audio and transcripts.

## Reusing the optional filter tool

Requires the project's existing evaluation extra/PyAV, with no separate ffmpeg
installation or new model. Input must already be a separate mono 16 kHz PCM16
working copy outside Git. Choose a **new** private output filename:

```bash
cd /home/quinten/vet-knowledge-library
uv run --project pipeline --extra evaluation python scripts/filter-review-audio.py \
  /absolute/private/normalized.wav /absolute/private/highpass.wav --profile highpass
```

Use `--profile denoise` for the combined filter. The tool writes a provenance
manifest next to the WAV. It refuses overwrites, Git-contained paths, unexpected
formats and changed input hashes. It preserves sample count, does not remove
silence or boost gain, and compensates the measured 25 ms FFT filter delay while
flushing the end of the audio. Impulse tests check near-start/middle/end timing.
Changing a filter or library version warrants rerunning those tests.

The filter definitions follow FFmpeg's official
[highpass](https://ffmpeg.org/ffmpeg-filters.html#highpass) and
[afftdn](https://ffmpeg.org/ffmpeg-filters.html#afftdn) documentation. These
general filters do not guarantee removal of clothing rustle or preservation of
all speech. Keep the unfiltered baseline and seek owner review before enabling
any new processing default.
