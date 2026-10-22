#!/usr/bin/env python3
"""Self-check for the monitor's parsers and board. Usage: python3 monitor/test_board.py"""

import json
import os
import tempfile
import time
from pathlib import Path

import server

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # B3: explicit STAGE lines win even when a later line mentions the architect
    assert server.stage_of(["# h", "STAGE: Build", "Task 2: architect clarified AC"]) == "Build"
    assert server.stage_of(["# h", "Plan approved", "Task 1: start base=abc model=sonnet"]) == "Build"

    # Repo with one run and a 3-task plan
    repo = tmp / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "tasks").mkdir()
    (repo / "tasks" / "todo.md").write_text("## Tasks\n### Task 1: a\n### Task 2: b\n### Task 3: c\n")
    (repo / ".orchestrate" / "cart-fix").mkdir(parents=True)
    (repo / ".orchestrate" / "cart-fix" / "ledger.md").write_text(
        "# orchestrate ledger — cart-fix — x\nSTAGE: Build\nTask 1: start base=a model=sonnet\nTask 1: complete head=b qa=PASS\nTask 2: QA r1 BLOCKED\n"
    )
    runs = server.find_orchestrate(str(repo))
    session = {"id": "s1", "project": "p", "status": "idle", "agents": [], "total": 10, "mtime": time.time(), "runs": runs}
    older = dict(session, id="s0", mtime=0)
    cards = server.board([session, older])
    assert len(cards) == 1, "same ledger in two sessions must be one card"
    card = cards[0]
    assert (card["session"], card["done"], card["total"], card["needs"]) == ("s1", 1, 3, "task blocked"), card

    # needs_you
    assert server.needs_you({"stage": "Approve", "tasks": []}, {"status": "idle"}) == "awaiting approval"
    assert server.needs_you({"stage": "Approve", "tasks": []}, {"status": "running"}) is None
    assert server.needs_you({"stage": "Stopped", "tasks": []}, {"status": "running"}) == "stopped"

    # B2: an id-less assistant message must not swallow later id-less usage
    transcript = tmp / "t.jsonl"
    usage = {"input_tokens": 5, "output_tokens": 1}
    transcript.write_text("\n".join(json.dumps({"type": "assistant", "message": {"usage": usage, "content": []}}) for _ in range(2)))
    assert server.parse_transcript(transcript)["tokens"]["input"] == 10

    # B4: a pending tool call keeps a quiet transcript running
    pending = tmp / "p.jsonl"
    pending.write_text(json.dumps({"type": "assistant", "message": {"id": "m", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}}))
    old = time.time() - 600
    os.utime(pending, (old, old))
    assert server.agent_status(server.parse_transcript(pending), False) == "running"

    # B1: a half-written .meta.json must not break the session list
    project = tmp / "projects" / "-x"
    sub_dir = project / "sess" / "subagents"
    sub_dir.mkdir(parents=True)
    (project / "sess.jsonl").write_text("{}\n")
    (sub_dir / "agent-a.jsonl").write_text("{}\n")
    (sub_dir / "agent-a.meta.json").write_text('{"agentType": "eng')
    server.PROJECTS = tmp / "projects"
    assert server.sessions(1)[0]["agents"][0]["type"] == "general-purpose"

print("ok")
