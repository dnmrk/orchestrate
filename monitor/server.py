#!/usr/bin/env python3
"""Orchestrate Monitor: a read-only local web UI over Claude Code transcripts and /orchestrate ledgers.

Reads ~/.claude/projects/**.jsonl (sessions and their subagents) and <repo>/.orchestrate/*/ledger.md|usage.md.
Writes nothing. Binds 127.0.0.1 only. Standard library only.
Usage: python3 server.py [--port 7788] [--hours 12]
"""

import argparse
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECTS = Path.home() / ".claude" / "projects"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import blueprint  # noqa: E402  (scripts/ is not a package)
RUNNING_WINDOW = 90  # seconds since last write before an unfinished agent counts as idle
TOOL_WINDOW = 1800  # a pending tool call keeps an agent running this long; past it, assume it was killed
_cache: dict[str, tuple[float, int, dict]] = {}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def short(value, limit=110):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe_tool(block):
    data = block.get("input") or {}
    name = block.get("name", "?")
    detail = data.get("command") or data.get("file_path") or data.get("pattern") or data.get("description") or data.get("query") or data.get("url") or data.get("skill") or ""
    if name == "Agent":
        detail = f"{data.get('subagent_type', 'general')}: {data.get('description', '')}"
    return name, short(detail)


def prompt_title(text: str) -> str | None:
    """The human's prompt: slash commands as '/name args'; harness-injected text is skipped."""
    if command := re.search(r"<command-name>(.*?)</command-name>", text, re.S):
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        return short(f"{command.group(1).strip()} {args.group(1).strip() if args else ''}", 140)
    if text.startswith(("<", "Base directory for this skill", "Caveat:", "[Request interrupted")):
        return None
    return short(text, 140)


