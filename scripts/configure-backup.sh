#!/usr/bin/env bash
set -eu
umask 077
VET_ROOT="${FIELDNOTES_HOME:-$HOME/FieldNotes}"
VET_RCLONE="$VET_ROOT/tools/maintenance/rclone"
VET_BACKUP_CONFIG="$VET_ROOT/config/rclone.conf"
mkdir -p "$(dirname "$VET_BACKUP_CONFIG")"
chmod 700 "$(dirname "$VET_BACKUP_CONFIG")"
# Interactive secrets stay in your local terminal/config; never paste them into chat.
exec "$VET_RCLONE" --config "$VET_BACKUP_CONFIG" config
