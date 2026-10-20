# orchestrate

Claude Code skill: `/orchestrate` runs a change through Architect → Designer (UI changes only, via impeccable) → Engineer → QA subagents. See `SKILL.md`.

## Install

```bash
git clone git@github.com:dnmrk/orchestrate.git ~/.claude/skills/orchestrate
~/.claude/skills/orchestrate/install.sh   # symlinks agents/*.md into ~/.claude/agents
```

The path matters: `SKILL.md` references `~/.claude/skills/orchestrate/scripts/orch`. Update with `git pull`.
