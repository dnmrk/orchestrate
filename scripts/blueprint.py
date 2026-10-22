#!/usr/bin/env python3
"""Render an /orchestrate plan (tasks/todo.md, per contracts/plan.md) as a self-contained approval page.

Usage: python3 blueprint.py <todo.md> > flow.html   (exit 3 when the plan has no mermaid block)
Standard library only; the monitor imports render() to serve the same page.
"""

import html
import json
import re
import sys
import textwrap
import time
from pathlib import Path

MODEL = {"mechanical": "haiku", "judgment": "sonnet"}  # contracts/plan.md tagging rule
MERMAID_WORDS = {"flowchart", "graph", "subgraph", "end", "direction", "classDef", "class", "style", "linkStyle", "click", "LR", "RL", "TB", "TD", "BT"}


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)


def markdown(text: str) -> str:
    """Paragraphs, list items, fenced code and sub-headings.
    shortcut: list nesting comes from indentation only and tables render as text; swap in a real parser if plans start using tables."""
    out, para, fence = [], [], None

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith("```"):
                out.append(f"<pre>{html.escape(chr(10).join(fence))}</pre>")
                fence = None
            else:
                fence.append(line)
            continue
        if stripped.startswith("```"):
            flush()
            fence = []
        elif not stripped:
            flush()
        elif heading := re.match(r"#{3,6}\s+(.*)", stripped):
            flush()
            out.append(f"<h4>{inline(heading.group(1))}</h4>")
        elif item := re.match(r"(\s*)([-*]|\d+\.)\s+(.*)", line):
            flush()
            marker = "" if item.group(2) in "-*" else f'<span class="n">{item.group(2)}</span>'
            out.append(f'<div class="li" style="--d:{len(item.group(1)) // 2}">{marker}{inline(item.group(3))}</div>')
        else:
            para.append(stripped)
    flush()
    if fence is not None:
        out.append(f"<pre>{html.escape(chr(10).join(fence))}</pre>")
    return "\n".join(out)


