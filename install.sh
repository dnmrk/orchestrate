#!/usr/bin/env bash
# Symlinks this skill's subagents into ~/.claude/agents and its guard hook into ~/.claude/hooks.
# Expects the repo at ~/.claude/skills/orchestrate.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ "$here" = "$HOME/.claude/skills/orchestrate" ] || echo "warning: SKILL.md expects ~/.claude/skills/orchestrate, repo is at $here" >&2
mkdir -p "$HOME/.claude/agents"
for f in "$here"/agents/*.md; do
  ln -sfn "$f" "$HOME/.claude/agents/$(basename "$f")"
  echo "linked $(basename "$f")"
done
mkdir -p "$HOME/.claude/hooks"
ln -sfn "$here/hooks/orchestrate-guard.sh" "$HOME/.claude/hooks/orchestrate-guard.sh"
echo "linked orchestrate-guard.sh"
# Registering the hook edits the human's settings, so only check it.
grep -qs 'orchestrate-guard.sh' "$HOME/.claude/settings.json" || cat >&2 <<'EOF'
warning: the guard hook is not registered. Add to ~/.claude/settings.json under "hooks":
  "PreToolUse": [{ "matcher": "Bash|Write|Edit|NotebookEdit",
    "hooks": [{ "type": "command", "command": "bash \"$HOME/.claude/hooks/orchestrate-guard.sh\"", "timeout": 10 }] }]
EOF
grep -qs '"impeccable@' "$HOME/.claude/plugins/installed_plugins.json" || cat >&2 <<'EOF2'
warning: the impeccable plugin is not installed; the designer step requires it. Run:
  claude plugin marketplace add pbakaus/impeccable && claude plugin install impeccable@impeccable
EOF2
