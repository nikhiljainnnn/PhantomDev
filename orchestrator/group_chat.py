"""
orchestrator/group_chat.py
──────────────────────────
AutoGen GroupChat. Uses a simple sync file-based state bridge
to work reliably on Windows Python 3.10 where asyncio event
loop is not accessible from thread executor context.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

import autogen
from autogen import GroupChat, GroupChatManager
import asyncio

import openai
from langsmith import wrappers

# Monkey-patch OpenAI clients to enable LangSmith tracing automatically
# for any clients created internally by AutoGen.
_orig_sync_init = openai.OpenAI.__init__
def _patched_sync_init(self, *args, **kwargs):
    _orig_sync_init(self, *args, **kwargs)
    wrappers.wrap_openai(self)
openai.OpenAI.__init__ = _patched_sync_init

_orig_async_init = openai.AsyncOpenAI.__init__
def _patched_async_init(self, *args, **kwargs):
    _orig_async_init(self, *args, **kwargs)
    wrappers.wrap_openai(self)
openai.AsyncOpenAI.__init__ = _patched_async_init

from orchestrator.state import TaskState, TaskStatus
from agents.pm_agent import build_pm_agent
from agents.architect_agent import build_architect_agent
from agents.engineer_agent import build_engineer_agents
from agents.qa_agent import build_qa_agent
from agents.security_agent import build_security_agent
from agents.writer_agent import build_writer_agent
from agents.pr_agent import build_pr_agent

logger = logging.getLogger(__name__)

# Directory where live task state JSON is written after each agent turn
# Frontend polls this via GET /tasks/{id} which reads from here
STATE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace")) / ".state"


def get_llm_config() -> dict:
    # Priority: Groq → OpenAI → Ollama
    groq_key   = os.getenv("GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

    if groq_key:
        logger.info("Using Groq: llama-3.3-70b-versatile")
        return {
            "config_list": [{
                "model": "llama-3.3-70b-versatile",
                "api_key": groq_key,
                "base_url": "https://api.groq.com/openai/v1",
            }],
            "temperature": 0.1,
            "timeout": 60,
            "cache_seed": None,
        }

    if openai_key:
        logger.info("Using OpenAI: gpt-4o-mini")
        return {
            "config_list": [{
                "model": "gpt-4o-mini",
                "api_key": openai_key,
            }],
            "temperature": 0.1,
            "timeout": 60,
            "cache_seed": None,
        }

    logger.info(f"Using Ollama: {ollama_model}")
    return {
        "config_list": [{
            "model": ollama_model,
            "base_url": f"{ollama_url}/v1",
            "api_key": "ollama",
        }],
        "temperature": 0.1,
        "timeout": int(os.getenv("AGENT_TIMEOUT", 180)),
        "cache_seed": None,
    }


def is_termination_msg(msg: dict) -> bool:
    content = msg.get("content", "") or ""
    return any(m in content for m in [
        "PHANTOMDEV_COMPLETE", "PHANTOMDEV_FAILED", "HUMAN_APPROVAL_REQUIRED"
    ])


AGENT_ORDER = [
    "PMAgent", "ArchitectAgent",
    "EngineerAgent_0", "EngineerAgent_1", "EngineerAgent_2",
    "QAAgent", "SecurityAgent", "WriterAgent", "PRAgent",
]


def custom_speaker_selection(last_speaker, groupchat):
    agents_by_name = {a.name: a for a in groupchat.agents}
    idx = AGENT_ORDER.index(last_speaker.name) if last_speaker.name in AGENT_ORDER else -1
    next_name = AGENT_ORDER[min(idx + 1, len(AGENT_ORDER) - 1)]
    return agents_by_name.get(next_name, groupchat.agents[0])


def _save_state_sync(state: TaskState) -> None:
    """
    Write task state to a JSON file synchronously.
    Called from thread context — no asyncio needed.
    The API's GET /tasks/{id} endpoint reads this file.
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = STATE_DIR / f"{state.task_id}.json"
        # Atomic write: write to temp then rename
        tmp = path.with_suffix(".tmp")
        tmp.write_text(state.model_dump_json(), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"State save failed: {e}")


def load_state_from_file(task_id: str) -> Optional[TaskState]:
    """Load task state from file. Called by API to get fresh state."""
    try:
        path = STATE_DIR / f"{task_id}.json"
        if path.exists():
            return TaskState.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"State load failed for {task_id}: {e}")
    return None


