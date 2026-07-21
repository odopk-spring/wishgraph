#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Install the WishGraph skill without cloning the whole repository by hand.

Usage:
  install-wishgraph.sh codex [--force] [--setup-project] [--project PATH] [--project-hosts HOSTS] [--strict] [--check]
  install-wishgraph.sh claude-user [--force] [--setup-project] [--project PATH] [--project-hosts HOSTS] [--strict] [--check]
  install-wishgraph.sh claude-project [--force] [--setup-project] [--project PATH] [--project-hosts HOSTS] [--strict] [--check]

Targets:
  codex          Install to ${CODEX_HOME:-$HOME/.codex}/skills/wishgraph
  claude-user    Install to ~/.claude/skills/wishgraph
  claude-project Install to ./.claude/skills/wishgraph in the current project

Project setup:
  --setup-project  Also install memory-sync hooks into the current project
  --project PATH   Install memory-sync hooks into PATH instead of the current project
  --project-hosts  Project-managed hosts: all (recommended default), codex, or claude
  --strict         Use enforce mode plus a Git pre-commit fallback; requires project setup
  --check          Check prerequisites and estimated cost without installing

Examples:
  install-wishgraph.sh codex
  install-wishgraph.sh codex --setup-project
  install-wishgraph.sh codex --setup-project --project-hosts codex
  install-wishgraph.sh claude-user --project /path/to/project
  install-wishgraph.sh codex --setup-project --strict

Environment:
  WISHGRAPH_REPO_URL  Defaults to https://github.com/odopk-spring/wishgraph.git
  WISHGRAPH_REF       Defaults to v0.1.0; set main only for development snapshots
USAGE
}

print_git_help() {
  echo "Git is required by this installer and by project memory checks." >&2
  case "$(uname -s 2>/dev/null || true)" in
    Darwin)
      echo "Install: xcode-select --install" >&2
      echo "Estimate: about 1-3 GB and 5-30 minutes for Apple Command Line Tools." >&2
      echo "If Homebrew already exists, 'brew install git' is usually smaller and faster." >&2
      ;;
    Linux)
      echo "Install: 'sudo apt install git', 'sudo dnf install git', or 'sudo pacman -S git'." >&2
      echo "Estimate: commonly 200-500 MB and 2-10 minutes." >&2
      ;;
    *)
      echo "Install from https://git-scm.com/downloads" >&2
      echo "Estimate: commonly 200-500 MB and 2-10 minutes." >&2
      ;;
  esac
}

find_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

print_python_help() {
  echo "Project hooks require Python 3.9 or newer; no third-party packages are needed." >&2
  case "$(uname -s 2>/dev/null || true)" in
    Darwin)
      echo "Install: brew install python, or use https://www.python.org/downloads/macos/" >&2
      ;;
    Linux)
      echo "Install: 'sudo apt install python3', 'sudo dnf install python3', or 'sudo pacman -S python'." >&2
      ;;
    *)
      echo "Install from https://www.python.org/downloads/" >&2
      ;;
  esac
  echo "Estimate: commonly 100-300 MB and 2-10 minutes." >&2
}

target="${1:-}"
if [[ -z "$target" || "$target" == "-h" || "$target" == "--help" ]]; then
  usage
  exit 0
fi
shift || true

force=0
setup_project=0
strict=0
check_only=0
project_dir="$(pwd)"
project_hosts="all"
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --force)
      force=1
      ;;
    --setup-project)
      setup_project=1
      ;;
    --project)
      if [[ "$#" -lt 2 ]]; then
        echo "--project requires a path." >&2
        exit 2
      fi
      project_dir="$2"
      setup_project=1
      shift
      ;;
    --project-hosts)
      if [[ "$#" -lt 2 ]]; then
        echo "--project-hosts requires all, codex, or claude." >&2
        exit 2
      fi
      case "$2" in
        all|codex|claude) project_hosts="$2" ;;
        *)
          echo "Unknown project host selection: $2" >&2
          exit 2
          ;;
      esac
      shift
      ;;
    --strict)
      strict=1
      ;;
    --check)
      check_only=1
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$strict" -eq 1 && "$setup_project" -eq 0 ]]; then
  echo "--strict requires --setup-project or --project PATH." >&2
  exit 2
fi

case "$target" in
  codex|claude-user|claude-project) ;;
  *)
    echo "Unknown target: $target" >&2
    usage >&2
    exit 2
    ;;
esac

echo "WishGraph installs source files only, adds no Python packages, and usually takes under 1 minute."
if [[ "$setup_project" -eq 1 ]]; then
  echo "Project runtime setup usually takes under 10 seconds."
fi
echo "Installation stage 1: checking prerequisites."

preflight_failed=0
if ! command -v git >/dev/null 2>&1; then
  print_git_help
  preflight_failed=1
fi

python_bin=""
if [[ ( "$setup_project" -eq 1 || "$target" != "claude-project" ) && "$preflight_failed" -eq 0 ]]; then
  if ! python_bin="$(find_python)"; then
    print_python_help
    preflight_failed=1
  fi
