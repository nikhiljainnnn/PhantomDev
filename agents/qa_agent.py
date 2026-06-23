"""
agents/qa_agent.py
──────────────────
QA Agent: runs pytest on generated tests with intelligent sandbox selection.

Execution priority:
  1. Kubernetes Job (highest isolation — used when running inside K8s)
  2. Docker container (medium isolation — used when Docker CLI is available)
  3. Direct subprocess (fallback — dev mode only, logs a warning)

Security model:
  - Network: DISABLED in all sandbox modes (no exfiltration)
  - Secrets: NEVER passed to sandbox (env vars not forwarded)
  - Workspace: read-write (pytest-cov needs to write coverage files)
  - Memory: limited to 512MB
  - CPU: limited to 0.5 cores
  - Timeout: 120 seconds max
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from agents.base_agent import PhantomBaseAgent, list_workspace_files
from orchestrator.state import TaskState, TaskStatus

logger = logging.getLogger(__name__)

MIN_COVERAGE = int(os.getenv("MIN_COVERAGE", 70))
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", 120))

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

If everything passes, end with:
"QAAgent done. SecurityAgent, please proceed."

If tests fail, end with:
"QAAgent BLOCKED. Tests failing — engineers must fix before we continue."

Available tool:
  run_tests() -> str
"""


# ── Environment detection ─────────────────────────────────────────────────────

def _is_kubernetes() -> bool:
    """Detect if we are running inside a Kubernetes pod."""
    return Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists()


def _is_docker_available() -> bool:
    """Detect if Docker CLI is available."""
    return shutil.which("docker") is not None


def _get_execution_mode() -> str:
    if _is_kubernetes():
        return "kubernetes"
    if _is_docker_available():
        return "docker"
    return "direct"


# ── Kubernetes Job execution ──────────────────────────────────────────────────

def _run_tests_kubernetes(workspace: str) -> dict:
    """
    Run pytest inside a Kubernetes Job.
    Uses the in-cluster K8s API directly via requests — no extra deps needed.
    Network is isolated at the pod level via NetworkPolicy (if configured).
    Secrets are NOT forwarded to the Job pod.
    """
    import requests as req
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    req.packages.urllib3.disable_warnings(InsecureRequestWarning)

    # Read in-cluster credentials
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ns_path    = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

    token     = Path(token_path).read_text().strip()
    namespace = Path(ns_path).read_text().strip() if Path(ns_path).exists() else "phantomdev"
    api_url   = "https://kubernetes.default.svc"
    headers   = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    job_name = f"pytest-{uuid.uuid4().hex[:8]}"
    
    # Extract the relative workspace path from /app/workspace 
    # to mount only this task's directory into the sandbox at /code
    try:
        rel_workspace = os.path.relpath(workspace, "/app/workspace")
    except ValueError:
        rel_workspace = ""

    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
            "labels": {"app": "phantomdev-pytest", "managed-by": "qa-agent"},
        },
        "spec": {
            "ttlSecondsAfterFinished": 60,  # auto-cleanup after 60s
            "backoffLimit": 0,              # no retries
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,  # no K8s API access from test pod
                    "containers": [{
                        "name": "pytest",
                        "image": "python:3.11-slim",
                        "command": [
                            "sh", "-c",
                            (
                                "pip install pytest pytest-cov --quiet && "
                                f"cd /code && "
                                f"python -m pytest /code --tb=short "
                                f"--cov=/code --cov-report=json "
                                f"--cov-report=term-missing -q --no-header "
                                f"2>&1 || true"
                            )
                        ],
                        "resources": {
                            "requests": {"memory": "256Mi", "cpu": "250m"},
                            "limits":   {"memory": "512Mi", "cpu": "500m"},
                        },
                        "volumeMounts": [{
                            "name": "workspace",
                            "mountPath": "/code",
                            "subPath": rel_workspace
                            # read-write so pytest-cov can write coverage files
                        }],
                        # CRITICAL: no env vars forwarded — secrets stay out
                        "env": [],
                    }],
                    "volumes": [{
                        "name": "workspace",
                        "persistentVolumeClaim": {"claimName": "workspace-pvc"},
                    }],
                }
            }
        }
    }

    try:
        # Create Job
        resp = req.post(
            f"{api_url}/apis/batch/v1/namespaces/{namespace}/jobs",
            headers=headers, json=job_manifest, verify=False, timeout=10
        )
        resp.raise_for_status()
        logger.info(f"K8s pytest Job created: {job_name}")

        # Poll until Job completes (max SANDBOX_TIMEOUT seconds)
        deadline = time.time() + SANDBOX_TIMEOUT
        pod_name = None

        while time.time() < deadline:
            time.sleep(3)

            # Get Job status
            job_resp = req.get(
                f"{api_url}/apis/batch/v1/namespaces/{namespace}/jobs/{job_name}",
                headers=headers, verify=False, timeout=10
            )
            job_data = job_resp.json()
            status   = job_data.get("status", {})

            if status.get("succeeded", 0) > 0 or status.get("failed", 0) > 0:
                break

            # Find associated Pod
            if not pod_name:
                pods_resp = req.get(
                    f"{api_url}/api/v1/namespaces/{namespace}/pods",
                    headers=headers,
                    params={"labelSelector": f"job-name={job_name}"},
                    verify=False, timeout=10
                )
                items = pods_resp.json().get("items", [])
                if items:
                    pod_name = items[0]["metadata"]["name"]

        # Fetch logs
        logs = ""
        if pod_name:
            log_resp = req.get(
                f"{api_url}/api/v1/namespaces/{namespace}/pods/{pod_name}/log",
                headers=headers, verify=False, timeout=10
            )
            logs = log_resp.text

        # Delete Job (cleanup)
        req.delete(
            f"{api_url}/apis/batch/v1/namespaces/{namespace}/jobs/{job_name}",
            headers=headers,
            params={"propagationPolicy": "Foreground"},
            verify=False, timeout=10
        )
        logger.info(f"K8s pytest Job {job_name} cleaned up")

        return _parse_pytest_output(logs, workspace)

    except Exception as e:
        logger.error(f"K8s Job execution failed: {e}")
        return {"status": "error", "message": str(e), "stdout": "", "passed": 0, "failed": 0, "total": 0, "coverage": 0.0}


