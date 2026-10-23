# Herdr pane agents

Use this route only when the user requests Herdr panes. Verify `HERDR_ENV=1`, read `herdr --skill`, and check Herdr access before dispatch. A Codex collaboration subagent cannot be moved into a pane.

For each role, create a sibling shell pane in the target repo with `--no-focus`, then start a uniquely named Codex agent there with `herdr agent start <name> --kind codex --pane <id> -- --model <routed model> -c model_reasoning_effort=<routed effort>`. The settings come from [SKILL.md](SKILL.md#model-routing); confirm the agent started with them before prompting. Give it the role file and input paths. Submit the prompt without `--wait`, log the dispatch with `model=<actual model> effort=<actual effort> agent=<name> pane=<returned pane id>`, then wait and verify its report file. Herdr's `idle` or `done` state is not a completion receipt. Give each QA pass a fresh pane and never send QA the engineer report.

If startup or a turn is blocked, inspect the visible pane and ask the user before answering its prompt, as the Herdr skill requires. If sandbox access to Herdr is denied, request the necessary escalation; persistent Codex command rules apply beyond this skill, so do not install them without the user's request.

Track panes created by this run. Keep an engineer pane through QA and any repair; keep planning panes until revisions are settled. Close each settled pane after its report is verified and no follow-up can need it. At handoff, close remaining settled run panes. Leave blocked panes open for resolution. Never close the caller's pane or panes this run did not create.
