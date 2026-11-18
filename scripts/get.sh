#!/bin/sh
# One-line install/update:  curl -fsSL https://raw.githubusercontent.com/minigu5/ai-api/main/scripts/get.sh | sh
set -eu
dest="${LOCAL_AGENT_DIR:-$HOME/.local/share/ai-api}"
tarball="${LOCAL_AGENT_TARBALL:-https://codeload.github.com/minigu5/ai-api/tar.gz/refs/heads/main}"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$tarball" | tar -xz -C "$tmp" --strip-components=1
mkdir -p "$(dirname "$dest")"
rm -rf "$dest"
mv "$tmp" "$dest"
trap - EXIT
exec "$dest/scripts/install.sh"
