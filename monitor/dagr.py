#!/usr/bin/env python3
"""Project timestamped /orchestrate ledger events into a validated dagr run."""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def validator():
    candidates = [os.environ.get("DAGR_BIN"), shutil.which("dagr")]
    candidates += glob.glob(str(Path.home() / ".config/herdr/plugins/github/*/bin/dagr"))
    return next((path for path in candidates if path and os.access(path, os.X_OK)), None)


def build(ledger: Path, slug: str, titles=None):
    titles = titles or {}
    lines = ledger.read_text().splitlines()
    stamps = [m.group(1) for line in lines if (m := re.search(r"\bat=(\S+)", line))]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    started = stamps[0] if stamps else now
    tasks = {}
    events = []
    approval_at = None
    approval_id = None
    approvals = 0
    for line in lines:
        stamp = re.search(r"\bat=(\S+)", line)
        if stamp and line.startswith("STAGE: Approve"):
            approvals += 1
            approval_at = stamp.group(1)
            approval_id = "PLAN" if approvals == 1 else f"PLAN{approvals}"
            tasks[approval_id] = {
                "id": approval_id, "title": "Approve plan", "kind": "question",
                "owner": "operator", "state": "queued", "deps": [], "attempts": [],
            }
        elif stamp and line.startswith(("Plan approved", "Plan auto-approved")) and approval_at and approval_id:
            at = stamp.group(1)
            actor = "eval" if line.startswith("Plan auto-approved") else "operator"
            tasks[approval_id].update(state="done", attempts=[{
                "id": f"{approval_id}·a1", "n": 1, "cause": {"type": "initial"},
                "actor": actor, "state": "done", "started_at": approval_at,
                "ended_at": at, "outcome": {
                    "result": "done", "evidence": "reported", "receipt": line.split(" at=", 1)[0],
                },
            }])
            events.append({"at": at, "type": "directive", "verb": "answer", "by": actor, "task": approval_id, "detail": line.split(" at=", 1)[0]})
        task_line = re.search(r"Task (\d+): (.*)", line)
        if not stamp or not task_line:
            continue  # shortcut: old untimestamped events stay monitor-only, migrate old ledgers if dagr history is needed.
        at = stamp.group(1)
        number, body = task_line.groups()
        body = body.split(" at=", 1)[0]
        task = tasks.setdefault(number, {
            "id": f"T{number}", "title": titles.get(number, f"Task {number}"), "kind": "impl",
            "owner": "engineer", "state": "queued", "deps": [], "attempts": [],
        })
        attempts = task["attempts"]
        if body.startswith(("start ", "fix round ")):
            if attempts and (body.startswith("start ") or attempts[-1]["state"] != "rejected"):
                raise ValueError(f"Task {number} retry needs a rejected attempt")
            agent = re.search(r"\bagent=(\S+)", body)
            if not agent:
                raise ValueError(f"Task {number} start/fix needs agent=<actual agent id>")
            n = len(attempts) + 1
            cause = {"type": "initial"} if n == 1 else {"type": "followup", "ref": attempts[-1]["id"], "reason": "QA sent work back"}
            # shortcut: dispatch ids locate work in the run record but may not focus a Herdr pane; use pane ids when available.
            pane = re.search(r"\bpane=(\S+)", body)
            locator = {"pane": pane.group(1)} if pane else {"agent": agent.group(1)}
            attempt = {
                "id": f"T{number}·a{n}", "n": n, "cause": cause,
                "actor": "engineer", "locator": locator, "state": "working",
                "started_at": at, "liveness": {
                    "prompt_acknowledged": True, "last_output_at": at, "queued_input": 0,
                },
            }
            if model := re.search(r"\bmodel=(\S+)", body):
                attempt["model"] = model.group(1)
            attempts.append(attempt)
            task["state"] = "working"
            task.pop("unblock", None)
            events.append({"at": at, "type": "attempt_started", "task": task["id"], "attempt": attempt["id"], "actor": "engineer"})
        elif body.startswith("QA "):
            verdict = re.search(r"\b(PASS|FAIL|BLOCKED)\b", body)
            if not verdict or not attempts:
                raise ValueError(f"Task {number} QA needs a verdict and a started attempt")
            if attempts[-1]["state"] != "working":
                raise ValueError(f"Task {number} QA already settled this attempt")
            if verdict.group(1) == "BLOCKED":
                task["state"] = "blocked"
                task["unblock"] = "operator"
                continue
            attempt = attempts[-1]
            head = re.search(r"\bhead=(\S+)", body)
            if not head:
                raise ValueError(f"Task {number} QA needs head=<reviewed sha>")
            state = "done" if verdict.group(1) == "PASS" else "rejected"
            attempt.update(state=state, ended_at=at, outcome={"result": state, "evidence": "reported", "receipt": body})
            attempt.pop("locator", None)
            attempt.pop("liveness", None)
            task["state"] = state
            task.pop("unblock", None)
            task["reviewed_head"] = head.group(1)
            events.append({"at": at, "type": "attempt_settled", "task": task["id"], "attempt": attempt["id"], "actor": "qa", "detail": body})
        elif body.startswith("review"):
            if not attempts or attempts[-1]["state"] != "working":
                raise ValueError(f"Task {number} review needs a started attempt")
            task["state"] = "review"
            attempts[-1]["liveness"]["last_output_at"] = at
        elif body.startswith("needs you"):
            task["state"] = "blocked"
            task["unblock"] = "operator"
        elif body.startswith("complete "):
            head = re.search(r"\bhead=(\S+)", body)
            if task["state"] != "done" or not head or head.group(1) != task.get("reviewed_head"):
                raise ValueError(f"Task {number} complete needs QA PASS on the same head")
            task["note"] = f"QA passed at {head.group(1)}"
    planned = sorted(titles, key=int)
    for index, number in enumerate(planned):
        task = tasks.setdefault(number, {
            "id": f"T{number}", "title": titles[number], "kind": "impl",
            "owner": "engineer", "state": "queued", "deps": [], "attempts": [],
        })
        task["deps"] = [f"T{planned[index - 1]}"] if index else ([approval_id] if approval_id else [])
    for task in tasks.values():
        task.pop("reviewed_head", None)
    run = {"id": f"orchestrate-{slug}", "title": f"Orchestrate: {slug}", "started_at": started}
    if pane := os.environ.get("HERDR_PANE_ID"):
        run["orchestrator"] = {"pane": pane}
    return {"dagr": 3, "run": run, "generated_at": now, "projects": [], "tasks": list(tasks.values()), "events": events}


