"""Redis helpers: player data cache, session cookie persistence."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")

BOOTSTRAP_KEY = "fpl:bootstrap"
BOOTSTRAP_TTL = 1800  # 30 minutes, per FPL rate-limit guidance

TOKEN_KEY = "fpl:session_token"
TEAM_ID_KEY = "fpl:team_id"

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


async def get_bootstrap_cache() -> Optional[dict]:
    return await get_json(BOOTSTRAP_KEY)


async def set_bootstrap_cache(data: dict) -> None:
    await set_json(BOOTSTRAP_KEY, data, ex=BOOTSTRAP_TTL)


async def save_session_token(bundle: dict) -> None:
    # No TTL: the token is re-validated on use, and the user re-signs in when
    # it eventually expires.
    await set_json(TOKEN_KEY, bundle)


async def load_session_token() -> Optional[dict]:
    return await get_json(TOKEN_KEY)


async def set_team_id(team_id: int) -> None:
    await get_client().set(TEAM_ID_KEY, str(team_id))


async def get_team_id() -> Optional[int]:
    raw = await get_client().get(TEAM_ID_KEY)
    return int(raw) if raw is not None else None


async def clear_session() -> None:
    await get_client().delete(TOKEN_KEY, TEAM_ID_KEY)
