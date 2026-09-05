"""
FPL API wrapper (read + write).

The FPL API is undocumented and reverse-engineered from browser traffic on
fantasy.premierleague.com. If the transfer endpoint starts failing, check
devtools on the live site first -- these contracts can change without notice.

Login itself is no longer handled here: FPL moved auth to OAuth2/OIDC
(PingOne), and the API now authenticates with an `Authorization: Bearer
<access_token>` header -- the old sessionid/pl_profile session cookies no
longer exist at all. See browser_login.py -- a real browser window handles
the actual login, and this client adopts the resulting token via
load_token().
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from cache import (
    get_bootstrap_cache,
    load_session_token,
    save_session_token,
    set_bootstrap_cache,
)
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


class FPLAuthError(Exception):
    pass


class FPLTransferError(Exception):
    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = payload


class FPLClient:
    def __init__(self):
        self.session = httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=15.0, follow_redirects=True)
        self._logged_in = False

    async def aclose(self):
        await self.session.aclose()


    def _apply_token(self, access_token: str) -> None:
        self.session.headers["Authorization"] = f"Bearer {access_token}"

    async def _authenticated_ok(self) -> bool:
        """An authenticated /api/me/ returns a non-null player."""
        try:
            resp = await self.session.get(ME_URL)
        except httpx.HTTPError:
            return False
        if resp.status_code != 200:
            return False
        try:
            return bool((resp.json() or {}).get("player"))
        except ValueError:
            return False

    async def restore_session(self) -> bool:
        """Try to reuse a previously saved token (from Redis) instead of logging in again."""
        bundle = await load_session_token()
        if not bundle or not bundle.get("access_token"):
            return False
        self._apply_token(bundle["access_token"])
        if await self._authenticated_ok():
            self._logged_in = True
            return True
        self.session.headers.pop("Authorization", None)
        return False

    def is_logged_in(self) -> bool:
        return self._logged_in

    async def logout(self) -> None:
        self.session.headers.pop("Authorization", None)
        self.session.cookies.clear()
        self._logged_in = False

    async def load_token(self, bundle: dict) -> None:
        """Adopt an OIDC token bundle captured from a real browser sign-in."""
        access_token = (bundle or {}).get("access_token")
        if not access_token:
            raise FPLAuthError("No access token found in that sign-in")

        self._apply_token(access_token)
        if not await self._authenticated_ok():
            self.session.headers.pop("Authorization", None)
            raise FPLAuthError("That FPL session was rejected -- try signing in again")

        self._logged_in = True
        await save_session_token(bundle)


    async def get_bootstrap(self, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = await get_bootstrap_cache()
            if cached is not None:
                return cached
        resp = await self.session.get(BOOTSTRAP_URL)
        resp.raise_for_status()
        data = resp.json()
        await set_bootstrap_cache(data)
        return data

    async def get_my_entry_id(self) -> Optional[int]:
        """The logged-in user's own team id, straight from /api/me/."""
        resp = await self.session.get(ME_URL)
        if resp.status_code != 200:
            return None
        player = (resp.json() or {}).get("player") or {}
        entry = player.get("entry")
        return int(entry) if entry else None

    async def get_my_team(self, team_id: int) -> dict:
        resp = await self.session.get(MY_TEAM_URL.format(team_id=team_id))
        resp.raise_for_status()
        return resp.json()

    async def get_fixtures(self, event: Optional[int] = None) -> list[dict]:
        params = {"event": event} if event is not None else {}
        resp = await self.session.get(FIXTURES_URL, params=params)
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


    async def execute_transfer(self, transfer: TransferPayload) -> dict:
        # Auth is the Bearer token on the session; the old CSRF cookie went
        # away with the Django login.
        if not self._logged_in:
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

        resp = await self.session.post(
            TRANSFERS_URL,
            json=body,
            headers={
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
