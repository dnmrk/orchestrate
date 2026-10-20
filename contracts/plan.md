# Contract: the plan

The architect writes it to `tasks/todo.md` in the target repo. It replaces any finished plan there; the old one stays in git history. The human approves this file before any code is written. Every section is required. If a section doesn't apply, write `none` and say why in one clause: an empty section reads as "not checked".

```markdown
# <Feature> — plan

**Request:** <the human's request, verbatim>
**Branch:** <feature branch to create from the default branch>   **Base:** <default branch>

## Impact call-outs
- **Data / schema:** tables, entities, columns. **Migrations:** new file names. If a migration exists, add **"apply to production before merge — human step"**.
- **Services / registration:** DI services, routes, subscribers and hooks that must be registered.
- **Events / hooks:** what this subscribes to or emits.
- **API contract:** endpoints, payloads, status codes. Who else calls this API, and do they still work?
- **UI:** admin / storefront / mobile screens touched; new copy, quoted verbatim. If this isn't `none`, the designer writes `.orchestrate/<slug>/design-spec.md` and you fold every `D-` item into an AC on the task that builds that screen.
- **Permissions / ACL:** new privileges and who gets them.
- **Config / env / dependencies:** new env vars, packages, and whether a native rebuild is needed.

## Activation path
How a user actually reaches this at runtime, in order: registration → discovery → invocation. If you can't trace it to an entry point, the plan is incomplete.

## Flow
A mermaid `flowchart LR` block: one node per task (`T1[Task 1: name]`), edges for build dependencies, migrations as their own nodes, and the activation path's entry point wired to the task it reaches. The human reads this at approval, rendered by `orch flow`.

## Risks
The failure-checklist IDs (`~/.claude/skills/orchestrate/failure-checklist.md`) that apply here. For each one, name the task whose acceptance criteria cover it.

## Verification commands
The project's own checks, copied from its CI config or README (lint, types, tests, schema checks, build), with the exact command and the container to run it in.

## Tasks

### Task 1: <name>  `[mechanical]` or `[judgment]`
- **Files:** create / modify (with paths).
- **Interfaces:** consumes: <signatures from earlier tasks>; produces: <signatures later tasks rely on>.
- **Steps:** one checkable action per line. A test step names the test and what it asserts. A code step names the signature and the exact values the request pins down.
- **Acceptance criteria:** written before the build. Each one is observable and has its own verification.
  - `AC-1.1` <behaviour a user or caller would see> — **Verify:** `<command>` → expects `<output/exit>`  *or*  **Inspect:** `<file>`: <what must be true>
  - `AC-1.2` …

## Open questions for the human
Only questions whose answer changes what gets built. Put the recommended answer first.
```

## Tagging rule

- `[mechanical]`: the steps fully determine the code. It touches 1–2 files, has no design choice left, and the plan carries the exact values. The engineer runs on Haiku.
- `[judgment]`: anything else. It touches several files, involves integration or concurrency, or needs a choice the plan leaves open. The engineer runs on Sonnet.
- When unsure, tag it `[judgment]`. Under-powered models cost more turns than they save.

## Acceptance-criteria rules

- Every task has at least one AC. Every AC names how it is verified.
- An AC that only says "tests pass" is not an AC. Name the behaviour.
- Any task touching UI needs an AC on states (loading, empty, error, disabled) and one on accessibility (role and label, no interactive element nested inside another).
- Any task touching writes needs an AC on retry and idempotency, plus validation boundaries checked at both the API and the DB.
