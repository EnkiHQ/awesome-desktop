#!/bin/sh
# Install the desktop character and put it on screen (macOS / Linux).
#   curl -LsSf https://raw.githubusercontent.com/EnkiHQ/awesome-desktop/main/pet/install.sh | sh
set -e
SOURCE="awesome-desktop @ https://github.com/EnkiHQ/awesome-desktop/archive/refs/heads/main.zip"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi
uv tool install --force "$SOURCE"
BIN="$(uv tool dir --bin)"
"$BIN/awesome-pet" start "$@"
