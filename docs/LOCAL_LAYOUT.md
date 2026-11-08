# Local FieldNotes folder

The owner installation uses `~/FieldNotes/`. Open **Start.html** in that folder for the private report links and folder guide.

| Folder | Contents |
| --- | --- |
| `app/` | Public application Git checkout, source, documentation and tests |
| `data/library/` | Current private processing workspace, ledger, retained original WAVs in `inputs/`, full transcripts in `transcripts/`, raw ASR in `transcription-details/`, checkpoints and publication candidates |
| `data/evaluations/` | Isolated AI, speaker and owner-reference experiments; private continuation notes |
| `data/archives/` | Preserved prior runs and resets |
| `data/validation/` | Local synthetic validation workspaces |
| `data/workspace/` | Earlier default CLI workspace; kept separate from the active library |
| `data/device-settings/`, `data/repairs/` | Recorder-setting records and repair history |
| `reports/` | Owner-facing offline summaries, transcripts and listening comparisons |
| `config/` | Private pipeline profile and OS registration definitions |
| `ai/` | Project-local Whisper build, models, tokenizers and isolated speaker environment |
| `tools/` | Project Node runtime, backup tools and setup records |
| `repositories/master/` | Dedicated private master Git checkout; remote clinical storage still requires authorization |
| `inbox/` | Imported owner annotation/download files |
| `maintenance/` | Private migration journal, integrity checks and service-definition backups |

Do not initialize Git in the hub root. Clinical data, full transcripts, recordings, voice vectors, annotations and capability URLs must never be added to `app/` or published. The separate master checkout accepts only content allowed by its existing clinical storage gates; moving it grants no new upload permission.

## Compatibility and required external locations

The former source, reports, configuration and hidden data paths remain as filesystem symlinks. Their data now lives in the hub. This preserves old bookmarks, saved absolute paths, editable environment imports and hash-bound recovery artifacts. **Do not remove these compatibility links** until a deliberate migration proves no saved checkpoint uses them. Immutable model manifests, experiment settings, original reports and old request fingerprints are not rewritten merely to replace a valid path.

Ubuntu still discovers user units through `~/.config/systemd/user/` and launchers through `~/.local/share/applications/`; FieldNotes definitions there point into `config/systemd/` and `config/desktop/`. Shared Ollama model storage, GPU drivers, system Python/uv interpreters, browser caches and general account credentials remain in their standard locations. They may be used by other applications and are not FieldNotes-owned data.

## Working here

```bash
cd ~/FieldNotes/app
pipeline/.venv/bin/python -m pytest pipeline/tests
npm run check
npm test
npm run build
```

Use the installed project Node runtime if your shell's Node is too old:

```bash
export PATH="$HOME/FieldNotes/tools/runtime/node_modules/node/bin:$HOME/FieldNotes/tools/runtime/node_modules/.bin:$PATH"
```

Python helpers use `FIELDNOTES_HOME` when supplied, otherwise `~/FieldNotes`. New CLI work defaults to `data/workspace/`; the unattended service explicitly uses `data/library/`. Select isolated new experiments under `data/evaluations/`. Do not change an in-progress experiment's fingerprinted paths or configuration in place. Refresh the local start page with `pipeline/.venv/bin/python scripts/build-local-home.py`. The page is generated only in the private hub and is never a website build input.

Systemd templates target the standard `~/FieldNotes` installation; a custom hub location also requires editing those owner-local units.

The organization task preserves the operator pause: processing and USB polling stay stopped. The read-only review services can be active while processing is paused. Nothing in this layout enables deletion, public publication or clinical cloud storage.