def parse_transcript(path: Path) -> dict:
    """Summarise one transcript; cached on (mtime, size)."""
    stat = path.stat()
    key = str(path)
    hit = _cache.get(key)
    if hit and hit[0] == stat.st_mtime and hit[1] == stat.st_size:
        return hit[2]
    calls, results, texts = [], set(), []
    tokens = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    models: dict[str, int] = {}
    first_ts = last_ts = None
    title = cwd = branch = None
    last_stop = None
    counted: set[str] = set()  # one streamed message is logged as several entries with the same usage
    for entry in read_jsonl(path):
        ts = entry.get("timestamp")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        cwd = cwd or entry.get("cwd")
        branch = entry.get("gitBranch") or branch
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user":
            if title is None and isinstance(content, str):
                title = prompt_title(content)
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        results.add(block.get("tool_use_id"))
                    elif title is None and block.get("type") == "text":
                        title = prompt_title(block.get("text", ""))
        elif entry.get("type") == "assistant":
            model = message.get("model")
            message_id = message.get("id")
            usage = {} if message_id and message_id in counted else (message.get("usage") or {})
            if message_id:
                counted.add(message_id)
            out = usage.get("output_tokens", 0) or 0
            if model and model != "<synthetic>":
                models[model] = models.get(model, 0) + out
            tokens["input"] += usage.get("input_tokens", 0) or 0
            tokens["cache_write"] += usage.get("cache_creation_input_tokens", 0) or 0
            tokens["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
            tokens["output"] += out
            last_stop = message.get("stop_reason") or last_stop
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use":
                    name, detail = describe_tool(block)
                    calls.append({"id": block.get("id"), "name": name, "detail": detail, "ts": ts, "input": block.get("input")})
                elif block.get("type") == "text" and block.get("text", "").strip():
                    texts.append({"ts": ts, "text": block["text"]})
    summary = {
        "title": title,
        "cwd": cwd,
        "branch": branch,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "mtime": stat.st_mtime,
        "tokens": tokens,
        "models": models,
        "calls": calls,
        "results": results,
        "texts": texts,
        "last_stop": last_stop,
    }
    _cache[key] = (stat.st_mtime, stat.st_size, summary)
    return summary


def busy(summary: dict) -> bool:
    """Recent writes, or a tool call still awaiting its result: long builds and test runs write nothing."""
    quiet = time.time() - summary["mtime"]
    if quiet < RUNNING_WINDOW:
        return True
    pending = any(call["id"] not in summary["results"] for call in summary["calls"])
    return pending and quiet < TOOL_WINDOW


def agent_status(summary: dict, finished: bool) -> str:
    if finished:
        return "done"
    return "running" if busy(summary) else "idle"


def current_action(summary: dict) -> str:
    pending = [call for call in summary["calls"] if call["id"] not in summary["results"]]
    if pending:
        call = pending[-1]
        return f"{call['name']}: {call['detail']}"
    if summary["texts"]:
        return short(summary["texts"][-1]["text"], 140)
    return ""


def total(tokens: dict) -> int:
    # Fresh tokens processed: cache reads are cheap re-reads of the same context, shown separately.
    return tokens["input"] + tokens["cache_write"] + tokens["output"]


def find_orchestrate(cwd: str | None):
    """Ledgers of /orchestrate runs in this session's repo, newest first."""
    if not cwd:
        return []
    root = Path(cwd)
    for candidate in [root, *root.parents]:
        if (candidate / ".git").exists():
            root = candidate
            break
    runs = []
    for index, ledger in enumerate(sorted((root / ".orchestrate").glob("*/ledger.md"), key=lambda p: p.stat().st_mtime, reverse=True)):
        lines = [line.rstrip() for line in ledger.read_text(errors="replace").splitlines() if line.strip()]
        usage_file = ledger.parent / "usage.md"
        usage = []
        if usage_file.exists():
            for row in usage_file.read_text(errors="replace").splitlines()[2:]:
                cells = [cell.strip() for cell in row.strip("|").split("|")]
                if len(cells) == 5:
                    usage.append(dict(zip(["when", "agent", "model", "tokens", "note"], cells)))
        runs.append({"slug": ledger.parent.name, "path": str(ledger), "root": str(root), "lines": lines, "stage": stage_of(lines), "tasks": tasks_of(lines), "usage": usage, "mtime": ledger.stat().st_mtime,
                     "blueprint": (root / "tasks" / "todo.md").exists() if index == 0 else (ledger.parent / "flow.html").exists()})
    return runs


STAGES = ["Pre-flight", "Plan", "Approve", "Build", "Final QA", "Report"]


def stage_of(lines: list[str]) -> str:
    """The last explicit `STAGE: <name>` line; only ledgers without any are inferred from events (last wins)."""
    explicit = [re.sub(r"\s+at=\S+$", "", match.group(1)).strip() for line in lines[1:] if (match := re.match(r"stage:\s*(.+)", line, re.I))]
    if explicit:
        return explicit[-1]
    stage = "Pre-flight"
    for line in lines[1:]:
        lower = line.lower()
        if lower.startswith(("outcome", "report")):
            stage = "Report"
        elif lower.startswith("final"):
            stage = "Final QA"
        elif re.match(r"task \d+:", lower) or lower.startswith("branch"):
            stage = "Build"
        elif "approved" in lower:
            stage = "Approve"
        elif "architect" in lower or lower.startswith("plan"):
            stage = "Plan"
    return stage


def tasks_of(lines: list[str]):
    tasks: dict[str, dict] = {}
    for line in lines:
        match = re.search(r"Task (\d+):\s*(.*)", line)
        if not match:
            continue
        number, rest = match.groups()
        task = tasks.setdefault(number, {"n": int(number), "state": "building", "verdict": "", "rounds": 0, "model": ""})
        if model := re.search(r"model=([^\s]+)", rest):
            task["model"] = model.group(1)
        if "complete" in rest:
            task["state"] = "complete"
        elif "needs you" in rest or "BLOCKED" in rest:
            task["state"] = "needs you"
        elif "review" in rest:
            task["state"] = "review"
        if verdict := re.search(r"qa=(\w+)|QA(?: r\d+)?:? (PASS|FAIL|BLOCKED)", rest, re.I):
            task["verdict"] = (verdict.group(1) or verdict.group(2)).upper()
            if task["verdict"] == "FAIL":
                task["state"] = "fixing"
        if re.search(r"fix round", rest, re.I):
            task["rounds"] += 1
    return sorted(tasks.values(), key=lambda task: task["n"])


def needs_you(run: dict, session: dict) -> str | None:
    """Why this run is waiting on the human, or None."""
    if re.match(r"stop", run["stage"], re.I):
        return "stopped"
    if any(task["verdict"] == "BLOCKED" for task in run["tasks"]):
        return "task blocked"
    if run["stage"] == "Approve" and session["status"] != "running":
        return "awaiting approval"
    return None


def planned_tasks(root: str) -> int:
    try:
        return len(re.findall(r"^### Task \d+", (Path(root) / "tasks" / "todo.md").read_text(errors="replace"), re.M))
    except OSError:
        return 0


def board(found: list[dict]) -> list[dict]:
    """One card per ledger, owned by the newest session in its repo; sessions arrive newest first."""
    cards: dict[str, dict] = {}
    for session in found:
        for index, run in enumerate(session["runs"]):
            if run["path"] in cards:
                continue
            active = next((agent for agent in reversed(session["agents"]) if agent["status"] == "running"), None)
            # tasks/todo.md holds only the repo's latest plan, so older runs count started tasks only
            total = max(len(run["tasks"]), planned_tasks(run["root"]) if index == 0 else 0)
            cards[run["path"]] = {
                "slug": run["slug"],
                "path": run["path"],
                "project": session["project"],
                "stage": run["stage"],
                "done": sum(task["state"] == "complete" for task in run["tasks"]),
                "total": total,
                "needs": needs_you(run, session),
                "session": session["id"],
                "status": session["status"],
                "agent": active and {"type": active["type"], "model": active["model"], "action": active["action"]},
                "tokens": session["total"],
                "mtime": max(run["mtime"], session["mtime"]),
            }
    return sorted(cards.values(), key=lambda card: card["mtime"], reverse=True)


def project_label(directory: Path) -> str:
    name = directory.name.lstrip("-")
    parts = [part for part in name.split("-") if part]
    return "/".join(parts[-2:]) if parts else name


def sessions(hours: float):
    cutoff = time.time() - hours * 3600
    found = []
    for project in PROJECTS.iterdir() if PROJECTS.exists() else []:
        for transcript in project.glob("*.jsonl"):
            if transcript.stat().st_mtime < cutoff:
                continue
            summary = parse_transcript(transcript)
            agents = []
            sub_dir = transcript.with_suffix("") / "subagents"
            newest = summary["mtime"]
            for sub in sorted(sub_dir.glob("agent-*.jsonl")) if sub_dir.exists() else []:
                try:
                    meta = json.loads(sub.with_suffix(".meta.json").read_text())
                except (OSError, ValueError):  # missing, or caught mid-write
                    meta = {}
                sub_summary = parse_transcript(sub)
                newest = max(newest, sub_summary["mtime"])
                finished = meta.get("toolUseId") in summary["results"]
                agents.append({
                    "id": sub.stem.removeprefix("agent-"),
                    "path": str(sub),
                    "type": meta.get("agentType", "general-purpose"),
                    "description": meta.get("description", ""),
                    "model": next(iter(sorted(sub_summary["models"], key=sub_summary["models"].get, reverse=True)), meta.get("model", "")),
                    "status": agent_status(sub_summary, finished),
                    "started": sub_summary["first_ts"],
                    "last": sub_summary["last_ts"],
                    "tokens": sub_summary["tokens"],
                    "total": total(sub_summary["tokens"]),
                    "calls": len(sub_summary["calls"]),
                    "action": current_action(sub_summary),
                    "background": meta.get("requestShape") == "background",
                })
            running = any(agent["status"] == "running" for agent in agents) or busy(summary)
            found.append({
                "id": transcript.stem,
                "path": str(transcript),
                "project": project_label(project),
                "cwd": summary["cwd"],
                "branch": summary["branch"],
                "title": summary["title"] or "(no prompt)",
                "started": summary["first_ts"],
                "last": summary["last_ts"],
                "mtime": newest,
                "status": "running" if running else "idle",
                "models": summary["models"],
                "tokens": summary["tokens"],
                "total": total(summary["tokens"]) + sum(agent["total"] for agent in agents),
                "action": current_action(summary),
                "agents": agents,
                "runs": find_orchestrate(summary["cwd"]),
            })
    found.sort(key=lambda item: item["mtime"], reverse=True)
    return found


def agent_detail(path: str):
    target = Path(path).resolve()
    if PROJECTS.resolve() not in target.parents or target.suffix != ".jsonl" or not target.exists():
        return None
    summary = parse_transcript(target)
    calls = [
        {"name": call["name"], "detail": call["detail"], "ts": call["ts"], "done": call["id"] in summary["results"], "input": short(call["input"], 600)}
        for call in summary["calls"][-60:]
    ]
    final = summary["texts"][-1]["text"] if summary["texts"] else ""
    return {"calls": calls, "final": final[-4000:], "tokens": summary["tokens"], "models": summary["models"]}


def run_blueprint(path: str) -> str | None:
    """The blueprint for one run's ledger: live from tasks/todo.md for the repo's newest run, else its saved flow.html.
    Only paths shaped <repo>/.orchestrate/<slug>/ledger.md are accepted, so the route can't read arbitrary files."""
    ledger = Path(path).resolve()
    if ledger.name != "ledger.md" or ledger.parent.parent.name != ".orchestrate" or not ledger.is_file():
        return None
    newest = max(ledger.parent.parent.glob("*/ledger.md"), key=lambda p: p.stat().st_mtime)
    todo = ledger.parent.parent.parent / "tasks" / "todo.md"
    if newest == ledger and todo.is_file():
        return blueprint.render(todo.read_text(errors="replace"), str(todo))
    snapshot = ledger.parent / "flow.html"
    return snapshot.read_text(errors="replace") if snapshot.is_file() else None


class Handler(BaseHTTPRequestHandler):
    hours = 12.0

    def send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=list).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/":
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/sessions":
            hours = float(query.get("hours", [self.hours])[0])
            found = sessions(hours)
            return self.send(200, {"now": time.time(), "sessions": found, "board": board(found)})
        if url.path == "/blueprint":
            page = run_blueprint(query.get("run", [""])[0])
            return self.send(200, page.encode(), "text/html; charset=utf-8") if page else self.send(404, {"error": "no blueprint for this run"})
        if url.path == "/api/agent":
            detail = agent_detail(query.get("path", [""])[0])
            return self.send(200, detail) if detail else self.send(404, {"error": "not found"})
        return self.send(404, {"error": "not found"})

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("ORCH_UI_PORT", 7788)))
    parser.add_argument("--hours", type=float, default=12.0)
    args = parser.parse_args()
    Handler.hours = args.hours
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Orchestrate Monitor on http://127.0.0.1:{args.port}  (read-only; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
