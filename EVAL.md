# /orchestrate eval: 2026-10-19

Every run was headless (`claude -p`) in a throwaway worktree of dnmrk/OpenIntake. Artifacts, including plans, QA reports and B's ledger, are in that session's scratchpad `eval/`.

## Results

| Run | What | Model(s) | Cost | Outcome |
|---|---|---|---|---|
| A | Plan replay of PR #24 (water goal), architect only | Opus | $1.61 (reported) | 4 tasks, 30+ ACs. It flagged the prod migration as a blocking human step (FC-01) and kept the retry protection. It quoted all copy verbatim. It anticipated the "partial goals update wipes other goals" risk (FC-15) and avoided it with a separate endpoint. |
| B | Full pipeline replay of PR #23 (Collection ⋯) | Opus plan, Sonnet/Haiku build, Sonnet QA | about 3–4× C (estimated from tokens; the first run was interrupted) | Two tasks. Task 2 was tagged mechanical and built on Haiku. Both passed QA with no fix rounds, and the final pass had no findings. The e2e was seen failing first ("2 !== 0" nested controls). The result is equivalent to the merged PR. |
| C | Baseline: one Opus session on PR #23 | Opus | $0.67 (reported) | An equivalent result in 2 minutes. |
| S1 | Planted bug: goals PATCH made non-partial (silent data loss), with its test deleted | QA Sonnet | $0.23 | **Caught, Critical.** QA wrote and ran its own probe and named the one-line fix. |
| S2 | Planted bug: client goal limit 20,000 vs server 10,000 | (same run) | — | **Caught**, but rated Minor (should be Important). |
| S3 | Planted bug: row button wraps the new ⋯ button and the switch (nested interactive) | QA Sonnet | $0.18 | **Caught, Important (FC-18)**, with the exact line. |

**QA catch rate: 3/3 planted bugs.** QA also flagged an unplanned change that came from a setup mistake: the seeded diff partly reverted PR #23.

## What changed because of the eval
1. **Size check:** changes of at most 2 files with no schema/API/auth/concurrency impact now take a short path (1-task plan, engineer and QA, no architect). For a change that size, B cost 3–4× C for the same result.
2. **QA must run every verification command,** e2e included. A `NOT RUN` check now forces BLOCKED, never PASS. In S1/S2, QA skipped the mobile checks and still counted the checks as passed.
3. **QA severity:** every failure-checklist hit is now at least Important. S2 had been rated Minor.
4. **Missing QA report:** the orchestrator continues QA until it writes the file, instead of transcribing a verdict itself. This happened once in B.
5. **Monitor:** fixed token over-counting. One streamed message is logged as several transcript entries.

## Caveats on this eval
- **Contamination:** the worktrees shared refs with the real repo, so B's architect could see the merged PR #23 (it said so). For future replays, use `git clone --no-local` at the base commit, without the remotes.
- The sample is small: 2 replays and 3 seeds. Treat the catch rate as a smoke test, not a benchmark.
- Native/device behaviour was not exercised; everything was checked against the web preview.