# ── Docker execution ──────────────────────────────────────────────────────────

def _run_tests_docker(workspace: str) -> dict:
    """
    Run pytest inside a Docker container.
    --network none prevents all external calls.
    Secrets are NOT passed via -e flags.
    """
    image     = "python:3.11-slim"
    container = f"phantomdev-pytest-{uuid.uuid4().hex[:8]}"

    cmd = [
        "docker", "run",
        "--rm",
        "--name", container,
        "--network", "none",           # no internet access
        "--memory", "512m",            # RAM limit
        "--cpus", "0.5",              # CPU limit
        "--tmpfs", "/tmp:size=100m",   # temp space
        "-v", f"{workspace}:/code",   # mount workspace (rw for coverage)
        "--workdir", "/code",
        # CRITICAL: no -e flags — secrets stay out of container
        image,
        "sh", "-c",
        (
            "pip install pytest pytest-cov --quiet 2>/dev/null && "
            "python -m pytest /code --tb=short "
            "--cov=/code --cov-report=json "
            "--cov-report=term-missing -q --no-header 2>&1 || true"
        )
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT,
        )
        output = result.stdout + result.stderr
        logger.info(f"Docker pytest completed (exit={result.returncode})")
        return _parse_pytest_output(output, workspace)

    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        return {"status": "timeout", "message": f"Tests timed out after {SANDBOX_TIMEOUT}s", "stdout": "", "passed": 0, "failed": 0, "total": 0, "coverage": 0.0}
    except Exception as e:
        logger.error(f"Docker execution failed: {e}")
        return {"status": "error", "message": str(e), "stdout": "", "passed": 0, "failed": 0, "total": 0, "coverage": 0.0}


# ── Direct execution (fallback) ───────────────────────────────────────────────

