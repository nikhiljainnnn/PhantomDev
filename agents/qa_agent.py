"""
agents/qa_agent.py
──────────────────
QA Agent: runs pytest on generated tests, measures coverage,
reports failures back into TaskState.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from agents.base_agent import PhantomBaseAgent, list_workspace_files
from orchestrator.state import TaskState, TaskStatus

logger = logging.getLogger(__name__)

QA_SYSTEM_PROMPT = """
You are the QA Agent in PhantomDev.

YOUR JOB:
1. Call run_tests() to execute all pytest tests in the workspace.
2. Analyse the results.
3. If coverage < {min_coverage}%, identify which files lack tests and instruct engineers to add more.
4. If all tests pass and coverage >= {min_coverage}%, declare success.

OUTPUT FORMAT:
## QA Report
- Tests run: X
- Tests passed: X
- Tests failed: X
- Coverage: X%
- Status: PASS / FAIL

## Failures (if any)
[List specific failures with file + line]

## Coverage Gaps (if any)
[Files with < 80% coverage]

If everything passes, end with:
"QAAgent done. SecurityAgent, please proceed."

If tests fail, end with:
"QAAgent BLOCKED. Tests failing — engineers must fix before we continue."

Available tool:
  run_tests() -> str  (runs pytest with coverage, returns JSON report)
"""

import os
MIN_COVERAGE = int(os.getenv("MIN_COVERAGE", 70))


def run_tests() -> str:
    """
    Run pytest with coverage in the workspace directory.
    Returns a JSON string with results.
    """
    from agents.base_agent import WORKSPACE
    workspace = str(WORKSPACE)

    if not Path(workspace).exists() or not any(Path(workspace).rglob("test_*.py")):
        return json.dumps({
            "status": "no_tests",
            "message": "No test files found in workspace",
            "coverage": 0,
            "passed": 0,
            "failed": 0,
            "total": 0,
        })

    try:
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                workspace,
                "--tb=short",
                f"--cov={workspace}",
                "--cov-report=json",
                "--cov-report=term-missing",
                "-q",
                "--no-header",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=workspace,
        )

        # Parse coverage JSON if it exists
        coverage_file = Path(workspace) / "coverage.json"
        coverage_pct = 0.0
        if coverage_file.exists():
            cov_data = json.loads(coverage_file.read_text())
            coverage_pct = cov_data.get("totals", {}).get("percent_covered", 0.0)

        # Parse test counts from stdout
        stdout = result.stdout or ""
        passed = failed = total = 0
        summary_match = re.search(r"(\d+) passed", stdout)
        if summary_match:
            passed = int(summary_match.group(1))
        fail_match = re.search(r"(\d+) failed", stdout)
        if fail_match:
            failed = int(fail_match.group(1))
        total = passed + failed

        return json.dumps({
            "status": "pass" if failed == 0 and coverage_pct >= MIN_COVERAGE else "fail",
            "passed": passed,
            "failed": failed,
            "total": total,
            "coverage": round(coverage_pct, 1),
            "stdout": stdout[:3000],
            "stderr": (result.stderr or "")[:1000],
            "return_code": result.returncode,
        })

    except subprocess.TimeoutExpired:
        return json.dumps({"status": "timeout", "message": "Tests timed out after 120s"})
    except Exception as e:
        logger.error(f"Test runner error: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def build_qa_agent(llm_config: dict, state: TaskState) -> PhantomBaseAgent:
    agent = PhantomBaseAgent(
        name="QAAgent",
        system_message=QA_SYSTEM_PROMPT.format(min_coverage=MIN_COVERAGE),
        llm_config=llm_config,
        state=state,
    )

    agent.register_function(function_map={
        "run_tests": lambda: _run_and_persist(state),
        "list_files": list_workspace_files,
    })

    return agent


def _run_and_persist(state: TaskState) -> str:
    """Run tests and write results into TaskState."""
    result_str = run_tests()
    result = json.loads(result_str)

    # Persist to state
    state.test_results = result
    state.coverage_report = result.get("stdout", "")
    state.metrics.test_pass_rate = (
        result["passed"] / result["total"] if result.get("total", 0) > 0 else 0.0
    )
    state.metrics.coverage_pct = result.get("coverage", 0.0)

    status = result.get("status", "fail")
    if status == "pass":
        state.set_status(TaskStatus.SECURING)
        state.add_message("QAAgent", f"✅ Tests passed | Coverage: {result['coverage']}%")
    else:
        state.add_message(
            "QAAgent",
            f"❌ Tests: {result.get('passed',0)} passed, "
            f"{result.get('failed',0)} failed | Coverage: {result.get('coverage',0)}%"
        )

    return result_str
