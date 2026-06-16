"""
orchestrator/state.py
─────────────────────
Central state machine for a PhantomDev task.
All agents read from and write to this shared object.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING      = "pending"
    PLANNING     = "planning"
    ARCHITECTING = "architecting"
    CODING       = "coding"
    TESTING      = "testing"
    SECURING     = "securing"
    DOCUMENTING  = "documenting"
    PR_OPEN      = "pr_open"
    APPROVED     = "approved"
    REJECTED     = "rejected"
    FAILED       = "failed"


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: str
    file_path: str          # target file to create/modify
    status: str = "pending" # pending | in_progress | done | failed
    assigned_to: Optional[str] = None
    code: Optional[str] = None
    tests: Optional[str] = None
    error: Optional[str] = None


class SecurityFinding(BaseModel):
    severity: str   # HIGH | MEDIUM | LOW
    test_id: str
    issue_text: str
    line_number: int
    filename: str


class EvalMetrics(BaseModel):
    test_pass_rate: float = 0.0
    coverage_pct: float = 0.0
    security_high_count: int = 0
    security_medium_count: int = 0
    doc_completeness: float = 0.0
    lines_generated: int = 0
    generation_time_sec: float = 0.0


class TaskState(BaseModel):
    """
    The single source of truth passed through the AutoGen GroupChat.
    Agents mutate this object and it is serialised to JSON for persistence.
    """
    # ── Identity ────────────────────────────────────────────────────────
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # ── Input ────────────────────────────────────────────────────────────
    github_issue_number: Optional[int] = None
    github_issue_title: str = ""
    github_issue_body: str = ""
    target_repo: str = ""
    base_branch: str = "main"

    # ── Planning outputs ─────────────────────────────────────────────────
    requirements: List[str] = []
    acceptance_criteria: List[str] = []
    subtasks: List[SubTask] = []

    # ── Architecture outputs ─────────────────────────────────────────────
    architecture_notes: str = ""
    api_contracts: str = ""          # OpenAPI YAML snippets
    tech_decisions: List[str] = []

    # ── Generated artifacts ──────────────────────────────────────────────
    generated_files: Dict[str, str] = {}   # path → code content
    test_files: Dict[str, str] = {}         # path → test content
    documentation: str = ""

    # ── QA outputs ──────────────────────────────────────────────────────
    test_results: Dict[str, Any] = {}
    coverage_report: str = ""

    # ── Security outputs ─────────────────────────────────────────────────
    security_findings: List[SecurityFinding] = []

    # ── PR ───────────────────────────────────────────────────────────────
    branch_name: str = ""
    pr_url: str = ""
    pr_number: Optional[int] = None
    pr_body: str = ""

    # ── Workflow ─────────────────────────────────────────────────────────
    status: TaskStatus = TaskStatus.PENDING
    current_agent: str = ""
    agent_messages: List[Dict[str, str]] = []  # for WebSocket streaming
    errors: List[str] = []

    # ── Evaluation ───────────────────────────────────────────────────────
    metrics: EvalMetrics = Field(default_factory=EvalMetrics)

    def add_message(self, agent: str, content: str) -> None:
        self.agent_messages.append({
            "agent": agent,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.current_agent = agent
        self.updated_at = datetime.utcnow().isoformat()

    def set_status(self, status: TaskStatus) -> None:
        self.status = status
        self.updated_at = datetime.utcnow().isoformat()

    def fail(self, error: str) -> None:
        self.errors.append(error)
        self.status = TaskStatus.FAILED
        self.updated_at = datetime.utcnow().isoformat()

    @property
    def is_blocked(self) -> bool:
        return self.status in (TaskStatus.FAILED, TaskStatus.REJECTED)

    @property
    def summary(self) -> str:
        done = sum(1 for s in self.subtasks if s.status == "done")
        return (
            f"Task {self.task_id[:8]} | {self.status.value} | "
            f"{done}/{len(self.subtasks)} subtasks | "
            f"coverage={self.metrics.coverage_pct:.0f}% | "
            f"security_high={self.metrics.security_high_count}"
        )
