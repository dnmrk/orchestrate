# Contract: the engineer report

The engineer writes it to the report path given in the dispatch: `.orchestrate/<slug>/task-<N>-report.md`. QA never reads it. Only the orchestrator does, to decide routing. The engineer's final message to the orchestrator is just the first four lines below.

```markdown
**Status:** DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
**Commits:** <sha> <subject>  (one per line; BASE..HEAD)
**Checks:** <command> → exit <code>, <summary line>  (one per project check you ran)
**Concerns:** <one line each, or "none">

## Acceptance criteria
| AC | Where it is satisfied (file:line or test name) |

## Deviations from the plan
Anything you did differently, and why. "None" if none. Never deviate silently.

## Blocked / needs context
The exact question, and what you tried. (Only for NEEDS_CONTEXT or BLOCKED.)
```