def split(text: str, level: str) -> list[tuple[str, str]]:
    """[(heading, body)] for one heading level; the text before the first heading gets heading ''."""
    parts = re.split(rf"^{level} +(.+)$", text, flags=re.M)
    return [("", parts[0])] + [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


def mermaid_source(text: str) -> str:
    match = re.search(r"^```mermaid\n(.*?)^```", text, re.S | re.M)
    return match.group(1).strip() if match else ""


def flagged(text: str) -> bool:
    """Red call-outs: migrations to apply, or anything the plan marks as a human step."""
    migration = re.search(r"\*\*Migrations?:\*\*\s*`?([^\s`.,;]+)", text)
    return bool(re.search(r"human step", text, re.I) or (migration and migration.group(1).lower() != "none"))


def impact(body: str) -> list[dict]:
    items = []
    for chunk in re.split(r"^- (?=\*\*)", body.split("\n### ")[0], flags=re.M)[1:]:
        match = re.match(r"\*\*(.+?):?\*\*:?\s*(.*)", chunk, re.S)
        if not match:
            continue
        label, rest = match.group(1).rstrip(":"), match.group(2).strip()
        first, _, more = rest.partition("\n")
        summary, dot, tail = first.partition(". ")
        items.append({
            "label": label,
            "summary": summary + ("." if dot else ""),
            "more": (tail + "\n" + more).strip(),
            "none": summary.lower().startswith("none"),
            "flag": flagged(rest),
        })
    return items


def criteria(text: str) -> list[tuple[str, str, str]]:
    """[(id, lead line, indented detail)] for each `AC-x.y` list item; detail is the sub-bullets beneath it."""
    found, lines = [], text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"(\s*)[-*] `(AC-[\d.]+)`\s*(.*)", line)
        if not match:
            continue
        indent, detail = len(match.group(1)), []
        for following in lines[index + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            detail.append(following)
        found.append((match.group(2), match.group(3), textwrap.dedent("\n".join(detail)).strip()))
    return found


def tasks(body: str):
    found, extras = [], []
    for heading, text in split(body, "###")[1:]:
        match = re.match(r"Task (\d+):\s*(.*)", heading)
        if not match:
            extras.append((heading, text))
            continue
        tag = re.search(r"\[(mechanical|judgment)\]", match.group(2))
        files = re.search(r"^- \*\*Files.*?(?=^- \*\*|\Z)", text, re.S | re.M)
        found.append({
            "n": int(match.group(1)),
            "name": re.sub(r"`?\[(mechanical|judgment)\]`?", "", match.group(2)).strip(),
            "tag": tag.group(1) if tag else "",
            "files": len({path for path in re.findall(r"`([^`\s]*[/.][^`\s]*)`", files.group(0))}) if files else 0,
            "acs": criteria(text),
            "body": text,
        })
    return found, extras


def flow_classes(source: str, plan_tasks: list[dict]) -> dict[str, str]:
    """Node id -> legend class: task nodes by their tag, migrations, everything else is an entry point."""
    tags = {f"T{task['n']}": task["tag"] or "task" for task in plan_tasks}
    labels = dict(re.findall(r"\b([A-Za-z][\w-]*)\s*[\[({>]+([^\])}]*)", source))
    ids = set()
    for line in source.splitlines()[1:]:
        bare = re.sub(r"\|[^|]*\||\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|\"[^\"]*\"", " ", line)
        if bare.strip().split(" ")[0] in {"classDef", "class", "style", "linkStyle", "click"}:
            continue
        ids.update(word for word in re.findall(r"\b[A-Za-z][\w-]*\b", bare) if word not in MERMAID_WORDS)
    classes = {}
    for node in sorted(ids):
        if node in tags:
            classes[node] = tags[node]
        elif "migration" in (node + labels.get(node, "")).lower():
            classes[node] = "migration"
        else:
            classes[node] = "entry"
    return classes


def open_questions(body: str) -> int:
    if body.strip().lower().startswith("none"):
        return 0
    return len(re.findall(r"^(?:\d+\.|-)\s", body, re.M))


def render(text: str, source: str = "") -> str:
    head, *_ = text.split("\n## ", 1)
    sections = dict(split(text, "##")[1:])
    feature = re.search(r"^# +(.+)$", head, re.M)
    feature = re.sub(r"\s+[—-]\s+plan$", "", feature.group(1).strip()) if feature else "Plan"
    request = re.search(r"\*\*Request:\*\*\s*(.*?)(?=\*\*Branch:\*\*|\Z)", head, re.S)
    branch = re.search(r"\*\*Branch:\*\*\s*(.*?)(?=\*\*Base:\*\*|$)", head, re.M)
    base = re.search(r"\*\*Base:\*\*\s*(.+)$", head, re.M)
    branch_name = re.search(r"`([^`]+)`", branch.group(1)) if branch else None
    branch_name = branch_name.group(1) if branch_name else (branch.group(1).split()[0] if branch and branch.group(1).split() else "—")
    base_name = base.group(1).strip().strip("`") if base else "—"

    def get(prefix: str) -> str:
        return next((body for heading, body in sections.items() if heading.lower().startswith(prefix.lower())), "")

    plan_tasks, extras = tasks(get("Tasks"))
    calls = impact(get("Impact"))
    source_mermaid = mermaid_source(text)
    classes = flow_classes(source_mermaid, plan_tasks) if source_mermaid else {}
    acs = sum(len(task["acs"]) for task in plan_tasks)
    mechanical = sum(task["tag"] == "mechanical" for task in plan_tasks)
    questions = open_questions(get("Open questions"))
    known = ("impact", "activation", "flow", "risks", "verification", "tasks", "open questions")
    others = [(name, body) for name, body in sections.items() if not name.lower().startswith(known)]

    stats = [
        f"<b>{len(plan_tasks)}</b> task{'s' * (len(plan_tasks) != 1)} ({mechanical} mechanical, {len(plan_tasks) - mechanical} judgment)",
        f"<b>{acs}</b> acceptance criteria",
        f'<span class="{"bad" if any(call["flag"] for call in calls) else ""}"><b>{sum(call["flag"] for call in calls)}</b> flagged call-outs</span>',
        f'<span class="{"bad" if questions else ""}"><b>{questions}</b> open question{"s" * (questions != 1)}</span>',
    ]
    chips = "".join(
        f'<div class="call {"flag" if call["flag"] else "none" if call["none"] else ""}"><span class="lbl">{"⚠ " if call["flag"] else ""}{inline(call["label"])}</span>'
        f'<span class="sum">{inline(call["summary"])}</span>'
        + (f'<details><summary>More</summary><div class="md">{markdown(call["more"])}</div></details>' if call["more"] else "")
        + "</div>"
        for call in calls
    )
    impact_extras = "".join(
        f'<details class="extra"><summary>{inline(name)}</summary><div class="md">{markdown(body)}</div></details>'
        for name, body in split(get("Impact"), "###")[1:]
    )
    task_cards = "".join(
        f'<article class="task" id="task-{task["n"]}"><header><span class="tn">T{task["n"]}</span><h3>{inline(task["name"])}</h3>'
        f'<span class="tag {task["tag"] or "task"}">{task["tag"] or "untagged"}{" · " + MODEL[task["tag"]] if task["tag"] in MODEL else ""}</span></header>'
        f'<div class="meta">{task["files"]} path{"s" * (task["files"] != 1)} in Files · {len(task["acs"])} AC{"s" * (len(task["acs"]) != 1)}</div>'
        + (f'<ul class="acs">{"".join(f'<li><code>{ac}</code> {inline(rest)}{f"<div class=md>{markdown(detail)}</div>" if detail else ""}</li>' for ac, rest, detail in task["acs"])}</ul>' if task["acs"] else '<p class="bad">No acceptance criteria.</p>')
        + f'<details><summary>Full task</summary><div class="md">{markdown(task["body"])}</div></details></article>'
        for task in plan_tasks
    )
    extra_blocks = "".join(f'<section class="panel"><h2>{inline(name)}</h2><div class="md">{markdown(body)}</div></section>' for name, body in extras)
    other_blocks = "".join(f'<details class="extra panel"><summary>{inline(name)}</summary><div class="md">{markdown(body)}</div></details>' for name, body in others)
    legend = "".join(f'<span><i class="sw {name}"></i>{label}</span>' for name, label in [("entry", "entry point"), ("mechanical", "mechanical · haiku"), ("judgment", "judgment · sonnet"), ("migration", "migration")] if name in classes.values())
    flow = (
        f'<pre class="mermaid" id="flow">{html.escape(source_mermaid)}</pre><script type="application/json" id="flow-classes">{json.dumps(classes)}</script><div class="legend">{legend}</div>'
        if source_mermaid else '<p class="bad">The plan has no mermaid Flow block. Send it back to the architect.</p>'
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blueprint · {html.escape(feature)}</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header class="top">
  <div class="eyebrow">Plan blueprint · <code>{html.escape(branch_name)}</code> ← <code>{html.escape(base_name)}</code></div>
  <h1>{inline(feature)}</h1>
  {f'<blockquote>{markdown(request.group(1).strip())}</blockquote>' if request else ''}
  <div class="stats">{"".join(f"<span>{s}</span>" for s in stats)}</div>
</header>
<section class="panel"><h2>Impact call-outs</h2><div class="calls">{chips or '<p class="bad">No impact call-outs.</p>'}</div>{impact_extras}</section>
<section class="panel"><h2>Flow</h2><div class="flow">{flow}</div></section>
<section class="panel"><h2>Activation path</h2><div class="md">{markdown(get("Activation")) or '<p class="bad">Missing.</p>'}</div></section>
<section><h2 class="out">Tasks</h2><div class="tasks">{task_cards or '<p class="bad">No tasks.</p>'}</div></section>
{extra_blocks}
<section class="panel"><h2>Risks</h2><div class="md">{markdown(get("Risks"))}</div></section>
<section class="panel"><h2>Verification commands</h2><div class="md">{markdown(get("Verification"))}</div></section>
<section class="panel {"ask" if questions else ""}"><h2>Open questions{f" ({questions})" if questions else ""}</h2><div class="md">{markdown(get("Open questions"))}</div></section>
{other_blocks}
<footer>Rendered {time.strftime("%Y-%m-%d %H:%M")}{f" from <code>{html.escape(source)}</code>" if source else ""}</footer>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<script>{JS}</script>
</body></html>
"""


CSS = """
:root {
  --bg: #f4f4f2; --panel: #ffffff; --inset: #ecebe7; --line: #e2e1dc; --ink: #16161a; --muted: #5d5d63; --faint: #8b8b91;
  --fail: #b3261e; --fail-soft: #fbe4e2; --entry: #6b4fd8; --entry-soft: #ece7fd; --mechanical: #1f7a4d; --mechanical-soft: #dff1e7;
  --judgment: #2463c4; --judgment-soft: #e2ecfb; --migration: #b3261e; --migration-soft: #fbe4e2; color-scheme: light;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #111114; --panel: #1a1a1f; --inset: #24242b; --line: #2e2e36; --ink: #ededf0; --muted: #a3a3ad; --faint: #7c7c86;
  --fail: #ff8a80; --fail-soft: #3a1c1a; --entry: #a993ff; --entry-soft: #2a2245; --mechanical: #4cc38a; --mechanical-soft: #173326;
  --judgment: #7fb0ff; --judgment-soft: #1c2a44; --migration: #ff8a80; --migration-soft: #3a1c1a; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #111114; --panel: #1a1a1f; --inset: #24242b; --line: #2e2e36; --ink: #ededf0; --muted: #a3a3ad; --faint: #7c7c86;
  --fail: #ff8a80; --fail-soft: #3a1c1a; --entry: #a993ff; --entry-soft: #2a2245; --mechanical: #4cc38a; --mechanical-soft: #173326;
  --judgment: #7fb0ff; --judgment-soft: #1c2a44; --migration: #ff8a80; --migration-soft: #3a1c1a; color-scheme: dark; }
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--bg); color: var(--ink); font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 0 max(16px, env(safe-area-inset-right, 0px)) 0 max(16px, env(safe-area-inset-left, 0px)); }
.wrap { max-width: 1120px; margin: 0 auto; padding-block: 32px 64px; display: grid; gap: 18px; }
code, pre { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12.5px; }
code { background: var(--inset); padding: 1px 5px; border-radius: 5px; overflow-wrap: anywhere; }
pre { background: var(--inset); padding: 12px; border-radius: 10px; overflow-x: auto; margin: 8px 0; }
h1, h2, h3 { margin: 0; letter-spacing: -0.01em; text-wrap: balance; }
h1 { font-size: clamp(24px, 4vw, 32px); line-height: 1.2; }
h2 { font-size: 13px; font-weight: 650; color: var(--muted); margin-bottom: 12px; }
h2.out { margin: 6px 0 12px; }
h3 { font-size: 15px; font-weight: 620; }
h4 { margin: 14px 0 6px; font-size: 14px; }
.top { display: grid; gap: 12px; padding-bottom: 4px; }
.eyebrow { color: var(--muted); font-size: 13px; }
blockquote { margin: 0; padding: 4px 0 4px 14px; border-left: 3px solid var(--line); color: var(--muted); max-width: 80ch; }
blockquote p { margin: 0 0 4px; }
.stats { display: flex; flex-wrap: wrap; gap: 6px 20px; color: var(--muted); font-size: 13.5px; font-variant-numeric: tabular-nums; }
.stats b { color: var(--ink); }
.bad, .bad b { color: var(--fail); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; min-width: 0; }
.panel.ask { border-color: var(--fail); }
.calls { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr)); gap: 8px; }
.call { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; display: grid; gap: 4px; align-content: start; min-width: 0; }
.call .lbl { font-size: 12px; font-weight: 650; color: var(--muted); }
.call .sum { font-size: 13.5px; overflow-wrap: anywhere; }
.call.none { background: var(--inset); border-color: transparent; }
.call.none .sum { color: var(--faint); }
.call.flag { border-color: var(--fail); background: var(--fail-soft); }
.call.flag .lbl { color: var(--fail); }
details summary { cursor: pointer; color: var(--muted); font-size: 13px; }
details[open] > summary { margin-bottom: 6px; }
.extra { margin-top: 10px; }
.extra.panel { margin-top: 0; }
.extra.panel > summary { font-size: 13px; font-weight: 650; }
.md { min-width: 0; overflow-wrap: anywhere; font-size: 14px; }
.md p { margin: 0 0 8px; }
.md .li { padding-left: calc(var(--d) * 18px + 16px); position: relative; margin: 3px 0; }
.md .li::before { content: "•"; position: absolute; left: calc(var(--d) * 18px + 3px); color: var(--faint); }
.md .li:has(.n)::before { content: none; }
.md .li .n { position: absolute; left: calc(var(--d) * 18px - 2px); color: var(--faint); font-variant-numeric: tabular-nums; }
.flow { overflow-x: auto; }
.flow pre.mermaid { background: transparent; text-align: center; font-size: 13px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; color: var(--muted); font-size: 12.5px; margin-top: 8px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; border-radius: 3px; border: 1.5px solid; display: inline-block; }
.sw.entry { background: var(--entry-soft); border-color: var(--entry); }
.sw.mechanical { background: var(--mechanical-soft); border-color: var(--mechanical); }
.sw.judgment { background: var(--judgment-soft); border-color: var(--judgment); }
.sw.migration { background: var(--migration-soft); border-color: var(--migration); }
.tasks { display: grid; gap: 10px; }
.task { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px; display: grid; gap: 8px; min-width: 0; }
.task header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.task h3 { flex: 1 1 240px; min-width: 0; }
.tn { font: 650 12px/1 ui-monospace, Menlo, monospace; color: var(--muted); }
.tag { font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: var(--inset); color: var(--muted); white-space: nowrap; }
.tag.mechanical { background: var(--mechanical-soft); color: var(--mechanical); }
.tag.judgment { background: var(--judgment-soft); color: var(--judgment); }
.task .meta { color: var(--faint); font-size: 13px; }
.acs { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 14px; }
.acs li { padding-left: 12px; border-left: 2px solid var(--line); overflow-wrap: anywhere; }
footer { color: var(--faint); font-size: 12.5px; }
"""

JS = """
(() => {
  const el = document.getElementById('flow');
  if (!el || typeof mermaid === 'undefined') return;  // offline: the source stays readable
  const css = getComputedStyle(document.documentElement);
  const t = name => css.getPropertyValue('--' + name).trim();
  const classes = JSON.parse(document.getElementById('flow-classes').textContent);
  const defs = ['entry', 'mechanical', 'judgment', 'migration'].map(c => `classDef ${c} fill:${t(c + '-soft')},stroke:${t(c)},color:${t('ink')},stroke-width:1.5px`);
  defs.push(`classDef task fill:${t('panel')},stroke:${t('faint')},color:${t('ink')}`);
  el.textContent += '\\n' + defs.join('\\n') + '\\n' + Object.entries(classes).map(([id, c]) => `class ${id} ${c}`).join('\\n');
  mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'base', themeVariables: {
    fontFamily: getComputedStyle(document.body).fontFamily, primaryColor: t('panel'), primaryTextColor: t('ink'),
    primaryBorderColor: t('faint'), lineColor: t('faint'), background: t('panel') } });
  mermaid.run({ nodes: [el] });
})();
"""


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: blueprint.py <tasks/todo.md>")
    path = Path(sys.argv[1])
    text = path.read_text(errors="replace")
    if not mermaid_source(text):
        print("no ```mermaid block in tasks/todo.md", file=sys.stderr)
        sys.exit(3)
    sys.stdout.write(render(text, str(path)))


if __name__ == "__main__":
    main()
