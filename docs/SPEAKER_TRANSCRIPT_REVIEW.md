# Transcript-only owner voice review

Use `scripts/review-speaker-transcripts.py` for an isolated, local CPU comparison of saved transcripts with an explicitly enrolled owner reference and listening labels. It never calls Whisper or an extraction LLM, opens a knowledge Store, uploads data, publishes, starts USB polling or deletes source material. The ordinary processing timer can remain paused.

Prerequisites: an existing whole-shift TitaNet comparison, cached diarization turns, retained mono16k WAVs, a matching owner-only confirmed reference, and genuine listening-pack labels with explicit other-speaker examples. Use the installed speaker environment under `~/FieldNotes/ai/diarization-venv/`. No additional models or dependencies are required.

```bash
cd ~/FieldNotes/app
~/FieldNotes/ai/diarization-venv/bin/python scripts/review-speaker-transcripts.py prepare \
  --reference /PRIVATE/OWNER_REFERENCE \
  --comparison /PRIVATE/WHOLE_SHIFT_COMPARISON \
  --labels /PRIVATE/GENUINE_LISTENING_LABELS.json \
  --manifest ~/FieldNotes/ai/models/speakers/titanet-models.json \
  --directory /PRIVATE/NEW_TRANSCRIPT_WORKSPACE \
  --visible /PRIVATE/READABLE_RESULTS \
  --owner-label YOUR_CHOSEN_DISPLAY_NAME
~/FieldNotes/ai/diarization-venv/bin/python scripts/review-speaker-transcripts.py run /PRIVATE/NEW_TRANSCRIPT_WORKSPACE
```

`prepare` requires a new private directory outside every Git checkout. Original audio remains intact; retained analysis WAVs are hardlinked when possible. Transcript and raw Whisper JSON copies preserve their bytes. Frozen source/profile/model/listening-pack hashes bind the run. Changing identities or settings requires a new experiment.

Speaker matching uses individual detected speech windows of three to eight seconds. Short and overlapping windows retain unverified anonymous grouping or uncertainty. It never assumes a whole historical group belongs to the owner. Three separate enrolled-reference template matches, a provisional similarity floor and a margin over explicitly labelled other voices constrain candidates. The current low-RMS reference subset is provisional; lower amplitude does not guarantee clean speech. Other labels retain the previous whole-shift grouping, rather than restarting numbering per file. Different labels can represent one person, and one old group can contain multiple people.

Listening labels constrain this experiment. Counts on these selected examples are not independent validation, probabilities or population accuracy estimates. Mixed/unsure examples are never binary negatives. Candidate owner labels remain explicitly unverified. The optional owner name is a local display setting, not a confirmed identity or permanent coworker/client roster.

Results refresh after each recording:

- `READABLE_RESULTS/Results.html`: complete readable transcript, progress, ASR warnings, original offsets and clickable audio timestamps. Open the actual file in a browser.
- `READABLE_RESULTS/Transcript.md`: portable readable text.
- Workspace `progress.json`, `calibration.json` and independent recording checkpoints: private diagnostics and resume state.

The saved Whisper wording is preserved, including repetitions and uncertainty. Files without usable parsed timestamps show their available raw ASR text separately, without invented timing or speaker assignments. This does not bypass the normal ASR review gate or make those files eligible for knowledge extraction.

Resume with the identical `run` command. Matching checkpoints are reused; recording attempts are bounded. Interruptions preserve completed work and update progress. A transcript-only run does not resume paused extraction workers or the normal service. Use `report WORKSPACE` to refresh readable files without inference. No result is production identity recognition until real listening review supports that claim.
