"""
agents/architect_agent.py
─────────────────────────
Architect Agent: reads PM subtasks + codebase RAG context,
produces system design notes and API contracts.
"""
from __future__ import annotations

import logging
import re

from agents.base_agent import PhantomBaseAgent, rag_search
from orchestrator.state import TaskState, TaskStatus

logger = logging.getLogger(__name__)

ARCHITECT_SYSTEM_PROMPT = """
You are the Architect Agent in PhantomDev.

YOUR JOB:
1. Review the subtasks from PMAgent.
2. Search the existing codebase for relevant patterns using rag_search().
3. Define the system design: folder structure, interfaces, data models, patterns to follow.
4. Write API contracts (function signatures or OpenAPI snippets) for each subtask.
5. Identify tech decisions: which libraries to use, why.

OUTPUT FORMAT:
## Architecture Notes
[Your notes here — patterns to follow, folder conventions, shared utilities]

## API Contracts
[Function signatures or pseudo-code for each subtask's public interface]

## Tech Decisions
- [Decision]: [Rationale]

End your message with:
"ArchitectAgent done. EngineerAgents, begin implementation now."

RULES:
- Always call rag_search() first with the main feature keyword to find existing patterns.
- Match existing code style found in the codebase.
- Keep architecture notes concise — engineers must be able to act on them immediately.
- If codebase is empty, define clean FastAPI + SQLAlchemy patterns.

Available tool:
  rag_search(query: str, n_results: int = 5) -> str
    Searches the indexed codebase and returns relevant snippets.
"""


def build_architect_agent(llm_config: dict, state: TaskState) -> PhantomBaseAgent:
    agent = PhantomBaseAgent(
        name="ArchitectAgent",
        system_message=ARCHITECT_SYSTEM_PROMPT,
        llm_config=llm_config,
        state=state,
    )

    original_generate = agent.generate_reply

    def generate_with_persistence(messages=None, sender=None, **kwargs):
        reply = original_generate(messages=messages, sender=sender, **kwargs)
        if reply and isinstance(reply, str):
            _parse_and_persist(reply, state)
        return reply

    agent.generate_reply = generate_with_persistence
    return agent


def _parse_and_persist(reply: str, state: TaskState) -> None:
    """Extract architecture notes and tech decisions from architect reply."""
    # Pull architecture notes
    arch_match = re.search(r"## Architecture Notes\s*(.*?)(?=##|$)", reply, re.DOTALL)
    if arch_match:
        state.architecture_notes = arch_match.group(1).strip()

    # Pull API contracts
    api_match = re.search(r"## API Contracts\s*(.*?)(?=##|$)", reply, re.DOTALL)
    if api_match:
        state.api_contracts = api_match.group(1).strip()

    # Pull tech decisions
    td_match = re.search(r"## Tech Decisions\s*(.*?)(?=##|ArchitectAgent done|$)", reply, re.DOTALL)
    if td_match:
        decisions = []
        for line in td_match.group(1).strip().splitlines():
            line = line.strip("- ").strip()
            if line:
                decisions.append(line)
        state.tech_decisions = decisions

    state.set_status(TaskStatus.CODING)
    state.add_message("ArchitectAgent", f"✅ Architecture defined: {len(state.tech_decisions)} decisions")
    logger.info(f"ArchitectAgent persisted: {len(state.tech_decisions)} tech decisions")
