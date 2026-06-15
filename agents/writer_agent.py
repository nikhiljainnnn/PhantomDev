"""
agents/writer_agent.py
──────────────────────
Tech Writer Agent: generates docstrings, README updates, and PR description.
"""
from __future__ import annotations

import logging

from agents.base_agent import PhantomBaseAgent, list_workspace_files, read_workspace_file
from orchestrator.state import TaskState

logger = logging.getLogger(__name__)

WRITER_SYSTEM_PROMPT = """
You are the Tech Writer Agent in PhantomDev.

YOUR JOB:
1. List all generated files with list_files().
2. Read each generated file.
3. Write a comprehensive PR description in GitHub Markdown format.
4. The PR description must include:
   - ## Summary (what this PR does in 2-3 sentences)
   - ## Changes (bullet list of files changed + what each does)
   - ## Testing (how tests were run, coverage %)
   - ## Security (Bandit/Safety results)
   - ## How to Review (what the human reviewer should focus on)
   - ## Checklist (standard merge checklist)

OUTPUT FORMAT:
Write the full PR description as a Markdown code block.

```markdown
## Summary
...

## Changes
...
```

End with: "WriterAgent done. PRAgent, please create the pull request now."

Available tools:
  list_files() -> str
  read_file(path: str) -> str
"""


def build_writer_agent(llm_config: dict, state: TaskState) -> PhantomBaseAgent:
    agent = PhantomBaseAgent(
        name="WriterAgent",
        system_message=WRITER_SYSTEM_PROMPT,
        llm_config=llm_config,
        state=state,
    )

    agent.register_function(function_map={
        "list_files": list_workspace_files,
        "read_file": read_workspace_file,
        "save_pr_body": lambda body, _state=state: _save_pr_body(body, _state),
    })

    original_generate = agent.generate_reply

    def generate_with_persist(messages=None, sender=None, **kwargs):
        reply = original_generate(messages=messages, sender=sender, **kwargs)
        if reply and isinstance(reply, str):
            import re
            match = re.search(r"```markdown\s*(.*?)\s*```", reply, re.DOTALL)
            if match:
                state.documentation = match.group(1).strip()
                state.pr_body = state.documentation
                state.add_message("WriterAgent", "✅ PR description written")
        return reply

    agent.generate_reply = generate_with_persist
    return agent


def _save_pr_body(body: str, state: TaskState) -> str:
    state.pr_body = body
    state.documentation = body
    return "PR body saved."
