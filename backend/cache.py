"""Redis helpers: shared player-data cache and per-user login sessions."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis.asyncio as redis

from security import SESSION_TTL_SECONDS

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")

BOOTSTRAP_KEY = "fpl:bootstrap"
BOOTSTRAP_TTL = 1800  # 30 minutes, per FPL rate-limit guidance

SESSION_PREFIX = "session:"

_client: Optional[redis.Redis] = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


async def get_json(key: str) -> Optional[Any]:
    raw = await get_client().get(key)
    return json.loads(raw) if raw is not None else None


async def set_json(key: str, value: Any, ex: Optional[int] = None) -> None:
    await get_client().set(key, json.dumps(value), ex=ex)


# bootstrap-static is public data and identical for everyone, so it stays a
# single shared cache rather than one copy per user.
async def get_bootstrap_cache() -> Optional[dict]:
    return await get_json(BOOTSTRAP_KEY)


async def set_bootstrap_cache(data: dict) -> None:
    await set_json(BOOTSTRAP_KEY, data, ex=BOOTSTRAP_TTL)


# ------------------------------------------------------------- sessions --- #


async def create_session(session_id: str, user_id: int) -> None:
    await get_client().set(SESSION_PREFIX + session_id, str(user_id), ex=SESSION_TTL_SECONDS)


async def get_session_user_id(session_id: str) -> Optional[int]:
    raw = await get_client().get(SESSION_PREFIX + session_id)
    return int(raw) if raw is not None else None


async def delete_session(session_id: str) -> None:
    await get_client().delete(SESSION_PREFIX + session_id)
