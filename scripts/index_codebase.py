"""
scripts/index_codebase.py
─────────────────────────
Indexes a Python codebase into ChromaDB for the Architect and Engineer agents.
Run once before starting PhantomDev, then re-run when the codebase changes.

Usage:
    python scripts/index_codebase.py --repo ./path/to/your/repo
    python scripts/index_codebase.py --repo https://github.com/owner/repo  (auto-clone)
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".pytest_cache", "migrations",
}
INCLUDED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yaml", ".yml"}
MAX_CHUNK_CHARS = 2000  # Keep chunks small for better retrieval


def extract_python_chunks(source: str, filepath: str) -> List[Tuple[str, dict]]:
    """
    AST-based chunking: extract each function and class as its own chunk.
    Falls back to line-based chunking if AST parsing fails.
    """
    chunks = []
    try:
        tree = ast.parse(source)
        lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = node.lineno - 1
                end = getattr(node, "end_lineno", start + 20)
                chunk = "\n".join(lines[start:end])
                if len(chunk) > 50:
                    chunks.append((chunk[:MAX_CHUNK_CHARS], {
                        "source": filepath,
                        "type": "function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class",
                        "name": node.name,
                        "start_line": start + 1,
                    }))
    except SyntaxError:
        pass

    # If AST yielded nothing, chunk by lines
    if not chunks:
        lines = source.splitlines()
        for i in range(0, len(lines), 50):
            chunk = "\n".join(lines[i:i+50])
            if chunk.strip():
                chunks.append((chunk, {"source": filepath, "type": "block", "start_line": i + 1}))

    return chunks


def extract_text_chunks(source: str, filepath: str) -> List[Tuple[str, dict]]:
    """Simple paragraph-based chunking for non-Python files."""
    chunks = []
    paragraphs = source.split("\n\n")
    for i, para in enumerate(paragraphs):
        if para.strip() and len(para) > 30:
            chunks.append((para[:MAX_CHUNK_CHARS], {"source": filepath, "type": "text", "paragraph": i}))
    return chunks


def index_repo(repo_path: str) -> None:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    print(f"📂 Indexing: {repo_path}")
    print(f"💾 ChromaDB: {CHROMA_DIR}")
    print(f"🧠 Embedding model: {EMBED_MODEL}")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

    # Delete + recreate for fresh index
    try:
        client.delete_collection("codebase")
    except Exception:
        pass

    collection = client.create_collection(
        name="codebase",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    all_chunks = []
    all_metas = []
    all_ids = []
    chunk_id = 0

    root = Path(repo_path)
    files_processed = 0

    for filepath in root.rglob("*"):
        # Skip excluded dirs
        if any(part in EXCLUDED_DIRS for part in filepath.parts):
            continue
        if not filepath.is_file():
            continue
        if filepath.suffix not in INCLUDED_EXTENSIONS:
            continue

        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(filepath.relative_to(root))

            if filepath.suffix == ".py":
                chunks = extract_python_chunks(source, rel_path)
            else:
                chunks = extract_text_chunks(source, rel_path)

            for chunk, meta in chunks:
                all_chunks.append(chunk)
                all_metas.append(meta)
                all_ids.append(f"chunk_{chunk_id}")
                chunk_id += 1

            files_processed += 1

            # Batch upsert every 100 chunks
            if len(all_chunks) >= 100:
                collection.upsert(documents=all_chunks, metadatas=all_metas, ids=all_ids)
                print(f"  ↑ Upserted {len(all_chunks)} chunks (total so far: {chunk_id})")
                all_chunks, all_metas, all_ids = [], [], []

        except Exception as e:
            print(f"  ⚠️  Skip {filepath}: {e}")

    # Final batch
    if all_chunks:
        collection.upsert(documents=all_chunks, metadatas=all_metas, ids=all_ids)

    print(f"\n✅ Indexed {files_processed} files → {chunk_id} chunks into ChromaDB")


def clone_if_url(repo_arg: str) -> str:
    """If a GitHub URL is given, clone to a temp dir and return the path."""
    if repo_arg.startswith("http") or repo_arg.startswith("git@"):
        tmp = tempfile.mkdtemp(prefix="phantomdev_")
        print(f"🔄 Cloning {repo_arg} → {tmp}")
        subprocess.run(["git", "clone", "--depth=1", repo_arg, tmp], check=True)
        return tmp
    return repo_arg


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a codebase into ChromaDB for PhantomDev")
    parser.add_argument("--repo", required=True, help="Path to repo dir or GitHub URL")
    args = parser.parse_args()

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("Installing required packages...")
        subprocess.run([sys.executable, "-m", "pip", "install", "chromadb", "sentence-transformers"], check=True)
        import chromadb
        from sentence_transformers import SentenceTransformer

    repo_path = clone_if_url(args.repo)
    index_repo(repo_path)
