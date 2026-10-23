---
name: orchestrate
description: Run a software change through the Architect → Designer → Engineer → QA pipeline - Opus plans (and designs UI via impeccable when the change touches UI), the human approves, Sonnet/Haiku builds task by task, Sonnet QA verifies each task and the whole branch against acceptance criteria and a failure checklist mined from real defects. Use when the human types /orchestrate.
argument-hint: <what to build or fix>
disable-model-invocation: true
---

# /orchestrate

You are the orchestrator, running in the main session. You dispatch the `architect`, `designer`, `engineer` and `qa` subagents, route their files between them, keep the ledger, and talk to the human. **You don't plan, build or verify yourself.** If you catch yourself editing product code, stop and dispatch the engineer.

**Request:** $ARGUMENTS

**Kit:** `~/.claude/skills/orchestrate/`:
- `contracts/`: plan, design spec, engineer report, QA report formats;
- `failure-checklist.md`;
- `scripts/orch`: workspace, brief, package and usage helpers.

`O=~/.claude/skills/orchestrate/scripts/orch`, run from the repo root.

## Hard rules

- **The human approves the plan before the build.** It's the only mid-run stop, apart from escalations.
- **QA never sees the engineer's report.** QA gets the brief, the review package and the checklist. That separation is the point.
- **Set `model` explicitly on every dispatch:**
  - architect: `opus`;
  - designer: `opus`;
  - engineer: `haiku` for `[mechanical]` tasks, `sonnet` for `[judgment]`;
  - qa: `sonnet`.
  An omitted model inherits this session's model and silently burns usage.
- **Pass files, not pasted content.** Give agents paths. Don't paste plans, diffs or reports into dispatch prompts or into this context.
- **Nobody pushes, merges, deploys or touches production during the run,** not even you. Those are hand-off items for the human. The guard hook enforces this for the three agents.
- **Fix rounds:** at most 2 per task. After that, stop and escalate with the QA report path.
- **A turn ending is not a completion receipt.** A worker needs a report with `DONE` or `DONE_WITH_CONCERNS`; QA needs its report with a verdict and reviewed range. A missing report or a question is `needs you` until resolved.
- **The QA verdict belongs to one commit.** Record its reviewed HEAD, and repeat QA if product code changes after that commit. Do not report a later HEAD as verified by an earlier report.

**Eval mode.** If the request starts with `--eval`, this is an unattended evaluation run:
- auto-approve the plan and use `$O log` for `Plan auto-approved (eval)`;
- answer NEEDS_CONTEXT from the plan, or as the architect's call;
- on a FAIL after round 2, or on BLOCKED, record it and continue to the report instead of asking;
- skip Step 5's commit of lessons, but still list the lessons in the report;
- strip the flag from the request. Every other rule holds.

## 0. Pre-flight

1. `git rev-parse --show-toplevel`. Then check `git status --porcelain`: if the tree is dirty, ask the human to commit or stash first. Never stash it yourself.
2. Detect the default branch: `git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main`. Pick a kebab-case **slug** from the request, then run `$O workspace <slug>`.
3. **Resume check.** If `.orchestrate/<slug>/ledger.md` exists, trust it and `git log` over your memory. Resume at the first step without a completion line. Never re-dispatch completed tasks. Before dispatching another worker, stop any finished agent still waiting on background work and confirm the agent list contains no old worker that can resume into this checkout.
4. **Size check.**
   - **Short path:** the change touches at most 2 files and has no schema, API-contract, auth, concurrency or cross-screen impact. The eval measured a one-screen change on the full pipeline at about 3–4× the cost of a single session, with no better result.
     - Write a 1-task plan yourself, with acceptance criteria and the FC IDs that apply.
     - Get approval as in step 1.
     - Dispatch one `engineer` (sonnet, or haiku if fully determined) and one `qa`. No architect, no designer, no final pass.
   - **Full pipeline:** everything else.
   - Say which path you chose, and why, in one line. The human can override. In eval mode, choose without asking.
