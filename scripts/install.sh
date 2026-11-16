#!/bin/bash
# clipsdaily copy-installer (macOS / Linux).
#
# Copies the clipsdaily skill + slash commands into your agent harness.
# This is the copy-install path (like BugHunter's scripts/install.sh).
# The recommended install is the Claude Code plugin instead:
#
#   /plugin marketplace add abelprasad/clipsdaily
#   /plugin install clipsdaily@abelprasad
#
# Usage (run from the repo root):
#   bash scripts/install.sh            # Claude Code only
#   bash scripts/install.sh --all      # Claude Code + every other detected harness
#   bash scripts/install.sh --help
#
# --all copies the SKILL (not the commands) to each detected harness:
#   Claude Code   ~/.claude/skills
#   OpenCode/Codex ~/.agents/skills
#   Hermes        ~/.hermes/skills
#   Gemini        ~/.gemini/config/skills
# A harness counts as detected when its binary is on PATH or its home
# directory already exists. Slash commands stay Claude-Code-only by
# design — other harnesses don't share the command format.
#
# Idempotent: re-running it replaces the installed copy.
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ALL=0

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "usage: bash scripts/install.sh [--all]"
    echo "  (no flag)  Claude Code only (~/.claude/skills + ~/.claude/commands)"
    echo "  --all      also copy the skill to every detected harness"
    exit 0
fi
[ "${1:-}" = "--all" ] && ALL=1
[ -n "${1:-}" ] && [ "${1:-}" != "--all" ] && { echo "unknown option: $1 (try --help)" >&2; exit 1; }

install_skill() {
    # $1 = skills root dir (e.g. ~/.claude/skills)
    mkdir -p "$1"
    rm -rf "$1/clipsdaily"
    cp -r "$REPO_DIR/skills/clipsdaily" "$1/clipsdaily"
    echo "  skill -> $1/clipsdaily"
}

install_commands() {
    # Claude Code only. Namespaced under commands/clipsdaily/ so the
    # commands are invoked as /clipsdaily:run, /clipsdaily:post, etc.
    mkdir -p "$HOME/.claude/commands/clipsdaily"
    rm -rf "$HOME/.claude/commands/clipsdaily"
    cp -r "$REPO_DIR/plugins/clipsdaily/commands" "$HOME/.claude/commands/clipsdaily"
    echo "  commands -> $HOME/.claude/commands/clipsdaily"
}

echo "== clipsdaily copy-install (Claude Code) =="
install_skill "$HOME/.claude/skills"
install_commands

if [ "$ALL" = 1 ]; then
    echo "== --all: detected harnesses =="
    # OpenCode / Codex
    if command -v opencode >/dev/null 2>&1 || command -v codex >/dev/null 2>&1 || [ -d "$HOME/.agents" ]; then
        install_skill "$HOME/.agents/skills"
    else
        echo "  OpenCode/Codex: not detected, skipped"
    fi
    # Hermes
    if command -v hermes >/dev/null 2>&1 || [ -d "$HOME/.hermes" ]; then
        install_skill "$HOME/.hermes/skills"
    else
        echo "  Hermes: not detected, skipped"
    fi
    # Gemini
    if command -v gemini >/dev/null 2>&1 || [ -d "$HOME/.gemini" ]; then
        install_skill "$HOME/.gemini/config/skills"
    else
        echo "  Gemini: not detected, skipped"
    fi
fi

echo "Done. Restart Claude Code (or your harness) to pick up the skill."
echo "Slash commands: /clipsdaily:run /clipsdaily:post /clipsdaily:queue"
echo "  /clipsdaily:campaign /clipsdaily:submit /clipsdaily:earnings /clipsdaily:status"
