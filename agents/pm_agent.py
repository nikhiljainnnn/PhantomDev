"""
agents/pm_agent.py
──────────────────
Product Manager Agent.
Receives a GitHub Issue → produces structured requirements + subtask list.
Writes results directly into the shared TaskState.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import autogen

from agents.base_agent import PhantomBaseAgent
from orchestrator.state import SubTask, TaskState, TaskStatus

logger = logging.getLogger(__name__)

PM_SYSTEM_PROMPT = """
You are the Product Manager Agent in PhantomDev, an autonomous software engineering team.

YOUR JOB:
1. Read the GitHub issue carefully.
2. Extract clear, unambiguous REQUIREMENTS (functional + non-functional).
3. Write specific ACCEPTANCE CRITERIA (testable, measurable).
4. Decompose the work into SUBTASKS — one subtask = one file to create or modify.
4. Output a JSON block that the system will parse.

OUTPUT FORMAT (always end your response with this exact JSON block):

```json
{
  "requirements": [
    "The system must ...",
    "Users should be able to ..."
  ],
  "acceptance_criteria": [
    "Given ... when ... then ...",
    "All endpoints return HTTP 200 for valid input"
  ],
  "subtasks": [
    {
      "title": "Create user model",
      "description": "SQLAlchemy model for User with id, email, hashed_password, created_at",
      "file_path": "app/models/user.py"
    },
    {
      "title": "Create user schema",
      "description": "Pydantic schemas UserCreate, UserRead, UserUpdate",
      "file_path": "app/schemas/user.py"
    }
  ]
}
```

RULES:
- One subtask per file. Never group multiple files into one subtask.
- file_path must be relative (e.g. app/api/users.py, not /home/user/...)
- Each subtask description must be self-contained (the engineer should not need to read other subtasks)
- After outputting the JSON, say: "PMAgent done. ArchitectAgent, please proceed."
"""


def build_pm_agent(llm_config: dict, state: TaskState) -> PhantomBaseAgent:
    agent = PhantomBaseAgent(
        name="PMAgent",
        system_message=PM_SYSTEM_PROMPT,
        llm_config=llm_config,
        state=state,
    )

    # Hook into the reply pipeline to parse and persist outputs
    original_generate = agent.generate_reply

    def generate_with_persistence(messages=None, sender=None, **kwargs):
        reply = original_generate(messages=messages, sender=sender, **kwargs)
        if reply:
            _parse_and_persist(reply, state)
        return reply

    agent.generate_reply = generate_with_persistence
    return agent


def _parse_and_persist(reply: str, state: TaskState) -> None:
    """Extract JSON from PM Agent reply and write into TaskState."""
    match = re.search(r"```json\s*(.*?)\s*```", reply, re.DOTALL)
    if not match:
        logger.warning("PMAgent: no JSON block found in reply")
        return

    try:
        data = json.loads(match.group(1))
        state.requirements = data.get("requirements", [])
        state.acceptance_criteria = data.get("acceptance_criteria", [])

        subtasks = []
        for raw in data.get("subtasks", []):
            subtasks.append(SubTask(
                title=raw["title"],
                description=raw["description"],
                file_path=raw["file_path"],
            ))
        state.subtasks = subtasks
        state.set_status(TaskStatus.ARCHITECTING)

        logger.info(
            f"PMAgent persisted: {len(state.requirements)} requirements, "
            f"{len(state.subtasks)} subtasks"
        )
        state.add_message("PMAgent", f"✅ {len(state.subtasks)} subtasks created")
    except Exception as e:
        logger.error(f"PMAgent JSON parse error: {e}\nRaw: {match.group(1)[:500]}")
        state.errors.append(f"PM parse error: {e}")
