from __future__ import annotations

import os
from typing import Optional

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/fpl_automanager")

_pool: Optional[asyncpg.Pool] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fpl_connections (
    user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    team_id INT,
    token_encrypted TEXT NOT NULL,
    connected_at TIMESTAMPTZ DEFAULT NOW()
);

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

-- transfers predates accounts, so add the owner column separately.
ALTER TABLE transfers ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS transfers_user_idx ON transfers (user_id, executed_at DESC);
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


async def create_user(email: str, password_hash: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email",
                email, password_hash,
            )
        except asyncpg.UniqueViolationError:
            return None
        return dict(row)


async def get_user_by_email(email: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
        return dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, email FROM users WHERE id = $1", user_id)
        return dict(row) if row else None


async def update_password_hash(user_id: int, password_hash: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash = $1 WHERE id = $2", password_hash, user_id)


async def save_fpl_connection(user_id: int, team_id: Optional[int], token_encrypted: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fpl_connections (user_id, team_id, token_encrypted, connected_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET team_id = EXCLUDED.team_id,
                    token_encrypted = EXCLUDED.token_encrypted,
                    connected_at = NOW()
            """,
            user_id, team_id, token_encrypted,
        )


async def get_fpl_connection(user_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM fpl_connections WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def delete_fpl_connection(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM fpl_connections WHERE user_id = $1", user_id)


async def insert_transfer(
    user_id: int,
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
                (user_id, gameweek, player_out_id, player_out_name, player_in_id,
                 player_in_name, selling_price, purchase_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            user_id, gameweek, player_out_id, player_out_name, player_in_id,
            player_in_name, selling_price, purchase_price,
        )
        return row["id"]


async def get_transfers(user_id: int, limit: int = 100) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM transfers WHERE user_id = $1 ORDER BY executed_at DESC LIMIT $2",
            user_id, limit,
        )
        return [dict(r) for r in rows]
