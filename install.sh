#!/usr/bin/env bash
# Symlinks this skill's subagents into ~/.claude/agents. Expects the repo at ~/.claude/skills/orchestrate.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ "$here" = "$HOME/.claude/skills/orchestrate" ] || echo "warning: SKILL.md expects ~/.claude/skills/orchestrate, repo is at $here" >&2
mkdir -p "$HOME/.claude/agents"
for f in "$here"/agents/*.md; do
  ln -sfn "$f" "$HOME/.claude/agents/$(basename "$f")"
  echo "linked $(basename "$f")"
done
