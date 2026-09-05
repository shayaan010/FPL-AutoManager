"""PostgreSQL connection pool and queries (asyncpg)."""
from __future__ import annotations

import os
from typing import Optional

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/fpl_automanager")

_pool: Optional[asyncpg.Pool] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS transfers (
    id SERIAL PRIMARY KEY,
    gameweek INT NOT NULL,
    player_out_id INT NOT NULL,
    player_out_name TEXT NOT NULL,
    player_in_id INT NOT NULL,
    player_in_name TEXT NOT NULL,
    selling_price INT NOT NULL,
    purchase_price INT NOT NULL,
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    points_gained INT
);
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def init_db() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def insert_transfer(
    gameweek: int,
    player_out_id: int,
    player_out_name: str,
    player_in_id: int,
    player_in_name: str,
    selling_price: int,
    purchase_price: int,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO transfers
                (gameweek, player_out_id, player_out_name, player_in_id, player_in_name,
                 selling_price, purchase_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            gameweek, player_out_id, player_out_name, player_in_id, player_in_name,
            selling_price, purchase_price,
        )
        return row["id"]


async def get_transfers(limit: int = 100) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM transfers ORDER BY executed_at DESC LIMIT $1", limit
        )
        return [dict(r) for r in rows]
