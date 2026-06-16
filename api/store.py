"""
api/store.py
────────────
Redis-backed task store.
Replaces the in-memory dict in main.py.
Tasks survive API restarts, crashes, and horizontal scaling.

Usage:
    from api.store import task_store
    await task_store.save(state)
    state = await task_store.get(task_id)
    tasks = await task_store.list_all()
"""
from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

import redis.asyncio as aioredis

from orchestrator.state import TaskState

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TASK_TTL_SECONDS = 60 * 60 * 24 * 7   # 7 days
TASK_PREFIX = "phantomdev:task:"
TASK_INDEX  = "phantomdev:task_ids"


class RedisTaskStore:
    """
    Async Redis store for TaskState objects.
    Falls back to in-memory if Redis is unavailable (dev mode).
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._fallback: dict[str, TaskState] = {}
        self._use_fallback = False

    async def connect(self) -> None:
        try:
            self._redis = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await self._redis.ping()
            logger.info(f"Redis connected: {REDIS_URL}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), using in-memory fallback")
            self._use_fallback = True

    async def save(self, state: TaskState) -> None:
        """Persist a TaskState to Redis (or fallback)."""
        if self._use_fallback:
            self._fallback[state.task_id] = state
            return
        try:
            data = state.model_dump_json()
            key = f"{TASK_PREFIX}{state.task_id}"
            pipe = self._redis.pipeline()
            pipe.setex(key, TASK_TTL_SECONDS, data)
            pipe.sadd(TASK_INDEX, state.task_id)
            pipe.expire(TASK_INDEX, TASK_TTL_SECONDS)
            await pipe.execute()
        except Exception as e:
            logger.error(f"Redis save failed for {state.task_id}: {e}")
            self._fallback[state.task_id] = state

    async def get(self, task_id: str) -> Optional[TaskState]:
        """Load a TaskState from Redis."""
        if self._use_fallback:
            return self._fallback.get(task_id)
        try:
            key = f"{TASK_PREFIX}{task_id}"
            data = await self._redis.get(key)
            if not data:
                return None
            return TaskState.model_validate_json(data)
        except Exception as e:
            logger.error(f"Redis get failed for {task_id}: {e}")
            return self._fallback.get(task_id)

    async def list_all(self) -> List[TaskState]:
        """Return all tasks sorted by created_at descending."""
        if self._use_fallback:
            return sorted(self._fallback.values(), key=lambda t: t.created_at, reverse=True)
        try:
            task_ids = await self._redis.smembers(TASK_INDEX)
            if not task_ids:
                return []
            pipe = self._redis.pipeline()
            for tid in task_ids:
                pipe.get(f"{TASK_PREFIX}{tid}")
            results = await pipe.execute()
            tasks = []
            for r in results:
                if r:
                    try:
                        tasks.append(TaskState.model_validate_json(r))
                    except Exception:
                        pass
            return sorted(tasks, key=lambda t: t.created_at, reverse=True)
        except Exception as e:
            logger.error(f"Redis list_all failed: {e}")
            return list(self._fallback.values())

    async def delete(self, task_id: str) -> None:
        """Delete a task from Redis."""
        if self._use_fallback:
            self._fallback.pop(task_id, None)
            return
        try:
            pipe = self._redis.pipeline()
            pipe.delete(f"{TASK_PREFIX}{task_id}")
            pipe.srem(TASK_INDEX, task_id)
            await pipe.execute()
        except Exception as e:
            logger.error(f"Redis delete failed for {task_id}: {e}")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()


# Singleton
task_store = RedisTaskStore()
