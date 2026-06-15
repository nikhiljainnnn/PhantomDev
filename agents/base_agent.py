"""
agents/base_agent.py
────────────────────
Base class for all PhantomDev agents.
Provides: ChromaDB RAG, file workspace, structured logging, state access.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import autogen
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from orchestrator.state import TaskState

logger = logging.getLogger(__name__)

WORKSPACE = Path(os.getenv("WORKSPACE_DIR", "./workspace"))
CHROMA_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"))
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def get_chroma_collection(collection_name: str = "codebase") -> Any:
    """Return (or create) the shared ChromaDB collection."""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def rag_search(query: str, n_results: int = 5, collection_name: str = "codebase") -> str:
    """
    Semantic search over indexed codebase.
    Returns formatted string of relevant code snippets.
    """
    try:
        col = get_chroma_collection(collection_name)
        if col.count() == 0:
            return "⚠️  Codebase not indexed yet. Run: python scripts/index_codebase.py"

        results = col.query(query_texts=[query], n_results=min(n_results, col.count()))
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        output = []
        for doc, meta in zip(docs, metas):
            src = meta.get("source", "unknown")
            output.append(f"### {src}\n```python\n{doc}\n```")
        return "\n\n".join(output) if output else "No relevant code found."
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")
        return f"RAG unavailable: {e}"


def read_workspace_file(relative_path: str) -> str:
    """Read a file from the agent workspace."""
    full = WORKSPACE / relative_path
    if not full.exists():
        return f"File not found: {relative_path}"
    return full.read_text(encoding="utf-8")


def write_workspace_file(relative_path: str, content: str) -> str:
    """Write content to the agent workspace, creating dirs as needed."""
    full = WORKSPACE / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return f"✅ Written: {relative_path} ({len(content)} chars)"


def list_workspace_files() -> str:
    """List all files in the workspace."""
    if not WORKSPACE.exists():
        return "Workspace is empty."
    files = [str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*") if p.is_file()]
    return "\n".join(files) if files else "Workspace is empty."


class PhantomBaseAgent(autogen.AssistantAgent):
    """
    Extended AutoGen AssistantAgent with:
    - Access to shared TaskState
    - ChromaDB RAG helpers
    - Workspace file I/O
    - Structured message logging
    """

    def __init__(
        self,
        name: str,
        system_message: str,
        llm_config: dict,
        state: TaskState,
        **kwargs,
    ):
        super().__init__(
            name=name,
            system_message=system_message,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=10,
            **kwargs,
        )
        self.state = state
        self._setup_function_map()

    def _setup_function_map(self) -> None:
        """Register common tool functions available to all agents."""
        self.register_function(
            function_map={
                "rag_search": rag_search,
                "read_file": read_workspace_file,
                "write_file": write_workspace_file,
                "list_files": list_workspace_files,
            }
        )

    def log(self, content: str) -> None:
        """Log to both Python logger and shared TaskState for WebSocket streaming."""
        logger.info(f"[{self.name}] {content[:200]}")
        self.state.add_message(self.name, content)