fi
if [[ "$setup_project" -eq 1 && "$preflight_failed" -eq 0 ]]; then
  if [[ ! -d "$project_dir" ]]; then
    echo "Project directory does not exist: $project_dir" >&2
    preflight_failed=1
  fi
  if [[ "$preflight_failed" -eq 0 ]]; then
    if detected_root="$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null)"; then
      if [[ "$detected_root" != "$project_dir" ]]; then
        echo "Using detected Git repository root: $detected_root"
      fi
      project_dir="$detected_root"
    else
      echo "Project hooks need a Git repository, but $project_dir is not inside one." >&2
      echo "Run 'git init' there, or ask your agent to initialize Git, then retry." >&2
      echo "Estimate: under 1 MB and normally under a second." >&2
      preflight_failed=1
    fi
  fi
fi

if [[ "$preflight_failed" -ne 0 ]]; then
  echo "Nothing was installed. Resolve the items above, reopen the terminal if needed, and retry." >&2
  exit 3
fi

if [[ "$check_only" -eq 1 ]]; then
  echo "Prerequisite check passed. Nothing was installed."
  exit 0
fi

repo_url="${WISHGRAPH_REPO_URL:-https://github.com/odopk-spring/wishgraph.git}"
repo_ref="${WISHGRAPH_REF:-v0.1.0}"

case "$target" in
  codex)
    dest="${CODEX_HOME:-$HOME/.codex}/skills/wishgraph"
    ;;
  claude-user)
    dest="$HOME/.claude/skills/wishgraph"
    ;;
  claude-project)
    dest="$project_dir/.claude/skills/wishgraph"
    ;;
  *)
    echo "Unknown target: $target" >&2
    usage >&2
    exit 2
    ;;
esac

reuse_existing=0
if [[ -e "$dest" ]]; then
  if [[ "$force" -eq 1 ]]; then
    # Keep the working installation until the replacement is downloaded and
    # passes the minimum layout validation below.
    :
  elif [[ "$setup_project" -eq 1 && -f "$dest/scripts/install_project_hooks.py" ]]; then
    reuse_existing=1
    echo "WishGraph skill already exists at $dest; reusing it for project setup."
  else
    echo "Destination already exists: $dest" >&2
    echo "Re-run with --force to replace it." >&2
    exit 1
  fi
fi

if [[ "$reuse_existing" -eq 0 ]]; then
  echo "Installation stage 2: installing the WishGraph Skill."
  tmpdir="$(mktemp -d)"
  cleanup() {
    rm -rf "$tmpdir"
  }
  trap cleanup EXIT

  git clone --depth 1 --filter=blob:none --sparse --branch "$repo_ref" "$repo_url" "$tmpdir" >/dev/null
  git -C "$tmpdir" sparse-checkout set skills/wishgraph >/dev/null

  staged_skill="$tmpdir/skills/wishgraph"
  for required in VERSION SKILL.md scripts/install_project_hooks.py; do
    if [[ ! -f "$staged_skill/$required" ]]; then
      echo "Downloaded WishGraph Skill is incomplete: missing $required" >&2
      exit 1
    fi
  done

  mkdir -p "$(dirname "$dest")"
  backup=""
  if [[ -e "$dest" ]]; then
    backup="${dest}.wishgraph-backup.$$"
    mv "$dest" "$backup"
  fi
  if ! mv "$staged_skill" "$dest"; then
    rm -rf "$dest"
    if [[ -n "$backup" && -e "$backup" ]]; then
      mv "$backup" "$dest"
    fi
    echo "WishGraph Skill replacement failed; the previous installation was restored." >&2
    exit 1
  fi
  if [[ -n "$backup" && -e "$backup" ]]; then
    rm -rf "$backup"
  fi

  echo "Installed WishGraph skill to $dest"
  echo "Restart your agent tool if it does not pick up new skills immediately."
fi

if [[ "$target" == "claude-user" || "$target" == "claude-project" ]]; then
  agent_source="$dest/assets/claude-agents/wishgraph-worker.md"
  if [[ "$target" == "claude-user" ]]; then
    agent_dest="$HOME/.claude/agents/wishgraph-worker.md"
  else
    agent_dest="$project_dir/.claude/agents/wishgraph-worker.md"
  fi
  if [[ -f "$agent_dest" ]] && ! grep -Fq '<!-- wishgraph-managed: wishgraph-worker -->' "$agent_dest"; then
    echo "Refusing to replace non-WishGraph Claude Agent: $agent_dest" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$agent_dest")"
  cp "$agent_source" "$agent_dest"
  echo "Installed WishGraph Claude Worker Agent to $agent_dest"
fi

if [[ "$target" == "codex" || "$target" == "claude-user" ]]; then
  global_host="codex"
  if [[ "$target" == "claude-user" ]]; then
    global_host="claude"
  fi
  "$python_bin" "$dest/scripts/install_global_adapter.py" --host "$global_host"
fi

if [[ "$setup_project" -eq 1 ]]; then
  echo "Installation stage 3: configuring project hooks."
  case "$target" in
    codex) hook_host="codex" ;;
    claude-user|claude-project) hook_host="claude" ;;
  esac

  hook_mode="warn"
  if [[ "$strict" -eq 1 ]]; then
    hook_mode="enforce"
  fi

  set -- \
    "$python_bin" "$dest/scripts/install_project_hooks.py" \
    --target "$project_dir" \
    --host "$project_hosts" \
    --current-host "$hook_host" \
    --mode "$hook_mode"
  if [[ "$force" -eq 1 ]]; then
    set -- "$@" --force-assets
  fi
  if [[ "$strict" -eq 1 ]]; then
    set -- "$@" --git-hook
  fi
  "$@"

fi
