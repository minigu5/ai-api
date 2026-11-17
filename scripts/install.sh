#!/bin/sh
# Link the local-agent command and the Claude Code skill into the user's folders.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)

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
