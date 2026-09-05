from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fpl_client import FPLClient, minutes_until, parse_deadline

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()


def start_scheduler(fpl_client: FPLClient, ws_manager) -> None:
    async def refresh_player_cache():
        try:
            await fpl_client.get_bootstrap(force_refresh=True)
            logger.info("Refreshed bootstrap cache")
        except Exception:
            logger.exception("Failed to refresh bootstrap cache")

    async def deadline_broadcast():
        try:
            gw = await fpl_client.get_gameweek_info()
            deadline_iso = gw.get("next_deadline_time")
            if not deadline_iso:
                return
            deadline = parse_deadline(deadline_iso)
            minutes_left = minutes_until(deadline)
            await ws_manager.broadcast({"minutes_left": minutes_left, "next_event": gw.get("next_event")})
        except Exception:
            logger.exception("Failed to broadcast deadline countdown")

    scheduler.add_job(refresh_player_cache, "interval", minutes=30, id="refresh_player_cache")
    scheduler.add_job(deadline_broadcast, "interval", minutes=1, id="deadline_broadcast")

    scheduler.start()
