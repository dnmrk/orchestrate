# orchestrate

A Claude Code skill. `/orchestrate <request>` runs a change through a pipeline of subagents:

```
Architect (Opus) → Designer (Opus, UI only) → you approve → Engineer (Haiku/Sonnet) ⇄ QA (Sonnet), per task → whole-branch QA → report
```

The main session acts as the orchestrator. It dispatches agents, passes file paths between them, keeps a ledger and talks to you. It doesn't plan, build or verify anything itself.

## Features

- **Plan before code.** The architect writes `tasks/todo.md`: impact call-outs (schema, API, auth, UI, ACL), the activation path, tasks tagged `[mechanical]` or `[judgment]` with acceptance criteria, and a mermaid flow.
- **UI design pass.** If the plan's UI call-out isn't `none`, the designer runs impeccable's *shape* workflow. It writes a checkable design spec and one static HTML mockup per screen, then the architect folds the spec into the plan as ACs.
- **One approval gate.** You see the plan digest, with the flow chart and mockups open in your browser, then choose **Approve / Revise / Stop**. Revisions go back to the same agents.
- **Model routing per task.** `[mechanical]` tasks run on Haiku and `[judgment]` tasks on Sonnet. Every dispatch sets its model explicitly, so nothing inherits the session's Opus.
- **Independent QA.** QA never sees the engineer's report. It works from the brief, the raw diff and real command runs, and sweeps every row of the failure checklist. A check marked `NOT RUN` makes the verdict BLOCKED, never PASS. Each task gets at most 2 fix rounds before it escalates to you, and a final whole-branch pass checks cross-task integration.
- **Failure checklist.** `failure-checklist.md` lists defect classes mined from real PRs and sessions (sources in `evidence.md`), such as unapplied migrations, 5xx on boundary input, and stale optimistic state. The architect maps them to ACs and QA checks them.
- **Short path.** A change touching at most 2 files, with no schema, API, auth or concurrency impact, skips the architect and designer: a 1-task plan, one engineer and one QA. See `EVAL.md` for why.
- **Guard hook.** `hooks/orchestrate-guard.sh` stops the pipeline agents from pushing, using `gh` write commands, rewriting history, deploying, running against prod or dropping data. Only the engineer may edit project files. Other sessions aren't affected.
- **Resumable.** The run state lives in `.orchestrate/<slug>/ledger.md` (git-ignored). Re-running picks up at the first unfinished step.
- **Learning loop.** Lesson candidates from QA get appended to the repo's `tasks/lessons.md`. A defect class that's new gets proposed as a checklist row.
- **Usage accounting.** Tokens per dispatch go in `.orchestrate/<slug>/usage.md` and are included in the final report.
- **Monitor UI.** `scripts/orch ui` serves a read-only local dashboard of sessions, subagents, ledgers and usage at http://127.0.0.1:7788. It uses only the Python standard library.
- **Eval mode.** `/orchestrate --eval <request>` runs unattended: it auto-approves the plan and records escalations instead of asking.

Nothing in the pipeline pushes, merges or deploys. Those steps are left for you, and at the end the orchestrator offers to push and open the PR.

## Requirements

- Claude Code with subagents and hooks
- `git`, `jq` (used by the guard hook), `python3` (used by the monitor)
- The [impeccable](https://github.com/pbakaus/impeccable) plugin, needed only for the designer step

## Install

```bash
git clone git@github.com:dnmrk/orchestrate.git ~/.claude/skills/orchestrate
~/.claude/skills/orchestrate/install.sh
```

The repo must live at `~/.claude/skills/orchestrate`, because `SKILL.md` calls `~/.claude/skills/orchestrate/scripts/orch`.

`install.sh` symlinks `agents/*.md` into `~/.claude/agents/` and the guard into `~/.claude/hooks/`. It doesn't edit your settings. If the hook isn't registered, it prints a warning. To register it, add this to `~/.claude/settings.json`:

```json
"hooks": {
  "PreToolUse": [{
    "matcher": "Bash|Write|Edit|NotebookEdit",
    "hooks": [{ "type": "command", "command": "bash \"$HOME/.claude/hooks/orchestrate-guard.sh\"", "timeout": 10 }]
  }]
}
```

Update with `git pull`. The symlinks pick up changes automatically, so you only need to re-run `install.sh` when an agent is added.

## Usage

Start from a clean working tree in the target repo:

```
/orchestrate add a water goal to the daily summary
/orchestrate --eval fix the duplicate save on retake
```

The run creates a `feat/<slug>` or `fix/<slug>` branch, commits the plan, then commits each task and the lessons. At the end you get a report with outcome, per-task verdicts, files touched, usage, and the steps left for you (push/PR, applying migrations to prod, device checks).

To watch a run live:

```bash
~/.claude/skills/orchestrate/scripts/orch ui            # --port N to change the port
```

## Layout

| Path | What |
|---|---|
| `SKILL.md` | The orchestrator's procedure |
| `agents/` | `architect`, `designer`, `engineer`, `qa` subagent definitions |
| `contracts/` | Output formats for the plan, design spec, engineer report and QA report |
| `failure-checklist.md`, `evidence.md` | Defect classes checked on every run, and where they came from |
| `scripts/orch` | Helpers: `workspace`, `brief`, `package`, `usage`, `flow`, `ui` |
| `hooks/orchestrate-guard.sh` | PreToolUse guard for the pipeline agents |
| `monitor/` | The read-only web UI |
| `EVAL.md` | Eval results, and what changed because of them |
