# Optional independent encrypted backup setup

The organized installation lives in `~/FieldNotes/`; see [Local layout](LOCAL_LAYOUT.md). Historical paths in this document still work through compatibility shortcuts. Use the new layout for new work.

**Deferred by owner decision.** Normal operation uses private GitHub as primary remote knowledge storage, the local computer as secondary copy, and Cloudflare for approved public content. No independent-provider account, encryption key or rclone credentials are required for processing or GitHub synchronization. The instructions below preserve optional future functionality; do not configure or enable it automatically.

The existing backup format and immutable version uploads are retained. Rclone v1.75.2 is installed user-locally at `~/.local/share/vet-fieldnotes-tools/rclone`, with its release checksum verified. No remote account or automatic clinical upload is enabled.

## Connect Google Drive once

Use an existing Google account with sufficient free space; do not create paid storage. Current rclone guidance recommends your own OAuth client because its shared Drive client is being retired in 2026. [Official Drive setup](https://rclone.org/drive/#making-your-own-client-id).

1. In Google Cloud Console, create/select a project, enable the **Google Drive API**, and configure its OAuth consent screen. No billing connection is needed for this setup.
2. Create an OAuth client of type **Desktop app**. Keep its JSON/client secret outside both repositories, preferably under `~/.config/vet-fieldnotes/` with mode 600. Never paste client secrets or access tokens into chat.
3. For personal testing, add your own Google account as a test user. Before relying on unattended refresh, resolve the consent application's publishing status: external apps left in Testing normally receive seven-day refresh tokens for Drive scopes. [Google token-expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration). Do not mistake one successful login for years of unattended authorization.
4. In your own terminal, from the project checkout, run:

```bash
./scripts/configure-backup.sh
```

Create a new remote named **vet-backup-drive**, storage type **drive**. Enter your own client ID/secret in the local interactive prompts. Set scope to **drive.file**, which limits access to files created/opened by the app rather than all Drive files. Use browser authentication; choose no shared/team drive unless that is deliberately your intended destination. Keep the encryption key out of this remote.

The script uses only `~/.config/vet-fieldnotes/rclone.conf`, leaving other rclone configurations untouched. Protect that directory/file with modes 700/600. Confirm names only, without printing tokens:

```bash
~/.local/share/vet-fieldnotes-tools/rclone \
  --config ~/.config/vet-fieldnotes/rclone.conf listremotes
```

If you prefer another provider, configure that backend interactively and change the remote name in a private copy of `config/backup-drive.example.toml`. Do not turn on clinical storage merely because authentication succeeds.

## Verify actual independent storage and restoration

After authentication, copy `config/backup-drive.example.toml` outside Git and run:

```bash
cp -n config/backup-drive.example.toml ~/.config/vet-fieldnotes/backup.toml
chmod 600 ~/.config/vet-fieldnotes/backup.toml
uv run --project pipeline python scripts/backup-drill.py \
  --config ~/.config/vet-fieldnotes/backup.toml \
  --directory ~/.local/share/vet-fieldnotes-validation/independent-backup-001
```

This uploads **only two encrypted synthetic library versions** to a unique remote drill folder. It checks remote bytes, makes the source workspace/local backups unavailable by renaming their test directories, downloads each version from the provider, decrypts/verifies every file and restores into new replacement directories. Older remote versions are never overwritten or synchronized away. It never uploads an encryption key or deletes remote files.

`restore-drill.json` records actual results. A local filesystem remote or mocked transfer is an adapter test, **not independent-cloud durability**. Until a real provider is authenticated and this drill passes, independent backup remains unverified.

## Key custody before real reliance

Losing the Fernet key makes these backups unrecoverable. Keep the production key mode 600 outside Git and **a second recoverable copy off this computer**, for example in an independently accessible password manager or an encrypted removable drive stored separately. Keep account/2FA recovery access too. Never upload the key beside its backups or paste it into chat. Test the recovery copy, not merely the key still on this computer.

Retain access to the OAuth client/project as well. A replacement Drive client using `drive.file` may not see the old application's files; recover with the original client or download the encrypted version through your authenticated Drive account and restore locally. Losing a computer must not also lose the only OAuth/client recovery information.

The drill creates a disposable synthetic recovery key outside its source workspace; that simulates replacement-workspace recovery but does **not** verify off-machine custody. Production clinical storage still needs separate authorization and `allow_clinical_remote = true` deliberately configured by the owner. Raw recordings/transcripts are not part of these permanent-library backups. No USB service or automatic deletion policy should be enabled during setup.