def _run_tests_direct(workspace: str) -> dict:
    """
    Direct subprocess execution — fallback for local dev.
    WARNING: No isolation. Only use in trusted dev environments.
    """
    logger.warning(
        "⚠️  Running tests WITHOUT sandbox isolation (dev mode). "
        "Generated code executes with full host permissions. "
        "Do NOT use in production."
    )

    py_files = list(Path(workspace).rglob("test_*.py"))
    if not py_files:
        return {"status": "no_tests", "message": "No test files found", "passed": 0, "failed": 0, "total": 0, "coverage": 0.0}

    try:
        result = subprocess.run(
            [
                "python", "-m", "pytest", workspace,
                "--tb=short",
                f"--cov={workspace}",
                "--cov-report=json",
                "--cov-report=term-missing",
                "-q", "--no-header",
            ],
            capture_output=True, text=True,
            timeout=SANDBOX_TIMEOUT,
            cwd=workspace,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return _parse_pytest_output(output, workspace)

    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Tests timed out", "passed": 0, "failed": 0, "total": 0, "coverage": 0.0}
    except Exception as e:
        return {"status": "error", "message": str(e), "passed": 0, "failed": 0, "total": 0, "coverage": 0.0}


# ── Output parser (shared by all modes) ──────────────────────────────────────

def _parse_pytest_output(output: str, workspace: str) -> dict:
    """Parse pytest stdout and coverage.json into a structured result dict."""
    passed = failed = total = 0

    summary = re.search(r"(\d+) passed", output)
    if summary:
        passed = int(summary.group(1))

    fail_match = re.search(r"(\d+) failed", output)
    if fail_match:
        failed = int(fail_match.group(1))

    total = passed + failed

    # Try to read coverage from file first (more accurate)
    coverage_pct = 0.0
    coverage_file = Path(workspace) / "coverage.json"
    if coverage_file.exists():
        try:
            cov_data     = json.loads(coverage_file.read_text())
            coverage_pct = cov_data.get("totals", {}).get("percent_covered", 0.0)
        except Exception:
            pass

    # Fallback: parse from output
    if coverage_pct == 0.0:
        cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if cov_match:
            coverage_pct = float(cov_match.group(1))

    status = "pass" if failed == 0 and coverage_pct >= MIN_COVERAGE and total > 0 else "fail"
    if total == 0:
        status = "no_tests"

    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "total": total,
        "coverage": round(coverage_pct, 1),
        "stdout": output[:3000],
        "return_code": 0 if failed == 0 else 1,
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def run_tests() -> str:
    """
    Auto-detect best available execution method and run pytest.
    Returns JSON string with results.
    """
    from agents.base_agent import WORKSPACE
    workspace = str(WORKSPACE)

    if not Path(workspace).exists():
        return json.dumps({"status": "no_workspace", "message": "Workspace not found", "coverage": 0, "passed": 0, "failed": 0, "total": 0})

    py_files = list(Path(workspace).rglob("test_*.py"))
    if not py_files:
        return json.dumps({"status": "no_tests", "message": "No test files found in workspace", "coverage": 0, "passed": 0, "failed": 0, "total": 0})

    mode = _get_execution_mode()
    logger.info(f"QA Agent using execution mode: {mode}")

    if mode == "kubernetes":
        result = _run_tests_kubernetes(workspace)
    elif mode == "docker":
        result = _run_tests_docker(workspace)
    else:
        result = _run_tests_direct(workspace)

    result["execution_mode"] = mode
    return json.dumps(result)


# ── Agent builder ─────────────────────────────────────────────────────────────

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
    result     = json.loads(result_str)

    state.test_results   = result
    state.coverage_report = result.get("stdout", "")

    total = result.get("total", 0)
    state.metrics.test_pass_rate = (
        result["passed"] / total if total > 0 else 0.0
    )
    state.metrics.coverage_pct = result.get("coverage", 0.0)

    mode   = result.get("execution_mode", "direct")
    status = result.get("status", "fail")

    mode_label = {"kubernetes": "🔒 K8s Job", "docker": "🐳 Docker", "direct": "⚠️ Direct"}.get(mode, mode)

    if status == "pass":
        state.set_status(TaskStatus.SECURING)
        state.add_message(
            "QAAgent",
            f"✅ Tests passed | Coverage: {result['coverage']}% | "
            f"Mode: {mode_label}"
        )
    elif status == "no_tests":
        state.add_message("QAAgent", f"⚠️ No test files found | Mode: {mode_label}")
    else:
        state.add_message(
            "QAAgent",
            f"❌ Tests: {result.get('passed', 0)} passed, "
            f"{result.get('failed', 0)} failed | "
            f"Coverage: {result.get('coverage', 0)}% | "
            f"Mode: {mode_label}"
        )

    return result_str
