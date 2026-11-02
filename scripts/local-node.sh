#!/usr/bin/env bash
# Use a current Node runtime without changing the system Node installation or shell configuration.
set -euo pipefail
if ! node -e 'const [a,b,c]=process.versions.node.split(".").map(Number);process.exit(a>22 || (a===22 && (b>23 || b===23&&c>=4)) ? 0 : 1)' 2>/dev/null; then
  task_toolchain="${XDG_DATA_HOME:-$HOME/.local/share}/vet-fieldnotes-toolchain"
  if [ ! -x "$task_toolchain/node_modules/.bin/node" ]; then
    npm install --prefix "$task_toolchain" node@24 npm@11 --no-audit --no-fund
  fi
  export PATH="$task_toolchain/node_modules/.bin:$PATH"
fi
exec npm "$@"