class PhantomDevOrchestrator:

    def __init__(self, on_update: Optional[Callable] = None):
        self._on_update_cb = on_update
        self.llm_config = get_llm_config()

    def _fire_update(self, state: TaskState) -> None:
        """
        Save state synchronously (always works from any thread).
        Also tries the async callback if one was provided.
        """
        # Always save to file — this is what the frontend polls
        _save_state_sync(state)

        # Try async callback (works when running in async context)
        if self._on_update_cb is not None:
            try:
                import inspect
                if inspect.iscoroutinefunction(self._on_update_cb):
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.run_coroutine_threadsafe(
                            self._on_update_cb(state), loop
                        )
                    except RuntimeError:
                        pass  # No running loop — fine, file save covers us
                else:
                    self._on_update_cb(state)
            except Exception as e:
                logger.debug(f"on_update callback skipped: {e}")

    async def run(self, state: TaskState) -> TaskState:
        logger.info(f"Starting task {state.task_id}")
        state.set_status(TaskStatus.PLANNING)
        state.add_message("PhantomDev", f"🚀 Pipeline starting for: {state.github_issue_title}")
        _save_state_sync(state)

        try:
            pm_agent        = build_pm_agent(self.llm_config, state)
            architect_agent = build_architect_agent(self.llm_config, state)
            engineer_agents = build_engineer_agents(
                self.llm_config, state, count=int(os.getenv("MAX_ENGINEERS", 3))
            )
            qa_agent       = build_qa_agent(self.llm_config, state)
            security_agent = build_security_agent(self.llm_config, state)
            writer_agent   = build_writer_agent(self.llm_config, state)
            pr_agent       = build_pr_agent(self.llm_config, state)

            all_agents = [
                pm_agent, architect_agent,
                *engineer_agents,
                qa_agent, security_agent, writer_agent, pr_agent,
            ]

            # Wrap every agent to capture replies and save state after each turn
            for ag in all_agents:
                self._wrap_agent(ag, state)

            user_proxy = autogen.UserProxyAgent(
                name="HumanProxy",
                human_input_mode="NEVER",
                is_termination_msg=is_termination_msg,
                code_execution_config=False,
                max_consecutive_auto_reply=0,
            )

            groupchat = GroupChat(
                agents=[user_proxy] + all_agents,
                messages=[],
                max_round=int(os.getenv("MAX_ROUNDS", 40)),
                speaker_selection_method=custom_speaker_selection,
                allow_repeat_speaker=False,
            )

            manager = GroupChatManager(
                groupchat=groupchat,
                llm_config=self.llm_config,
                is_termination_msg=is_termination_msg,
            )

            state.add_message("PhantomDev", "🤖 All agents ready. PMAgent analysing requirements…")
            _save_state_sync(state)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: user_proxy.initiate_chat(
                    manager,
                    message=self._build_initial_message(state),
                    clear_history=True,
                ),
            )

            last_msgs = groupchat.messages[-5:] if groupchat.messages else []
            combined  = " ".join(m.get("content", "") for m in last_msgs)

            if "PHANTOMDEV_FAILED" in combined:
                state.fail("Agent pipeline reported failure")
            elif "HUMAN_APPROVAL_REQUIRED" in combined or state.pr_url:
                state.set_status(TaskStatus.PR_OPEN)
            else:
                state.fail("Pipeline ended without clear success signal")

        except Exception as exc:
            logger.exception(f"Orchestrator error: {exc}")
            state.fail(str(exc))

        _save_state_sync(state)
        logger.info(f"Task finished: {state.summary}")
        return state

    def _wrap_agent(self, agent, state: TaskState) -> None:
        """Intercept every agent reply → add to messages → save state."""
        original = agent.generate_reply
        orchestrator = self

        def wrapped(messages=None, sender=None, **kwargs):
            reply = original(messages=messages, sender=sender, **kwargs)
            if reply and isinstance(reply, str) and reply.strip():
                # Avoid duplicate messages
                last = state.agent_messages[-1] if state.agent_messages else {}
                if last.get("content") != reply or last.get("agent") != agent.name:
                    state.add_message(agent.name, reply[:3000])
                orchestrator._fire_update(state)
            return reply

        agent.generate_reply = wrapped

    def _build_initial_message(self, state: TaskState) -> str:
        return f"""New GitHub Issue assigned to PhantomDev autonomous engineering team.

ISSUE #{state.github_issue_number}: {state.github_issue_title}

DESCRIPTION:
{state.github_issue_body}

TARGET REPOSITORY: {state.target_repo}
BASE BRANCH: {state.base_branch}
TASK ID: {state.task_id}

PMAgent, please begin by extracting requirements and creating subtasks.""".strip()