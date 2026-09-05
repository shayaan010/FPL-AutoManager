from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from cache import get_client

logger = logging.getLogger("ratelimit")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce(key: str, limit: int, window_seconds: int, message: str) -> None:
    redis_key = f"ratelimit:{key}"
    try:
        client = get_client()
        hits = await client.incr(redis_key)
        if hits == 1:
            await client.expire(redis_key, window_seconds)
    except Exception:
        logger.exception("Rate limit check failed for %s; allowing request", key)
        return

    if hits > limit:
        raise HTTPException(
            status_code=429,
            detail=message,
            headers={"Retry-After": str(window_seconds)},
        )


async def limit_login(request: Request, email: str) -> None:
    ip = client_ip(request)
    await enforce(f"login:ip:{ip}", limit=10, window_seconds=300,
                  message="Too many sign-in attempts. Try again in a few minutes.")
    await enforce(f"login:email:{email.lower()}", limit=5, window_seconds=900,
                  message="Too many sign-in attempts for this account. Try again shortly.")


async def limit_register(request: Request) -> None:
    await enforce(f"register:ip:{client_ip(request)}", limit=5, window_seconds=3600,
                  message="Too many accounts created from this address. Try again later.")


async def limit_link_token(request: Request, user_id: int) -> None:
    await enforce(f"link:user:{user_id}", limit=20, window_seconds=300,
                  message="Too many connection attempts. Try again in a few minutes.")


async def limit_transfer(user_id: int) -> None:
    await enforce(f"transfer:user:{user_id}", limit=20, window_seconds=3600,
                  message="Too many transfers in a short period. Slow down.")
