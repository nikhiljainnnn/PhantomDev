"""
api/main.py  (PRODUCTION VERSION)
──────────────────────────────────
Redis-backed task store, Celery dispatch, CORS locked to ALLOWED_ORIGINS,
Prometheus metrics, structured JSON logging, WebSocket live-push for both
BackgroundTask and Celery execution paths.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from api.models import CreateTaskRequest, TaskResponse
from api.store import task_store
from orchestrator.state import TaskState, TaskStatus

# ── Structured JSON logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config from environment ────────────────────────────────────────────────────
API_KEY         = os.getenv("PHANTOMDEV_API_KEY", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
USE_CELERY      = os.getenv("USE_CELERY", "true").lower() == "true"

# ── In-memory WebSocket registry (per-process, not persisted) ─────────────────
websocket_connections: Dict[str, List[WebSocket]] = {}

# ── API key auth ───────────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(key: Optional[str] = Depends(api_key_header)) -> None:
    if not API_KEY:
        return
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Lifespan: connect Redis on startup, close on shutdown ─────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in [
        os.getenv("WORKSPACE_DIR", "./workspace"),
        os.getenv("SANDBOX_DIR", "./sandbox"),
        os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"),
    ]:
        os.makedirs(d, exist_ok=True)
    await task_store.connect()
    logger.info("PhantomDev API started | celery=%s | redis=%s", USE_CELERY,
                "connected" if not task_store._use_fallback else "fallback")
    yield
    await task_store.close()
    logger.info("PhantomDev API shutdown")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="PhantomDev", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Prometheus metrics ─────────────────────────────────────────────────────────
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
except ImportError:
    pass


# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    logger.info(
        "method=%s path=%s status=%d ms=%.0f",
        request.method,
        request.url.path,
        response.status_code,
        (time.time() - start) * 1000,
    )
    return response


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "redis": "connected" if not task_store._use_fallback else "fallback",
        "celery": USE_CELERY,
        "ollama_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        "version": "2.0.0",
    }


@app.post("/tasks", response_model=TaskResponse, dependencies=[Depends(verify_api_key)])
async def create_task(request: CreateTaskRequest, background_tasks: BackgroundTasks):
    state = TaskState(
        github_issue_number=request.issue_number,
        github_issue_title=request.title,
        github_issue_body=request.body,
        target_repo=request.repo or os.getenv("TARGET_REPO", ""),
        base_branch=request.base_branch or "main",
    )
    await task_store.save(state)
    websocket_connections[state.task_id] = []

    if USE_CELERY:
        from worker.celery_app import run_pipeline
        run_pipeline.delay(state.task_id, state.model_dump_json())
        logger.info("Task %s dispatched to Celery", state.task_id)
    else:
        background_tasks.add_task(_run_pipeline_bg, state.task_id)
        logger.info("Task %s started in BackgroundTasks", state.task_id)

    return TaskResponse(task_id=state.task_id, status=state.status, message="Task created. Pipeline starting.")


@app.get("/tasks", dependencies=[Depends(verify_api_key)])
async def list_tasks():
    tasks = await task_store.list_all()
    # Sync any file-state updates back into Redis (orchestrator writes files from thread context)
    result = []
    for t in tasks:
        fresh = await _get_fresh_state(t.task_id) or t
        result.append({
            "task_id": fresh.task_id,
            "status": fresh.status,
            "title": fresh.github_issue_title,
            "created_at": fresh.created_at,
            "updated_at": fresh.updated_at,
            "pr_url": fresh.pr_url,
            "coverage": fresh.metrics.coverage_pct,
            "files_generated": len(fresh.generated_files),
        })
    return result


@app.get("/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
async def get_task(task_id: str):
    state = await _get_fresh_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    return state.model_dump()


@app.delete("/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
async def delete_task(task_id: str):
    if not await task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    await task_store.delete(task_id)
    websocket_connections.pop(task_id, None)
    return {"message": "Task deleted"}


@app.post("/tasks/{task_id}/approve", dependencies=[Depends(verify_api_key)])
async def approve_pr(task_id: str):
    state = await task_store.get(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    if state.status != TaskStatus.PR_OPEN:
        raise HTTPException(status_code=400, detail=f"Task status is {state.status}, expected pr_open")
    state.set_status(TaskStatus.APPROVED)
    state.add_message("Human", "✅ PR approved")
    await task_store.save(state)
    await _broadcast(task_id, state)
    return {"message": "PR approved", "pr_url": state.pr_url}


@app.post("/tasks/{task_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_pr(task_id: str, reason: str = ""):
    state = await task_store.get(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    state.set_status(TaskStatus.REJECTED)
    state.add_message("Human", f"❌ PR rejected: {reason}")
    await task_store.save(state)
    await _broadcast(task_id, state)
    return {"message": "PR rejected"}


@app.post("/webhook/github")
async def github_webhook(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    event_type = payload.get("action", "")
    issue = payload.get("issue", {})
    labels = [l.get("name", "") for l in issue.get("labels", [])]
    if event_type == "labeled" and "phantomdev" in labels:
        state = TaskState(
            github_issue_number=issue.get("number"),
            github_issue_title=issue.get("title", ""),
            github_issue_body=issue.get("body", ""),
            target_repo=payload.get("repository", {}).get("full_name", ""),
        )
        await task_store.save(state)
        websocket_connections[state.task_id] = []
        if USE_CELERY:
            from worker.celery_app import run_pipeline
            run_pipeline.delay(state.task_id, state.model_dump_json())
        else:
            background_tasks.add_task(_run_pipeline_bg, state.task_id)
        logger.info("Webhook task created: %s (issue #%s)", state.task_id, issue.get("number"))
        return {"task_id": state.task_id}
    return {"message": "ignored"}


# ── WebSocket endpoint ─────────────────────────────────────────────────────────
@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    websocket_connections.setdefault(task_id, []).append(websocket)

    # Send all existing messages immediately on connect
    state = await task_store.get(task_id)
    if state:
        for msg in state.agent_messages:
            try:
                await websocket.send_json(msg)
            except Exception:
                break

    last_msg_count = len(state.agent_messages) if state else 0

    try:
        while True:
            await asyncio.sleep(1)

            # Poll Redis for new messages — works for BOTH Celery and BackgroundTasks paths
            fresh = await task_store.get(task_id)
            if fresh and len(fresh.agent_messages) > last_msg_count:
                new_msgs = fresh.agent_messages[last_msg_count:]
                for msg in new_msgs:
                    try:
                        await websocket.send_json({
                            **msg,
                            "status": fresh.status,
                            "metrics": fresh.metrics.model_dump(),
                        })
                    except Exception:
                        break
                last_msg_count = len(fresh.agent_messages)

            # Heartbeat ping to detect dead connections
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    finally:
        conns = websocket_connections.get(task_id, [])
        if websocket in conns:
            conns.remove(websocket)


# ── Internal pipeline runner (BackgroundTasks path only) ──────────────────────
async def _run_pipeline_bg(task_id: str) -> None:
    from orchestrator.group_chat import PhantomDevOrchestrator
    state = await task_store.get(task_id)
    if not state:
        return

    async def on_update(s: TaskState) -> None:
        await task_store.save(s)
        await _broadcast(task_id, s)

    final_state = await PhantomDevOrchestrator(on_update=on_update).run(state)
    # Always persist final state to Redis — the orchestrator thread may have failed
    # to call on_update reliably from inside run_in_executor
    if final_state:
        await task_store.save(final_state)
        logger.info("Task %s final state saved to Redis: %s", task_id, final_state.status)


# ── File-state bridge: sync orchestrator file writes back to Redis ─────────────
async def _get_fresh_state(task_id: str) -> Optional[TaskState]:
    """
    The orchestrator writes state to workspace/.state/{task_id}.json after every
    agent turn (sync, works from thread context). Redis may lag behind.
    This helper reads the file, updates Redis if file is newer, returns freshest state.
    """
    redis_state = await task_store.get(task_id)

    try:
        from orchestrator.group_chat import load_state_from_file
        file_state = load_state_from_file(task_id)
        if file_state and (
            redis_state is None or
            file_state.updated_at > redis_state.updated_at
        ):
            # File is newer — sync back to Redis and return file state
            await task_store.save(file_state)
            return file_state
    except Exception as e:
        logger.debug("File state bridge skipped: %s", e)

    return redis_state


# ── WebSocket broadcaster ──────────────────────────────────────────────────────
async def _broadcast(task_id: str, state: TaskState) -> None:
    connections = websocket_connections.get(task_id, [])
    if not connections or not state.agent_messages:
        return
    latest = state.agent_messages[-1]
    dead = []
    for ws in connections:
        try:
            await ws.send_json({
                **latest,
                "status": state.status,
                "metrics": state.metrics.model_dump(),
            })
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)