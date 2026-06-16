"""
tests/test_pipeline.py
──────────────────────
Integration tests for PhantomDev pipeline.
Uses a mock LLM to test the full agent flow without burning tokens.
"""
from __future__ import annotations

import asyncio
import json
import os
import pytest

# Set test environment BEFORE importing project modules
os.environ.setdefault("WORKSPACE_DIR", "/tmp/phantomdev_test_workspace")
os.environ.setdefault("CHROMA_PERSIST_DIR", "/tmp/phantomdev_test_chroma")
os.environ.setdefault("SANDBOX_DIR", "/tmp/phantomdev_test_sandbox")

from orchestrator.state import TaskState, TaskStatus, SubTask, EvalMetrics


class TestTaskState:
    """Unit tests for the TaskState model."""

    def test_initial_state(self):
        state = TaskState(
            github_issue_title="Add user login",
            github_issue_body="Implement JWT auth",
        )
        assert state.status == TaskStatus.PENDING
        assert state.task_id is not None
        assert len(state.task_id) > 0

    def test_set_status(self):
        state = TaskState()
        state.set_status(TaskStatus.PLANNING)
        assert state.status == TaskStatus.PLANNING

    def test_add_message(self):
        state = TaskState()
        state.add_message("PMAgent", "Requirements extracted")
        assert len(state.agent_messages) == 1
        assert state.agent_messages[0]["agent"] == "PMAgent"
        assert state.current_agent == "PMAgent"

    def test_fail(self):
        state = TaskState()
        state.fail("Something went wrong")
        assert state.status == TaskStatus.FAILED
        assert "Something went wrong" in state.errors

    def test_is_blocked(self):
        state = TaskState()
        assert not state.is_blocked
        state.set_status(TaskStatus.FAILED)
        assert state.is_blocked

    def test_summary(self):
        state = TaskState(github_issue_title="Test")
        state.subtasks = [
            SubTask(title="Task 1", description="", file_path="a.py", status="done"),
            SubTask(title="Task 2", description="", file_path="b.py", status="pending"),
        ]
        state.metrics = EvalMetrics(coverage_pct=80.0)
        summary = state.summary
        assert "1/2" in summary


class TestSubTask:
    def test_subtask_creation(self):
        st = SubTask(
            title="Create user model",
            description="SQLAlchemy model",
            file_path="app/models/user.py",
        )
        assert st.status == "pending"
        assert st.id is not None

    def test_subtask_status_transitions(self):
        st = SubTask(title="T", description="", file_path="f.py")
        st.status = "in_progress"
        assert st.status == "in_progress"
        st.status = "done"
        assert st.status == "done"


class TestEvalMetrics:
    def test_default_metrics(self):
        m = EvalMetrics()
        assert m.test_pass_rate == 0.0
        assert m.coverage_pct == 0.0
        assert m.security_high_count == 0

    def test_metrics_update(self):
        m = EvalMetrics(test_pass_rate=0.95, coverage_pct=82.5)
        assert m.test_pass_rate == 0.95
        assert m.coverage_pct == 82.5


class TestPMAgentParsing:
    """Test PM Agent JSON parsing."""

    def test_parse_pm_output(self):
        from agents.pm_agent import _parse_and_persist
        state = TaskState()

        fake_reply = """
        I've analysed the issue.

        ```json
        {
          "requirements": ["User can register", "User can login"],
          "acceptance_criteria": ["POST /register returns 201", "POST /login returns JWT"],
          "subtasks": [
            {"title": "User model", "description": "SQLAlchemy User", "file_path": "app/models/user.py"},
            {"title": "Auth routes", "description": "FastAPI routes", "file_path": "app/api/auth.py"}
          ]
        }
        ```

        PMAgent done.
        """
        _parse_and_persist(fake_reply, state)

        assert len(state.requirements) == 2
        assert len(state.acceptance_criteria) == 2
        assert len(state.subtasks) == 2
        assert state.subtasks[0].file_path == "app/models/user.py"
        assert state.status == TaskStatus.ARCHITECTING

    def test_parse_invalid_json(self):
        from agents.pm_agent import _parse_and_persist
        state = TaskState()
        _parse_and_persist("No JSON here at all", state)
        # Should not crash, just log warning
        assert len(state.subtasks) == 0


class TestSecurityScanner:
    """Test security scanning functions."""

    def test_bandit_no_files(self, tmp_path):
        os.environ["WORKSPACE_DIR"] = str(tmp_path)
        from agents.security_agent import run_bandit
        result = json.loads(run_bandit())
        # Should not crash with empty workspace
        assert "status" in result

    def test_bandit_clean_code(self, tmp_path):
        os.environ["WORKSPACE_DIR"] = str(tmp_path)
        # Write clean Python file
        (tmp_path / "clean.py").write_text(
            'def greet(name: str) -> str:\n    """Greet a user."""\n    return f"Hello, {name}"\n'
        )
        from agents.security_agent import run_bandit
        import importlib
        import agents.security_agent as sa
        importlib.reload(sa)
        result = json.loads(sa.run_bandit())
        high_count = result.get("counts", {}).get("HIGH", 0)
        assert high_count == 0


class TestAPIHealth:
    """Test FastAPI endpoints."""

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_create_task(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.post("/tasks", json={
            "title": "Test task",
            "body": "Test body with requirements",
        })
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_get_nonexistent_task(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/tasks/nonexistent-id")
        assert response.status_code == 404


class TestEvalHarness:
    """Test evaluation pipeline."""

    def test_evaluate_complete_task(self):
        from evaluation.eval_harness import evaluate_task

        state = TaskState(
            github_issue_title="Add auth",
            subtasks=[
                SubTask(title="Model", description="", file_path="m.py", status="done"),
                SubTask(title="Routes", description="", file_path="r.py", status="done"),
            ],
            generated_files={
                "app/models/user.py": 'from typing import Optional\n\nclass User:\n    """User model."""\n    def __init__(self, id: int) -> None:\n        self.id = id\n',
            },
            test_files={"tests/test_user.py": "def test_user():\n    assert True\n"},
            documentation="## Summary\nAuth added.\n## Changes\n- user.py\n## Testing\n100%",
            metrics=EvalMetrics(test_pass_rate=1.0, coverage_pct=85.0, security_high_count=0),
            status=TaskStatus.PR_OPEN,
        )

        scores = evaluate_task(state)
        assert scores["completeness"] == 1.0
        assert scores["security_score"] == 1.0
        assert scores["composite_score"] > 0.5
