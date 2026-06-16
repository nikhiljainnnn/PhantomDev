"""
evaluation/eval_harness.py
──────────────────────────
Automated evaluation pipeline for PhantomDev.
Run after a task completes to generate a quality scorecard.

Usage:
    python -m evaluation.eval_harness --task-id <task_id>
    python -m evaluation.eval_harness --all   # evaluate all completed tasks
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict

from orchestrator.state import TaskState


def evaluate_task(state: TaskState) -> Dict:
    """
    Run full evaluation suite on a completed task.
    Returns a scorecard dict.
    """
    scores = {}

    # 1. Code completeness — are all subtasks done?
    done = sum(1 for s in state.subtasks if s.status == "done")
    total = len(state.subtasks)
    scores["completeness"] = round(done / total if total > 0 else 0, 2)

    # 2. Test pass rate
    scores["test_pass_rate"] = state.metrics.test_pass_rate

    # 3. Coverage
    scores["coverage_pct"] = state.metrics.coverage_pct

    # 4. Security (inverted — lower HIGH count = better score)
    high = state.metrics.security_high_count
    scores["security_score"] = max(0, 1 - (high * 0.25))

    # 5. Documentation completeness
    doc = state.documentation or ""
    has_summary = "## Summary" in doc
    has_changes = "## Changes" in doc
    has_testing = "## Testing" in doc
    scores["doc_completeness"] = round(sum([has_summary, has_changes, has_testing]) / 3, 2)

    # 6. Code quality — avg function length (shorter = better)
    total_lines = 0
    file_count = 0
    for content in state.generated_files.values():
        lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        total_lines += len(lines)
        file_count += 1
    avg_lines = total_lines / file_count if file_count > 0 else 0
    # Penalize files > 200 lines
    scores["code_conciseness"] = round(max(0, 1 - (max(0, avg_lines - 100) / 200)), 2)

    # 7. Type hint coverage — ratio of typed functions
    typed = total_fns = 0
    for content in state.generated_files.values():
        fns = re.findall(r"def \w+\(.*?\)", content, re.DOTALL)
        total_fns += len(fns)
        typed_fns = re.findall(r"def \w+\(.*?\)\s*->\s*\w+", content, re.DOTALL)
        typed += len(typed_fns)
    scores["type_hint_coverage"] = round(typed / total_fns if total_fns > 0 else 0, 2)

    # 8. Composite score (weighted)
    weights = {
        "completeness": 0.30,
        "test_pass_rate": 0.25,
        "coverage_pct": 0.15,
        "security_score": 0.15,
        "doc_completeness": 0.10,
        "type_hint_coverage": 0.05,
    }
    composite = sum(
        scores.get(k, 0) * w if k != "coverage_pct" else (scores.get(k, 0) / 100) * w
        for k, w in weights.items()
    )
    scores["composite_score"] = round(composite, 3)

    # 9. Performance metadata
    scores["files_generated"] = len(state.generated_files)
    scores["test_files_generated"] = len(state.test_files)
    scores["lines_of_code"] = total_lines
    scores["task_status"] = state.status.value
    scores["pr_url"] = state.pr_url

    return scores


def print_scorecard(task_id: str, scores: Dict) -> None:
    """Pretty-print evaluation results."""
    print(f"\n{'='*60}")
    print(f"  PhantomDev Evaluation Scorecard")
    print(f"  Task: {task_id[:16]}...")
    print(f"{'='*60}")

    grade_items = [
        ("Completeness", scores["completeness"], "completeness"),
        ("Test Pass Rate", scores["test_pass_rate"], "test_pass_rate"),
        ("Code Coverage", scores["coverage_pct"] / 100, "coverage_pct"),
        ("Security Score", scores["security_score"], "security_score"),
        ("Documentation", scores["doc_completeness"], "doc_completeness"),
        ("Type Hints", scores["type_hint_coverage"], "type_hint_coverage"),
        ("Code Conciseness", scores["code_conciseness"], "code_conciseness"),
    ]

    for label, val, key in grade_items:
        bar = "█" * int(val * 20)
        color = "✅" if val >= 0.8 else "⚠️" if val >= 0.5 else "❌"
        raw = f"{scores[key]:.0f}%" if key == "coverage_pct" else f"{val:.0%}"
        print(f"  {color} {label:<22} {bar:<20} {raw}")

    print(f"{'─'*60}")
    composite = scores["composite_score"]
    grade = "A" if composite >= 0.85 else "B" if composite >= 0.70 else "C" if composite >= 0.55 else "D"
    print(f"  🏆 COMPOSITE SCORE: {composite:.1%}  (Grade: {grade})")
    print(f"  📁 Files: {scores['files_generated']} code + {scores['test_files_generated']} tests")
    print(f"  📏 Lines of Code: {scores['lines_of_code']}")
    if scores["pr_url"]:
        print(f"  🔗 PR: {scores['pr_url']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", help="Evaluate a specific task")
    parser.add_argument("--demo", action="store_true", help="Run with demo state")
    args = parser.parse_args()

    if args.demo:
        # Demo state for testing the eval harness
        from orchestrator.state import EvalMetrics, SubTask, TaskStatus
        state = TaskState(
            github_issue_title="Demo: Add user auth",
            subtasks=[
                SubTask(title="User model", description="", file_path="app/models/user.py", status="done"),
                SubTask(title="Auth routes", description="", file_path="app/api/auth.py", status="done"),
            ],
            generated_files={
                "app/models/user.py": 'from typing import Optional\n\nclass User:\n    """User model."""\n    def __init__(self, id: int, email: str) -> None:\n        self.id = id\n        self.email = email\n',
                "app/api/auth.py": 'from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.post("/login")\nasync def login(email: str, password: str) -> dict:\n    """Login endpoint."""\n    return {"token": "demo"}\n',
            },
            test_files={"tests/test_auth.py": "def test_login(): assert True"},
            documentation="## Summary\nAdds JWT auth.\n## Changes\n- user.py\n## Testing\n100% pass",
            metrics=EvalMetrics(test_pass_rate=1.0, coverage_pct=85.0, security_high_count=0),
            status=TaskStatus.PR_OPEN,
            pr_url="http://localhost:3000/dry-run",
        )
        scores = evaluate_task(state)
        print_scorecard("demo-task-12345678", scores)
    else:
        print("Usage: python -m evaluation.eval_harness --demo")
        print("       or import and call evaluate_task(state) from your code")
