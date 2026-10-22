#!/usr/bin/env python3
"""Self-check for the plan blueprint and the monitor's /blueprint guard. Usage: python3 scripts/test_blueprint.py"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "monitor"))
import blueprint  # noqa: E402
import server  # noqa: E402

PLAN = """# Quote approval — plan

**Request:** add approval to B2B quotes
**Branch:** `feat/quote-approval`   **Base:** `main`

## Impact call-outs
- **Data / schema:** new `quote_approval` table. **Migrations:** `Migration1729000000QuoteApproval.php` — **apply to production before merge — human step**
- **Services / registration:** `QuoteApprovalSubscriber` in services.xml.
- **Permissions / ACL:** none.

## Activation path
1. Registration → discovery → invocation.

## Flow
```mermaid
flowchart LR
  E[Employee submits quote] --> T2
  T1[Task 1: Schema] --> M1[(Migration1729000000)]
  M1 --> T2[Task 2: Subscriber]
```

## Risks
- **FC-03**: Task 2.

## Verification commands
- `docker compose exec web vendor/bin/phpunit`

## Tasks

### Task 1: Schema  `[mechanical]`
- **Files:** create `src/Migration/V6_6/Migration1729000000QuoteApproval.php`
- **Acceptance criteria:**
  - `AC-1.1` Table exists — **Verify:** `bin/console dbal:run-sql` → 1 row

### Task 2: Subscriber  `[judgment]`
- **Files:** create `src/Subscriber/QuoteApprovalSubscriber.php`, modify `src/Resources/config/services.xml`
- **Acceptance criteria:**
  - `AC-2.1` Submit blocks until approved:
    - **Verify:** `phpunit --filter QuoteApprovalTest` → OK
  - `AC-2.2` Idempotent on retry

## Open questions for the human
1. Approver from customer group? Recommended: yes.

## Review
done
"""

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    sections = dict(blueprint.split(PLAN, "##")[1:])

    calls = {call["label"]: call for call in blueprint.impact(sections["Impact call-outs"])}
    assert calls["Data / schema"]["flag"] and not calls["Services / registration"]["flag"], calls
    assert calls["Permissions / ACL"]["none"] and not calls["Permissions / ACL"]["flag"]
    assert not blueprint.flagged("none. **Migrations:** none.")

    tasks, extras = blueprint.tasks(sections["Tasks"])
    assert [(t["n"], t["tag"], t["files"], len(t["acs"])) for t in tasks] == [(1, "mechanical", 1, 1), (2, "judgment", 2, 2)], tasks
    assert extras == []
    assert "QuoteApprovalTest" in tasks[1]["acs"][0][2] and tasks[1]["acs"][1][2] == "", tasks[1]["acs"]

    classes = blueprint.flow_classes(blueprint.mermaid_source(PLAN), tasks)
    assert classes == {"E": "entry", "M1": "migration", "T1": "mechanical", "T2": "judgment"}, classes
    assert blueprint.open_questions(sections["Open questions for the human"]) == 1
    assert blueprint.open_questions("none (both resolved)") == 0

    page = blueprint.render(PLAN)
    for expected in ("Quote approval", "feat/quote-approval", "⚠ Data / schema", "mechanical · haiku", "AC-2.2", "Open questions (1)", "<summary>Review</summary>"):
        assert expected in page, expected
    assert "<script>alert" not in blueprint.render(PLAN.replace("add approval", "<script>alert(1)</script>")), "request must be escaped"

    # CLI: exit 3 without a mermaid block, as `orch flow` relies on
    bare = tmp / "todo.md"
    bare.write_text(PLAN.replace("```mermaid", "```text"))
    result = subprocess.run([sys.executable, str(HERE / "blueprint.py"), str(bare)], capture_output=True, text=True)
    assert result.returncode == 3 and "mermaid" in result.stderr, result

    # Monitor guard: only <repo>/.orchestrate/<slug>/ledger.md; newest run live, older run from its snapshot
    repo = tmp / "repo"
    (repo / "tasks").mkdir(parents=True)
    (repo / "tasks" / "todo.md").write_text(PLAN)
    old, new = repo / ".orchestrate" / "old", repo / ".orchestrate" / "new"
    for run in (old, new):
        run.mkdir(parents=True)
        (run / "ledger.md").write_text("# ledger\n")
    os.utime(old / "ledger.md", (time.time() - 60, time.time() - 60))
    (old / "flow.html").write_text("snapshot")
    assert "Quote approval" in server.run_blueprint(str(new / "ledger.md"))
    assert server.run_blueprint(str(old / "ledger.md")) == "snapshot"
    assert server.run_blueprint(str(repo / "tasks" / "todo.md")) is None
    assert server.run_blueprint("/etc/passwd") is None
    assert server.run_blueprint(str(new / ".." / ".." / "tasks" / "todo.md")) is None

print("ok")