def main(root: Path, slug: str, optional=False):
    binary = validator()
    if not binary:
        if optional:
            return
        raise RuntimeError("dagr validator not found; install herdr-dagr or set DAGR_BIN")
    ledger = root / ".orchestrate" / slug / "ledger.md"
    plan = root / "tasks" / "todo.md"
    titles = {}
    if plan.exists():
        for line in plan.read_text().splitlines():
            if match := re.match(r"^### Task (\d+): (.+)", line):
                titles[match.group(1)] = re.sub(r"\s+`?\[(mechanical|judgment)\]`?.*$", "", match.group(2))
    run_dir = root / ".dagr"
    run_dir.mkdir(exist_ok=True)
    (run_dir / ".gitignore").write_text("*\n")
    candidate = run_dir / "run.json.tmp"
    candidate.write_text(json.dumps(build(ledger, slug, titles), indent=2) + "\n")
    check = subprocess.run([binary, "check", str(candidate), "--strict", "--json"], capture_output=True, text=True)
    if check.returncode or check.stdout.strip() != "[]":
        raise RuntimeError(f"dagr check failed ({check.returncode}): {check.stdout or check.stderr}")
    candidate.replace(run_dir / "run.json")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]), sys.argv[2], "--optional" in sys.argv[3:])
    except (IndexError, OSError, ValueError, RuntimeError) as error:
        sys.exit(f"orch dagr: {error}")
