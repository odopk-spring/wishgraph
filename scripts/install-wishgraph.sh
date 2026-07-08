#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Install the WishGraph skill without cloning the whole repository by hand.

Usage:
  install-wishgraph.sh codex [--force]
  install-wishgraph.sh claude-user [--force]
  install-wishgraph.sh claude-project [--force]

Targets:
  codex          Install to ${CODEX_HOME:-$HOME/.codex}/skills/wishgraph
  claude-user    Install to ~/.claude/skills/wishgraph
  claude-project Install to ./.claude/skills/wishgraph in the current project

Environment:
  WISHGRAPH_REPO_URL  Defaults to https://github.com/odopk-spring/wishgraph.git
  WISHGRAPH_REF       Defaults to main
USAGE
}

target="${1:-}"
if [[ -z "$target" || "$target" == "-h" || "$target" == "--help" ]]; then
  usage
  exit 0
fi
shift || true

force=0
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_url="${WISHGRAPH_REPO_URL:-https://github.com/odopk-spring/wishgraph.git}"
repo_ref="${WISHGRAPH_REF:-main}"

case "$target" in
  codex)
    dest="${CODEX_HOME:-$HOME/.codex}/skills/wishgraph"
    ;;
  claude-user)
    dest="$HOME/.claude/skills/wishgraph"
    ;;
  claude-project)
    dest="$(pwd)/.claude/skills/wishgraph"
    ;;
  *)
    echo "Unknown target: $target" >&2
    usage >&2
    exit 2
    ;;
esac

if [[ -e "$dest" ]]; then
  if [[ "$force" -eq 1 ]]; then
    rm -rf "$dest"
  else
    echo "Destination already exists: $dest" >&2
    echo "Re-run with --force to replace it." >&2
    exit 1
  fi
fi

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

git clone --depth 1 --filter=blob:none --sparse --branch "$repo_ref" "$repo_url" "$tmpdir" >/dev/null
git -C "$tmpdir" sparse-checkout set skills/wishgraph >/dev/null

mkdir -p "$(dirname "$dest")"
cp -R "$tmpdir/skills/wishgraph" "$dest"

echo "Installed WishGraph skill to $dest"
echo "Restart your agent tool if it does not pick up new skills immediately."
