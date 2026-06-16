"""
worker/celery_app.py
────────────────────
Celery worker for PhantomDev pipeline execution.
Moves agent pipeline off FastAPI BackgroundTasks into a proper
queue with retry logic, timeout enforcement, and worker isolation.

Start worker:
    celery -A worker.celery_app worker --loglevel=info --concurrency=2

Monitor:
    celery -A worker.celery_app flower --port=5555
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from celery import Celery
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Celery app ────────────────────────────────────────────────────────────────
celery_app = Celery(
    "phantomdev",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    # Task settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Retry settings
    task_acks_late=True,               # re-queue on worker crash
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    task_default_retry_delay=30,       # 30s between retries

    # Timeout — agent pipeline max 45 min
    task_soft_time_limit=2700,         # 45 min soft limit → raises SoftTimeLimitExceeded
    task_time_limit=2880,              # 48 min hard kill

    # Concurrency — limit to 2 pipelines simultaneously (Ollama bottleneck)
    worker_concurrency=2,
    worker_prefetch_multiplier=1,

    # Result expiry
    result_expires=86400 * 7,          # 7 days

    # Routing
    task_routes={
        "worker.celery_app.run_pipeline": {"queue": "pipeline"},
    },
    task_default_queue="pipeline",
)


@celery_app.task(
    bind=True,
    name="worker.celery_app.run_pipeline",
    max_retries=2,
    soft_time_limit=2700,
    time_limit=2880,
)
def run_pipeline(self, task_id: str, state_json: str) -> dict:
    """
    Execute the PhantomDev agent pipeline for one task.
    Receives serialised TaskState JSON, runs the full pipeline,
    saves result back to Redis.
    """
    from orchestrator.state import TaskState, TaskStatus
    from orchestrator.group_chat import PhantomDevOrchestrator

    logger.info(f"Worker starting pipeline for task {task_id}")

    try:
        state = TaskState.model_validate_json(state_json)
    except Exception as e:
        logger.error(f"Failed to deserialise TaskState: {e}")
        return {"status": "error", "task_id": task_id, "error": str(e)}

    # Save state updates to Redis as pipeline runs
    def on_update(updated_state: TaskState) -> None:
        try:
            # Sync Redis write from sync context
            import redis as sync_redis
            r = sync_redis.from_url(REDIS_URL, decode_responses=True)
            key = f"phantomdev:task:{updated_state.task_id}"
            r.setex(key, 86400 * 7, updated_state.model_dump_json())
            r.sadd("phantomdev:task_ids", updated_state.task_id)
            r.close()
        except Exception as e:
            logger.warning(f"Redis update failed during pipeline: {e}")

    try:
        orchestrator = PhantomDevOrchestrator(on_update=on_update)
        # Run async pipeline in sync Celery context
        final_state = asyncio.get_event_loop().run_until_complete(
            orchestrator.run(state)
        )
        on_update(final_state)
        logger.info(f"Pipeline complete for {task_id}: {final_state.status}")
        return {
            "status": final_state.status.value,
            "task_id": task_id,
            "pr_url": final_state.pr_url,
            "coverage": final_state.metrics.coverage_pct,
        }

    except Exception as exc:
        logger.exception(f"Pipeline error for {task_id}: {exc}")
        # Retry up to max_retries times
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            # Mark task as failed in Redis
            try:
                state.fail(f"Max retries exceeded: {exc}")
                on_update(state)
            except Exception:
                pass
            return {"status": "failed", "task_id": task_id, "error": str(exc)}
