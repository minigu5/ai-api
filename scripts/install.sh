#!/bin/sh
# Install Python, Node and pi (if missing), link the local-agent command and Claude Code skill, then set up the token, CA and pi models.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)

# Pinned runtimes, installed under $rt without admin rights; bin/local-agent puts them first on PATH.
PY_VER=3.12.16 PY_TAG=20261110
PY_SHA=e956e60bc9465d577ef8062059aa05cd3a2665b4b8678a2ed24e432368330b8f
NODE_VER=v22.23.5
NODE_SHA=e7131995759b61a0170b646010d2ad35a5d37b4cb0d471f3e8317eac6f742f3d
PI_VER=1.0.0
rt="${LOCAL_AGENT_RUNTIME:-$HOME/.local/share/ai-api-runtime}"

download() {  # download <url> <sha256> <dest dir> -- unpack a verified tarball, dropping its top folder
  tmp=$(mktemp -d)
  curl -fsSL "$1" -o "$tmp/pkg.tgz"
  if [ "$(shasum -a 256 "$tmp/pkg.tgz" | cut -d' ' -f1)" != "$2" ]; then
    rm -rf "$tmp"; echo "stop: checksum mismatch for $1" >&2; exit 1
  fi
  rm -rf "$3"; mkdir -p "$3"
  tar -xzf "$tmp/pkg.tgz" -C "$3" --strip-components=1
  rm -rf "$tmp"
}

ensure_runtime() {
  if [ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]; then
    echo "stop: the one-step runtime install supports Apple Silicon Macs only; install Python 3.10+, Node 22.19+ and pi yourself" >&2
    exit 1
  fi
  want="python $PY_VER-$PY_TAG node $NODE_VER pi $PI_VER"
  if [ "$(cat "$rt/versions" 2>/dev/null)" = "$want" ]; then echo "ok: $rt"; return; fi
  echo "installing Python, Node and pi into $rt (about 100 MB)..."
  mkdir -p "$rt"; rm -f "$rt/versions"
  download "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_TAG/cpython-$PY_VER%2B$PY_TAG-aarch64-apple-darwin-install_only.tar.gz" "$PY_SHA" "$rt/python"
  download "https://nodejs.org/dist/$NODE_VER/node-$NODE_VER-darwin-arm64.tar.gz" "$NODE_SHA" "$rt/node"
  PATH="$rt/node/bin:$PATH" "$rt/node/bin/npm" install -g --prefix "$rt/pi" --no-fund --no-audit "@earendil-works/pi-coding-agent@$PI_VER"
  echo "$want" > "$rt/versions"
}

ensure_path() {  # ~/.local/bin is not on a new Mac's PATH, so Claude Code could not find local-agent
  case ":$PATH:" in *":$HOME/.local/bin:"*) return;; esac
  if ! grep -qs "# ai-api" "$HOME/.zshrc"; then
    printf '\nexport PATH="$HOME/.local/bin:$PATH"  # ai-api\n' >> "$HOME/.zshrc"
    echo "added ~/.local/bin to PATH in ~/.zshrc (open a new terminal or Claude Code window)"
  fi
}

ensure_runtime

link() {  # link <target> <link path>
  if [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]; then
    echo "ok: $2"
  elif [ -e "$2" ] || [ -L "$2" ]; then
    echo "stop: $2 already exists and is not a link to $1; move it away and run again" >&2
    exit 1
  else
    mkdir -p "$(dirname "$2")"
    ln -s "$1" "$2"
    echo "linked: $2 -> $1"
  fi
}

link "$repo/bin/local-agent" "$HOME/.local/bin/local-agent"
link "$repo/skills/local-agent" "$HOME/.claude/skills/local-agent"

ensure_path
"$repo/bin/local-agent" --setup