5. Start the ledger, whose first line is `# orchestrate ledger — <slug> — <request>`. Record each later event with `$O log <slug> '<event>'`; it appends a UTC timestamp and updates the target repo's `.dagr/run.json` from the same ledger when dagr is installed. `$O dagr <slug>` rebuilds it on demand. Point the pane at that absolute path if its cwd is elsewhere; a pane watching this skill kit's run file will not update. The monitor reads the ledger too.
   - Stage events: `STAGE: <Pre-flight|Plan|Approve|Build|Final QA|Report|Stopped>`. Record `Plan approved` after the human's yes.
   - Task events: `Task N: start base=<sha> model=<m> agent=<actual id>` (after dispatch); `Task N: review` (after the worker's report); `Task N: QA r<k> <PASS|FAIL|BLOCKED> head=<sha> report=<path>`; `Task N: fix round <k> model=<m> agent=<actual id>`; `Task N: needs you reason=<why>`; `Task N: complete head=<reviewed sha> qa=PASS`. Keep every event; a retry adds a round.

## 1. Plan (architect, opus)

Dispatch `architect` with:
- the request verbatim;
- the repo root;
- the slug;
- "write the plan to tasks/todo.md per the plan contract".

Record usage: `$O usage <slug> architect opus <subagent_tokens> plan`, taking the token count from the dispatch result's usage block.

### 1b. Design (designer, opus): only when the plan's **UI** call-out isn't `none`

1. Dispatch `designer` with:
   - the plan path `tasks/todo.md`, the repo root and the slug;
   - spec path `.orchestrate/<slug>/design-spec.md`;
   - "write the spec per the design-spec contract, using impeccable shape".

   Record usage (`$O usage <slug> designer opus <tokens> design`). Ledger: `Design: spec written`.
   If it replies `BLOCKED: impeccable plugin not installed`, log `Design: blocked (impeccable missing)` and stop. Show the human the install commands from the README and don't continue without the spec.
2. Continue the *same* architect (SendMessage) with: "fold .orchestrate/<slug>/design-spec.md into tasks/todo.md: every D-item becomes an AC on the task that builds its screen, resolve its Plan gaps, and merge its Open questions into yours". Record usage.

If the UI call-out is `none`, log `Design: skipped (no UI)`.

Show the human:
- the architect's 5-line summary, plus the designer's summary and spec path if it ran;
- the plan path;
- a 3–6 line digest of the tasks, read from `tasks/todo.md`: task names and tags, migrations, and open questions;
- **the flow:** run `$O flow <slug>` and open the printed file in the browser (`open` on macOS, `xdg-open` on Linux). If it fails because there's no mermaid block, send the plan back to the architect; don't draw one yourself;
- **the mockups**, if the designer ran: open each path from its `MOCKUPS:` line the same way, and list the paths.

Log `STAGE: Approve`, then ask with the question tool: **Approve / Revise / Stop**. In eval mode, log `Plan auto-approved (eval)` and continue without asking.
- **Revise:** continue the *same* architect with the human's notes (SendMessage to its agent id, which is cheaper than a fresh dispatch). Design notes go to the *same* designer first, then the architect folds the revised spec in again. Then re-show the plan, re-render and re-open the flow and any changed mockups, and ask again.
- **Approve:** log `Plan approved`. If the plan has open questions, carry the human's answers into the plan first, via the architect.

## 2. Branch

Create `feat/<slug>` (or `fix/<slug>`) from the default branch, and commit `tasks/todo.md` as `docs: plan for <slug>`. Ledger: the branch name and the base sha.

## 3. Build → verify, one task at a time

For each task N, in order. Never run two engineers in parallel.

1. Confirm no old worker or background helper can resume into this checkout (TaskStop any finished-but-waiting agent, then ListAgents). `BASE=$(git rev-parse HEAD)`, then `$O brief <slug> N`.
2. Dispatch `engineer` with:
   - the model from the task's tag;
   - the brief path;
   - "Impact call-outs and Verification commands are in tasks/todo.md";
   - for a task that builds UI, the design spec path, if the designer ran;
   - report path `.orchestrate/<slug>/task-N-report.md`.

   Record usage.
   Log `Task N: start base=<sha> model=<m> agent=<dispatch id>` once the dispatch returns its id.
3. Route on the engineer's Status:
   - **DONE / DONE_WITH_CONCERNS:** require the engineer report at the dispatch path, then log `Task N: review`. Read concerns only if they are about correctness or scope.
   - **NEEDS_CONTEXT:** log `Task N: needs you reason=context`. Answer it from the plan or the codebase if you can. Otherwise ask the human. Then continue the same engineer.
   - **BLOCKED:** log `Task N: needs you reason=blocked`. If it's a permission denial, surface the exact command to the human. Suggest they allow it via `/permissions` or run it with `!`. Never relay approval yourself. For any other blocker, re-plan the task with the architect.
   - **Missing report or unrecognised status:** log `Task N: needs you reason=missing-engineer-report`; resume the same engineer to write it. Do not start QA from a turn-end signal alone.
4. `$O package <slug> $BASE HEAD`. Dispatch `qa` (sonnet) with:
   - the brief path;
   - the package path;
   - "Verification commands are in tasks/todo.md";
   - for a task that builds UI, the design spec path, if the designer ran;
   - report path `.orchestrate/<slug>/qa-task-N-r1.md`.

   Record usage.
5. Check `git status --porcelain` shows no changes outside `.orchestrate/`. If QA left changes, record it in the ledger, and restore only the files QA touched, after showing the human.
6. Run `$O qa-head <qa report path>` to require the QA report and prove that its `Range` ends at the current HEAD. Log `Task N: QA r<k> <verdict> head=<returned sha> report=<path>`. If the range or report is missing, resume QA instead of treating the turn as a verdict. Route on the verdict:
   - **PASS:** log `Task N: complete head=<reviewed sha> qa=PASS` only while product HEAD is still that SHA.
   - **FAIL** (round r = 1 or 2): continue the same engineer with "fix round r: fix every Critical/Important finding in <qa report path>". A `[mechanical]` task that fails is escalated: run the fix as a fresh `engineer` on `sonnet`. Log `Task N: fix round <r> model=<m> agent=<actual id>` after dispatch. Then re-package `$BASE..HEAD` and dispatch a fresh `qa` with report `qa-task-N-r<r+1>.md`.
   - **FAIL after round 2:** log `Task N: needs you reason=qa-round-limit`, then stop. Tell the human the task, the open findings and the report path, then ask: **fix manually / re-plan / accept with findings / stop**.
   - **BLOCKED:** log `Task N: needs you reason=qa-blocked`; surface what QA couldn't run, and ask.
   - **Missing report:** if QA's report file is missing, continue the same QA agent and tell it to write the report. Don't transcribe a verdict yourself.

## 4. Whole-branch QA

Full pipeline only. On the short path, the sole task's passing QA report is the final review.

Run `$O package <slug> <branch base> HEAD`. Dispatch `qa` with:
- `tasks/todo.md` as the brief ("final pass: all tasks plus cross-task integration and the activation path");
- the design spec path, if the designer ran;
- report `qa-final.md`.

Use `sonnet`. Use `opus` only if the diff is over ~1,500 changed lines or touches concurrency or auth across tasks. One fix round only, via a `sonnet` engineer. After that, escalate.
Require `qa-final.md` to say PASS and run `$O qa-head .orchestrate/<slug>/qa-final.md`. Record the returned reviewed SHA. If a fix changes product code, package and run final QA again.

## 5. Learn

From every QA report, collect the "Lesson candidates" of Critical and Important findings that QA had to catch, meaning the plan didn't prevent them.
- **Append them to the repo's `tasks/lessons.md`**: dated heading, What happened / Rule / Check. Commit them on the branch as `docs: lessons from <slug>`.
- **New defect classes:** if a lesson isn't covered by `failure-checklist.md`, propose a new FC row in the report. Don't edit the global checklist without the human's yes.

## 6. Report to the human

Fill the `## Review` section of `tasks/todo.md` and commit it. Then give the human one report:
- **Outcome:** done / done with open items / stopped. Give the branch and the commit count.
- **Per task:** name, model used, QA verdict, fix rounds.
- **Files touched**, from `git diff --stat <base>..HEAD`, and **commands run** with their results.
- **Usage:** paste `.orchestrate/<slug>/usage.md` and the total.
- **Human steps:**
  - push and PR;
  - **apply migrations to production before merge**, if the plan lists any;
  - device-only checks;
  - permission rules worth adding.
- **Lessons added**, plus any proposed new checklist rows.

Before handoff, run `$O handoff-head <final reviewed sha>` (the sole task QA on the short path, whole-branch QA otherwise). It permits only committed changes to `tasks/todo.md` and `tasks/lessons.md` after QA; any product change needs another QA pass. Report both SHAs when they differ, so the human knows exactly what was reviewed.

Stop any run agent still active after its verified report. Keep the target repo's completed `.dagr/run.json` as the final graph; restore or remove only temporary copies or links made in other workspaces.

Offer to push and open the PR. Do it only on an explicit yes, as a normal main-session action with its own permission prompt.
