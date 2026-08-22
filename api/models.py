"""api/models.py — Pydantic request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from orchestrator.state import TaskStatus


class CreateTaskRequest(BaseModel):
    title: str = Field(..., description="Issue title or feature name")
    body: str = Field(..., description="Full issue description with requirements")
    issue_number: int | None = Field(None, description="GitHub issue number")
    repo: str | None = Field(None, description="GitHub repo (owner/name)")
    base_branch: str | None = Field("main", description="Branch to PR into")

    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "Add user authentication with JWT",
                "body": "## Description\nImplement JWT-based authentication.\n\n## Requirements\n- POST /auth/register\n- POST /auth/login returns JWT token\n- Protected routes require Bearer token\n- Passwords hashed with bcrypt",
                "issue_number": 42,
                "repo": "myorg/myproject",
                "base_branch": "main",
            }
        }
    }


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str
