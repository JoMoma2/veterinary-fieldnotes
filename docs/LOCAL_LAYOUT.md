# Local FieldNotes folder

The owner installation uses `~/FieldNotes/`. Open **Start.html** in that folder for the private report links and folder guide.

After a clean slate, historical data/report folders may be absent. The active library and Morning Report can be empty while old recordings/transcripts/results remain in a locked external quarantine. The owner explicitly authorized that storage exception; it is outside normal FieldNotes discovery. Use the private current handoff and restore manifest, never archived worker instructions, to determine what was actually moved and what remains pending approval. Shared Ollama and protected operational files must not be assumed retired. Development source/tests and Git history remain recoverable.

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

The former source, reports, configuration and hidden data shortcuts have been removed at the owner's request. All actual data stays in the hub. The application translates known old FieldNotes path prefixes at filesystem access using `locations.local_path`; it does not rewrite serialized clinical evidence, frozen profiles, source/model bindings or request fingerprints. Existing saved JSON/settings can therefore contain historical path strings without requiring home-folder shortcuts. Use canonical paths in new commands; the old shell directories and executable paths no longer exist. Do not recreate the shortcuts.

The installed Whisper ELF library search paths use `$ORIGIN`, so its executable and libraries work from their new directory without an old AI-folder shortcut. Historical ASR comparison executable checksums remain historical; new ASR configuration comparisons should use a fresh workspace, preserving old results.
Ubuntu still discovers user units through `~/.config/systemd/user/` and launchers through `~/.local/share/applications/`. Unit definitions there point into `config/systemd/`. Desktop definitions remain in `config/desktop/`, with small native copies in Ubuntu's applications directory: GNOME can retain stale commands when these entries are symlinks. Shared Ollama model storage, GPU drivers, system Python/uv interpreters, browser caches and general account credentials remain in their standard locations. They may be used by other applications and are not FieldNotes-owned data.

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

Check the private handoff for current processing and USB-polling state; historical organization pauses do not override later owner authorization. Read-only review can run while processing is paused. This layout grants no deletion, publication or clinical cloud-storage permission.

The **Fieldnotes — Morning Review** application starts only the selected read-only viewer, waits for its HTTP page to become ready, and opens the desktop browser. It does not start processing or publish anything. The private `maintenance/launchers/morning-review.log` records launch stages and error classes without report URLs or clinical content. An opening failure displays a message instead of silently disappearing. `config/active-review.json` may select an existing private workspace and a FieldNotes review service. The launcher validates both and never accepts a processing service as the viewer.

The current desktop entry ID is `vet-fieldnotes-morning-review.desktop` (visible name unchanged). Retire the obsolete `vet-fieldnotes-review.desktop` entry when updating an existing installation. Browser launch output goes to the null device: capturing it can hang when a browser child inherits the output pipes. This does not affect report data or model jobs.
