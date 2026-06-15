"""
agents/engineer_agent.py
────────────────────────
Engineer Agents: take individual subtasks and generate production code.
Multiple instances run in round-robin via AutoGen GroupChat.
Each engineer claims a subtask, generates code + unit tests, writes to workspace.
"""
from __future__ import annotations

import logging
import re
from typing import List

from agents.base_agent import PhantomBaseAgent, rag_search, write_workspace_file
from orchestrator.state import TaskState, TaskStatus

logger = logging.getLogger(__name__)

ENGINEER_SYSTEM_PROMPT = """
You are EngineerAgent_{idx} in PhantomDev, an autonomous software engineering team.

YOUR JOB:
1. Find the next PENDING subtask from the list below.
2. Search the codebase for relevant patterns with rag_search().
3. Write production-quality code for the subtask file.
4. Write unit tests for the code (pytest style).
5. Save both files using write_file().

SUBTASKS (read the TaskState):
{subtasks_summary}

ARCHITECTURE CONTEXT:
{architecture_notes}

API CONTRACTS:
{api_contracts}

OUTPUT FORMAT:
After generating code, output EXACTLY this structure:

## Subtask Claimed
subtask_id: <id>
file_path: <path>

## Implementation
```python
# <file_path>
<your complete code here>
```

## Tests
```python
# tests/test_<filename>.py
<your complete pytest tests here>
```

After writing files, say:
"EngineerAgent_{idx} done with subtask <id>. Next engineer please proceed."

CODING RULES:
1. Write COMPLETE files — never use placeholders like "# TODO" or "# implement later"
2. Add proper docstrings to every function and class
3. Use type hints everywhere
4. Handle errors explicitly — raise specific exceptions, not bare Exception
5. Follow existing codebase patterns (check rag_search results)
6. Tests must cover: happy path, edge cases, error cases
7. Always call write_file() to save — do not just print the code

Available tools:
  rag_search(query: str) -> str
  read_file(relative_path: str) -> str
  write_file(relative_path: str, content: str) -> str
  list_files() -> str
"""


def build_engineer_agents(
    llm_config: dict,
    state: TaskState,
    count: int = 3,
) -> List[PhantomBaseAgent]:
    """Build N engineer agents, each aware of all subtasks."""
    agents = []
    for idx in range(count):
        subtasks_summary = _format_subtasks(state)
        system_msg = ENGINEER_SYSTEM_PROMPT.format(
            idx=idx,
            subtasks_summary=subtasks_summary,
            architecture_notes=state.architecture_notes or "Not yet defined",
            api_contracts=state.api_contracts or "Not yet defined",
        )

        agent = PhantomBaseAgent(
            name=f"EngineerAgent_{idx}",
            system_message=system_msg,
            llm_config=llm_config,
            state=state,
        )

        # Attach custom function map with code + file tools
        agent.register_function(function_map={
            "rag_search": rag_search,
            "write_file": lambda path, content, _state=state: _write_and_persist(path, content, _state),
            "read_file": lambda path: _safe_read(path),
            "list_files": lambda: _safe_list_files(),
        })

        original_generate = agent.generate_reply

        def make_reply_fn(ag, _idx=idx):
            def generate_with_persistence(messages=None, sender=None, **kwargs):
                reply = original_generate(messages=messages, sender=sender, **kwargs)
                if reply and isinstance(reply, str):
                    _parse_and_persist(reply, state, _idx)
                return reply
            return generate_with_persistence

        agent.generate_reply = make_reply_fn(agent)
        agents.append(agent)

    return agents


def _format_subtasks(state: TaskState) -> str:
    lines = []
    for st in state.subtasks:
        status_icon = {"pending": "⏳", "in_progress": "🔨", "done": "✅", "failed": "❌"}.get(st.status, "?")
        lines.append(f"{status_icon} [{st.id}] {st.title} → {st.file_path}")
        if st.status == "pending":
            lines.append(f"   DESC: {st.description}")
    return "\n".join(lines) if lines else "No subtasks defined yet — wait for PMAgent."


def _write_and_persist(path: str, content: str, state: TaskState) -> str:
    """Write file to workspace AND record in TaskState."""
    result = write_workspace_file(path, content)
    # Track in state
    if "test_" in path.split("/")[-1] or "/tests/" in path:
        state.test_files[path] = content
    else:
        state.generated_files[path] = content
    # Mark subtask done
    for st in state.subtasks:
        if st.file_path == path and st.status != "done":
            st.status = "done"
            st.code = content
            state.add_message("EngineerAgent", f"✅ Completed: {path}")
            break
    return result


def _safe_read(path: str) -> str:
    from agents.base_agent import read_workspace_file
    return read_workspace_file(path)


def _safe_list_files() -> str:
    from agents.base_agent import list_workspace_files
    return list_workspace_files()


def _parse_and_persist(reply: str, state: TaskState, agent_idx: int) -> None:
    """Parse engineer reply and save code blocks to workspace."""
    # Find all code blocks
    code_blocks = re.findall(
        r"```python\s*\n# ([\w/._-]+)\n(.*?)```",
        reply,
        re.DOTALL
    )

    for file_path, code in code_blocks:
        file_path = file_path.strip()
        code = code.strip()
        if file_path and code:
            _write_and_persist(file_path, code, state)
            logger.info(f"EngineerAgent_{agent_idx}: wrote {file_path} ({len(code)} chars)")

    # Update status if all subtasks done
    pending = [s for s in state.subtasks if s.status == "pending"]
    if not pending:
        state.set_status(TaskStatus.TESTING)
