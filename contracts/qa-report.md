# Contract: the QA report

QA writes it to the path given in the dispatch: `.orchestrate/<slug>/qa-task-<N>-r<round>.md`, or `qa-final.md` for the whole-branch pass. QA's inputs are the plan's task section (brief), the review package (`git diff BASE..HEAD` with context), and the failure checklist. It never sees the engineer's report. QA's final message is just the verdict line plus the one-line counts.

```markdown
**Verdict:** PASS | FAIL | BLOCKED
**Range:** <BASE>..<HEAD>   **Counts:** AC <pass>/<total>, checklist <n applied>, findings C<n> I<n> M<n>

## Acceptance criteria
| AC | Verdict (PASS/FAIL/UNVERIFIABLE) | Evidence: the command you ran and its key output line, or file:line you inspected |

## Failure-checklist sweep
| ID | Applies? | Result and evidence |

## Project checks
<command> → exit <code>, <summary line>   (each check from the plan's Verification commands)

## Findings
For each finding:
- **Severity:** Critical | Important | Minor
- **Where:** file:line
- **Observed vs expected**
- **Repro:** a command or concrete steps

## Lesson candidates
For each Critical or Important finding, one line in the form "When <situation>, <specific check or rule>". Only include patterns a future plan could prevent.
```

## Verdict rules
- **PASS:** every AC is PASS, no Critical or Important findings, and every project check exits 0.
- **FAIL:** any AC fails, any Critical or Important finding, or any project check fails.
- **BLOCKED:** you couldn't run what verification needs, for example because a service is down or a permission was denied. Say exactly what was missing. Never guess a verdict.
- **UNVERIFIABLE** on an AC counts as FAIL, unless the AC itself is only verifiable on a device or in production. In that case, mark it so it is carried to the human as an open item.
- Evidence is something you ran or read in this session. A claim in a commit message is not evidence.
