#!/usr/bin/env bash
# PreToolUse guard for the /orchestrate pipeline agents (architect, designer, engineer, qa).
# Blocks outward-facing or irreversible commands; those stay the human's call.
# Other sessions and agents pass through untouched.
# Input: hook JSON on stdin. Block: exit 2 with the reason on stderr.
set -u
input=$(cat)
agent=$(printf '%s' "$input" | jq -r '.agent_type // empty')
case "$agent" in architect|designer|engineer|qa) ;; *) exit 0 ;; esac
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')

block() { echo "orchestrate-guard: '$agent' may not $1. Stop and report it as an open item for the human." >&2; exit 2; }

# Separation of duties: only the engineer edits the project. QA writes its reports;
# the architect writes the plan (tasks/todo.md) and its workspace; the designer only its workspace.
if [ "$tool" = "Write" ] || [ "$tool" = "Edit" ] || [ "$tool" = "NotebookEdit" ]; then
  [ "$agent" = "engineer" ] && exit 0
  path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')
  case "$path" in */.orchestrate/*) exit 0 ;; esac
  [ "$agent" = "architect" ] && case "$path" in */tasks/todo.md) exit 0 ;; esac
  block "edit $path (only the engineer changes project files)"
fi
[ "$tool" = "Bash" ] || exit 0
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')

# Word-boundary style matches, case-insensitive for SQL.
grep -Eq '(^|[;&|[:space:]])git[[:space:]]+push([[:space:]]|$)' <<<"$cmd" && block "push"
grep -Eq '(^|[;&|[:space:]])gh[[:space:]]+(pr[[:space:]]+(merge|create|close|ready|review)|release|repo[[:space:]]+(delete|edit)|workflow[[:space:]]+run)' <<<"$cmd" && block "change PRs, releases or repos on GitHub"
grep -Eq '(^|[;&|[:space:]])gh[[:space:]]+api[[:space:]].*(-X|--method)[[:space:]]*(POST|PUT|PATCH|DELETE)' <<<"$cmd" && block "write through the GitHub API"
grep -Eq 'git[[:space:]]+(reset[[:space:]]+--hard|clean[[:space:]]+-[a-z]*f|checkout[[:space:]]+--[[:space:]]+\.|branch[[:space:]]+-D|rebase)' <<<"$cmd" && block "discard or rewrite git history/work"
grep -Eq '(-e|--environment)[[:space:]=]+prod(uction)?\b|--prod\b|--env[= ]prod\b|APP_ENV=prod' <<<"$cmd" && block "run against production"
grep -Eq '(^|[;&|[:space:]])(vercel[[:space:]]+(deploy|promote|rollback|env[[:space:]]+(add|rm|pull))|npm[[:space:]]+publish|terraform[[:space:]]+(apply|destroy)|kubectl[[:space:]]+(apply|delete)|fly[[:space:]]+deploy)' <<<"$cmd" && block "deploy or publish"
grep -Eiq '\b(drop[[:space:]]+(table|database|schema)|truncate[[:space:]]+table)\b' <<<"$cmd" && block "drop or truncate data"
grep -Eq 'rm[[:space:]]+-[a-zA-Z]*r[a-zA-Z]*f?[[:space:]]+(/|~|\$HOME)([[:space:]]|$)' <<<"$cmd" && block "delete outside the project"
exit 0
