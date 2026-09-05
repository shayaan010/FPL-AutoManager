"""
FPL API wrapper (read + write).

The FPL API is undocumented and reverse-engineered from browser traffic on
fantasy.premierleague.com. If the transfer endpoint starts failing, check
devtools on the live site first -- these contracts can change without notice.

Auth is an `Authorization: Bearer <access_token>` header; the old
sessionid/pl_profile session cookies no longer exist. Each user supplies
their own token, so a client instance is cheap and scoped to one user --
one shared HTTP connection pool underneath, with the token passed per call.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from cache import get_bootstrap_cache, set_bootstrap_cache
from models import TransferPayload

logger = logging.getLogger("fpl_client")

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
MY_TEAM_URL = "https://fantasy.premierleague.com/api/my-team/{team_id}/"
ME_URL = "https://fantasy.premierleague.com/api/me/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"
TRANSFERS_URL = "https://fantasy.premierleague.com/api/transfers/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

# One pool shared by every user; per-user auth travels in request headers.
_http: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=15.0, follow_redirects=True)
    return _http


async def aclose() -> None:
    global _http
    if _http is not None:
        await _http.aclose()
        _http = None


class FPLAuthError(Exception):
    pass


class FPLTransferError(Exception):
    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = payload


class FPLClient:
    """Scoped to a single user's FPL session (or none, for public data)."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token

    @property
    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}

    # ------------------------------------------------------------- auth --- #

    async def get_player(self) -> Optional[dict]:
        """The signed-in player, or None if the token is missing/expired."""
        if not self.access_token:
            return None
        try:
            resp = await _client().get(ME_URL, headers=self._auth_headers)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            return (resp.json() or {}).get("player")
        except ValueError:
            return None

    async def verify(self) -> dict:
        """Raise unless the token currently works, returning the player."""
        player = await self.get_player()
        if not player:
            raise FPLAuthError("That FPL session was rejected -- reconnect your account")
        return player

    async def get_my_entry_id(self) -> Optional[int]:
        player = await self.get_player()
        entry = (player or {}).get("entry")
        return int(entry) if entry else None

    # ------------------------------------------------------------ reads --- #

    async def get_bootstrap(self, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = await get_bootstrap_cache()
            if cached is not None:
                return cached
        resp = await _client().get(BOOTSTRAP_URL)
        resp.raise_for_status()
        data = resp.json()
        await set_bootstrap_cache(data)
        return data

    async def get_my_team(self, team_id: int) -> dict:
        resp = await _client().get(MY_TEAM_URL.format(team_id=team_id), headers=self._auth_headers)
        resp.raise_for_status()
        return resp.json()

    async def get_fixtures(self, event: Optional[int] = None) -> list[dict]:
        params = {"event": event} if event is not None else {}
        resp = await _client().get(FIXTURES_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_gameweek_info(self) -> dict:
        bootstrap = await self.get_bootstrap()
        events = bootstrap.get("events", [])
        current = next((e for e in events if e.get("is_current")), None)
        nxt = next((e for e in events if e.get("is_next")), None)
        return {
            "current_event": current.get("id") if current else None,
            "next_event": nxt.get("id") if nxt else None,
            "next_deadline_time": nxt.get("deadline_time") if nxt else None,
        }

    # ------------------------------------------------------------ write --- #

    async def execute_transfer(self, transfer: TransferPayload) -> dict:
        if not self.access_token:
            raise FPLTransferError("Not signed in to FPL")

        body = {
            "entry": transfer.entry,
            "event": transfer.event,
            "chip": transfer.chip,
            "transfers": [
                {
                    "element_in": transfer.element_in,
                    "element_out": transfer.element_out,
                    "purchase_price": transfer.purchase_price,
                    "selling_price": transfer.selling_price,
                }
            ],
        }

        resp = await _client().post(
            TRANSFERS_URL,
            json=body,
            headers={
                **self._auth_headers,
                "Referer": "https://fantasy.premierleague.com/",
                "Content-Type": "application/json",
            },
        )

        if resp.status_code not in (200, 201):
            try:
                payload = resp.json()
            except ValueError:
                payload = {"raw": resp.text}
            raise FPLTransferError(f"Transfer rejected ({resp.status_code})", payload=payload)

        # A successful transfer comes back 200 with an empty body -- parsing that
        # as JSON used to raise, which made a completed transfer look like a
        # failure and skipped logging it.
        if not resp.content:
            return {"status": "ok"}
        try:
            return resp.json()
        except ValueError:
            return {"status": "ok", "raw": resp.text}


def parse_deadline(deadline_iso: str) -> datetime:
    return datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))


def minutes_until(deadline: datetime) -> int:
    now = datetime.now(timezone.utc)
    delta = deadline - now
    return max(0, int(delta.total_seconds() // 60))
