import subprocess
import tempfile
import unittest
from pathlib import Path

from dagr import build
from server import stage_of, tasks_of


class DagrLedgerTest(unittest.TestCase):
    def build_lines(self, *lines):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.md"
            ledger.write_text("# orchestrate ledger — demo — change\n" + "\n".join(lines) + "\n")
            return build(ledger, "demo")

    def test_approval_and_retry_keep_history(self):
        run = self.build_lines(
            "STAGE: Approve at=2026-10-23T03:00:00Z",
            "Plan approved at=2026-10-23T03:01:00Z",
            "Task 1: start base=abc model=sonnet agent=agent-1 at=2026-10-23T03:02:00Z",
            "Task 1: QA r1 FAIL head=abc at=2026-10-23T03:03:00Z",
            "Task 1: fix round 1 model=sonnet agent=agent-2 at=2026-10-23T03:04:00Z",
            "Task 1: QA r2 PASS head=def at=2026-10-23T03:05:00Z",
            "Task 1: complete head=def qa=PASS at=2026-10-23T03:06:00Z",
        )
        self.assertEqual(run["tasks"][0]["state"], "done")
        self.assertEqual([attempt["state"] for attempt in run["tasks"][1]["attempts"]], ["rejected", "done"])

    def test_reviewed_head_must_match_completion(self):
        with self.assertRaisesRegex(ValueError, "same head"):
            self.build_lines(
                "Task 1: start base=abc agent=agent-1 at=2026-10-23T03:01:00Z",
                "Task 1: QA r1 PASS head=abc at=2026-10-23T03:02:00Z",
                "Task 1: complete head=def qa=PASS at=2026-10-23T03:03:00Z",
            )

    def test_task_title_comes_from_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.md"
            ledger.write_text("Task 2: start agent=agent-2 at=2026-10-23T03:01:00Z\n")
            self.assertEqual(build(ledger, "demo", {"2": "Fix login"})["tasks"][0]["title"], "Fix login")

    def test_planned_tasks_appear_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.md"
            ledger.write_text("STAGE: Approve at=2026-10-23T03:00:00Z\n")
            tasks = build(ledger, "demo", {"1": "Build API", "2": "Use API"})["tasks"]
            self.assertEqual([(task["id"], task["state"], task["deps"]) for task in tasks], [
                ("PLAN", "queued", []),
                ("T1", "queued", ["PLAN"]),
                ("T2", "queued", ["T1"]),
            ])

    def test_herdr_pane_locates_worker(self):
        run = self.build_lines("Task 1: start base=abc model=codex agent=worker pane=w4:p2 at=2026-10-23T03:01:00Z")
        self.assertEqual(run["tasks"][0]["attempts"][0]["locator"], {"pane": "w4:p2"})

    def test_qa_head_rejects_a_different_commit(self):
        root = Path(__file__).resolve().parent.parent
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "qa.md"
            report.write_text(f"**Verdict:** PASS\n**Range:** {head}..{head}   **Counts:** AC 1/1\n")
            command = [str(root / "scripts/orch"), "qa-head", str(report)]
            self.assertEqual(subprocess.run(command, cwd=root, capture_output=True, text=True).stdout.strip(), head)
            report.write_text(f"**Verdict:** PASS\n**Range:** {head}..{'0' * len(head)}   **Counts:** AC 1/1\n")
            self.assertNotEqual(subprocess.run(command, cwd=root, capture_output=True).returncode, 0)

    def test_monitor_reads_timestamped_events(self):
        lines = ["# run", "STAGE: Build at=2026-10-23T03:00:00Z", "Task 1: start model=gpt-6.1-sol agent=a at=2026-10-23T03:01:00Z", "Task 1: needs you reason=context at=2026-10-23T03:02:00Z"]
        self.assertEqual(stage_of(lines), "Build")
        self.assertEqual(tasks_of(lines)[0]["model"], "gpt-6.1-sol")
        self.assertEqual(tasks_of(lines)[0]["state"], "needs you")

    def test_eval_approval_is_not_attributed_to_operator(self):
        run = self.build_lines("STAGE: Approve at=2026-10-23T03:00:00Z", "Plan auto-approved (eval) at=2026-10-23T03:01:00Z")
        self.assertEqual(run["tasks"][0]["attempts"][0]["actor"], "eval")

    def test_handoff_accepts_docs_but_rejects_product_changes(self):
        script = Path(__file__).resolve().parent.parent / "scripts/orch"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.com")
            (root / "app.txt").write_text("checked\n")
            git("add", "app.txt")
            git("commit", "-qm", "checked")
            reviewed = git("rev-parse", "HEAD")
            (root / "tasks").mkdir()
            (root / "tasks/todo.md").write_text("review\n")
            git("add", "tasks/todo.md")
            git("commit", "-qm", "docs")
            package = subprocess.check_output([str(script), "package", "demo", reviewed, "HEAD"], cwd=root, text=True).strip()
            self.assertIn(f"# Review package {reviewed}..{git('rev-parse', 'HEAD')}", Path(package).read_text())
            command = [str(script), "handoff-head", reviewed]
            self.assertEqual(subprocess.run(command, cwd=root, capture_output=True).returncode, 0)
            (root / "app.txt").write_text("changed\n")
            git("add", "app.txt")
            git("commit", "-qm", "product")
            self.assertNotEqual(subprocess.run(command, cwd=root, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
