"""
agents/security_agent.py
────────────────────────
Security Agent: runs Bandit (SAST) + Safety (dep vulns) on generated code.
Blocks PR creation if HIGH severity findings exist.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import List

from agents.base_agent import PhantomBaseAgent
from orchestrator.state import SecurityFinding, TaskState, TaskStatus

logger = logging.getLogger(__name__)

SECURITY_SYSTEM_PROMPT = """
You are the Security Agent in PhantomDev.

YOUR JOB:
1. Call run_bandit() to perform SAST on all generated Python files.
2. Call run_safety() to check for vulnerable dependencies.
3. Report all findings categorised by severity (HIGH / MEDIUM / LOW).
4. Block the pipeline if any HIGH severity issues exist.

OUTPUT FORMAT:
## Security Report

### SAST (Bandit) Findings
| Severity | Test ID | Issue | File | Line |
|----------|---------|-------|------|------|
[table rows]

### Dependency Vulnerabilities (Safety)
[List of vulnerable packages or "None found"]

### Decision
- HIGH findings: X
- MEDIUM findings: X
- Status: CLEAR / BLOCKED

If CLEAR (0 HIGH findings), end with:
"SecurityAgent done. WriterAgent, please proceed."

If BLOCKED, end with:
"SecurityAgent BLOCKED. HIGH severity findings must be fixed."
List exactly what code changes are needed.

Available tools:
  run_bandit() -> str   (SAST scan, returns JSON)
  run_safety() -> str   (dependency check, returns JSON)
"""

import os
FAIL_ON_HIGH = os.getenv("FAIL_ON_HIGH_SEVERITY", "true").lower() == "true"


def run_bandit() -> str:
    """Run Bandit SAST on workspace Python files."""
    from agents.base_agent import WORKSPACE
    workspace = str(WORKSPACE)

    py_files = list(Path(workspace).rglob("*.py"))
    if not py_files:
        return json.dumps({"status": "no_files", "findings": [], "counts": {}})

    try:
        result = subprocess.run(
            ["python", "-m", "bandit", "-r", workspace, "-f", "json", "-q"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        raw = result.stdout.strip()
        if not raw:
            return json.dumps({"status": "clean", "findings": [], "counts": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}})

        data = json.loads(raw)
        findings_raw = data.get("results", [])
        findings = []
        counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for f in findings_raw:
            sev = f.get("issue_severity", "LOW").upper()
            counts[sev] = counts.get(sev, 0) + 1
            findings.append({
                "severity": sev,
                "test_id": f.get("test_id", ""),
                "issue_text": f.get("issue_text", ""),
                "line_number": f.get("line_number", 0),
                "filename": f.get("filename", ""),
            })

        return json.dumps({
            "status": "blocked" if counts.get("HIGH", 0) > 0 and FAIL_ON_HIGH else "clear",
            "findings": findings,
            "counts": counts,
        })

    except FileNotFoundError:
        logger.warning("Bandit not installed. Install: pip install bandit")
        return json.dumps({"status": "unavailable", "message": "bandit not installed", "findings": []})
    except Exception as e:
        logger.error(f"Bandit error: {e}")
        return json.dumps({"status": "error", "message": str(e), "findings": []})


def run_safety() -> str:
    """Check for vulnerable dependencies with Safety."""
    req_files = []
    from agents.base_agent import WORKSPACE
    for path in Path(WORKSPACE).rglob("requirements*.txt"):
        req_files.append(str(path))

    if not req_files:
        return json.dumps({"status": "no_requirements", "vulnerabilities": []})

    try:
        result = subprocess.run(
            ["python", "-m", "safety", "check", "--json", "-r", req_files[0]],
            capture_output=True,
            text=True,
            timeout=60,
        )

        raw = result.stdout.strip() or "[]"
        vulns = json.loads(raw) if raw.startswith("[") else []

        return json.dumps({
            "status": "vulnerable" if vulns else "clean",
            "count": len(vulns),
            "vulnerabilities": [
                {
                    "package": v[0] if len(v) > 0 else "",
                    "affected": v[1] if len(v) > 1 else "",
                    "installed": v[2] if len(v) > 2 else "",
                    "description": v[3] if len(v) > 3 else "",
                }
                for v in vulns[:10]
            ],
        })

    except FileNotFoundError:
        return json.dumps({"status": "unavailable", "message": "safety not installed"})
    except Exception as e:
        logger.error(f"Safety error: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def build_security_agent(llm_config: dict, state: TaskState) -> PhantomBaseAgent:
    agent = PhantomBaseAgent(
        name="SecurityAgent",
        system_message=SECURITY_SYSTEM_PROMPT,
        llm_config=llm_config,
        state=state,
    )

    agent.register_function(function_map={
        "run_bandit": lambda: _bandit_and_persist(state),
        "run_safety": run_safety,
    })

    return agent


def _bandit_and_persist(state: TaskState) -> str:
    """Run bandit and write findings into TaskState."""
    result_str = run_bandit()
    result = json.loads(result_str)

    findings: List[SecurityFinding] = []
    for f in result.get("findings", []):
        findings.append(SecurityFinding(**f))

    state.security_findings = findings
    counts = result.get("counts", {})
    state.metrics.security_high_count = counts.get("HIGH", 0)
    state.metrics.security_medium_count = counts.get("MEDIUM", 0)

    if result.get("status") == "blocked":
        state.add_message(
            "SecurityAgent",
            f"🚨 BLOCKED: {counts.get('HIGH', 0)} HIGH severity findings"
        )
    else:
        state.set_status(TaskStatus.DOCUMENTING)
        state.add_message(
            "SecurityAgent",
            f"✅ Clear: 0 HIGH | {counts.get('MEDIUM', 0)} MEDIUM | {counts.get('LOW', 0)} LOW"
        )

    return result_str
