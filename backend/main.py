"""FastAPI app: routes + WebSocket server for FPL Auto-Manager."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Playwright needs ProactorEventLoop for subprocess support on Windows, but
# uvicorn's default loop there is SelectorEventLoop -- under that, browser
# launch doesn't error, it just hangs forever. Must be set before uvicorn
# creates its event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

import cache
import db
from browser_login import clear_profile, login_via_browser
from fpl_client import FPLAuthError, FPLClient, FPLTransferError
from models import (
    AuthStatus,
    BrowserLoginStartRequest,
    BrowserLoginState,
    GameweekInfo,
    TokenLoginRequest,
    TransferExecuteRequest,
    TransferPayload,
    TransferPreviewRequest,
)
from optimizer import POSITION_NAMES, build_reasons, build_scored_players, recommend_transfers
from scheduler import scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

fpl_client = FPLClient()
browser_login_state: dict = {"status": "idle", "error": None}


class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: dict):
        stale = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


ws_manager = WSManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    if await fpl_client.restore_session():
        logger.info("Restored FPL session from a previous login")
    else:
        logger.info("No active FPL session -- waiting for a user to connect via POST /auth/browser/start")
    start_scheduler(fpl_client, ws_manager)
    yield
    scheduler.shutdown(wait=False)
    await fpl_client.aclose()
    await db.close_db()


app = FastAPI(title="FPL Auto-Manager", lifespan=lifespan)

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Without this, an unhandled error returns a bare 500 with no CORS headers,
    which the browser surfaces as an opaque "Failed to fetch" -- hiding what
    actually went wrong.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": {"message": f"Server error: {exc}"}},
        headers={"Access-Control-Allow-Origin": FRONTEND_ORIGIN, "Access-Control-Allow-Credentials": "true"},
    )


async def _require_connection() -> int:
    team_id = await cache.get_team_id()
    if not team_id or not fpl_client.is_logged_in():
        raise HTTPException(status_code=401, detail="FPL account not connected")
    return team_id


async def _get_scored_players():
    bootstrap = await fpl_client.get_bootstrap()
    fixtures = await fpl_client.get_fixtures()
    return bootstrap, fixtures, build_scored_players(bootstrap, fixtures)


async def _verify_and_store_team(team_id: int) -> None:
    try:
        await fpl_client.get_my_team(team_id)
    except Exception:
        raise HTTPException(status_code=400, detail="That team ID couldn't be found on your FPL account")
    await cache.set_team_id(team_id)


@app.post("/auth/logout")
async def logout():
    global browser_login_state
    await fpl_client.logout()
    await cache.clear_session()
    # Also sign the browser profile out, otherwise the next sign-in silently
    # reconnects to the same FPL account and you can't switch.
    clear_profile()
    browser_login_state = {"status": "idle", "error": None}
    return {"status": "ok"}


async def _run_browser_login(fresh: bool = False):
    global browser_login_state
    try:
        bundle = await login_via_browser(fresh=fresh)
        await fpl_client.load_token(bundle)

        # The session already tells us which team is theirs -- no need to make
        # the user go find their team id.
        team_id = await fpl_client.get_my_entry_id()
        if not team_id:
            raise RuntimeError("Signed in, but couldn't determine your team ID")
        await cache.set_team_id(team_id)

        browser_login_state = {"status": "success", "error": None}
    except Exception as e:
        logger.exception("Browser sign-in failed")
        browser_login_state = {"status": "error", "error": str(e)}


@app.post("/auth/browser/start")
async def start_browser_login(req: BrowserLoginStartRequest | None = None):
    global browser_login_state
    if browser_login_state.get("status") == "waiting":
        raise HTTPException(status_code=409, detail="A sign-in is already in progress")
    browser_login_state = {"status": "waiting", "error": None}
    asyncio.create_task(_run_browser_login(fresh=bool(req and req.fresh)))
    return browser_login_state


@app.get("/auth/browser/status")
async def browser_login_status() -> BrowserLoginState:
    return BrowserLoginState(**browser_login_state)


@app.post("/auth/token")
async def login_with_token(req: TokenLoginRequest):
    """
    Adopt an FPL access token captured outside this app -- a manual fallback
    if the browser sign-in can't run. The team id is derived from the token's
    own session when not given.
    """
    try:
        await fpl_client.load_token({"access_token": req.access_token})
    except FPLAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    team_id = req.team_id or await fpl_client.get_my_entry_id()
    if not team_id:
        raise HTTPException(status_code=400, detail="Couldn't determine your team ID from that session")

    await _verify_and_store_team(team_id)
    return {"status": "ok", "team_id": team_id}


@app.get("/auth/status")
async def auth_status() -> AuthStatus:
    team_id = await cache.get_team_id()
    if not fpl_client.is_logged_in() and team_id is not None:
        await fpl_client.restore_session()
    connected = bool(team_id) and fpl_client.is_logged_in()
    return AuthStatus(connected=connected, team_id=team_id if connected else None)


@app.get("/squad")
async def get_squad():
    team_id = await _require_connection()
    try:
        my_team = await fpl_client.get_my_team(team_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch squad from FPL: {e}")

    _, _, scored_players = await _get_scored_players()
    by_id = {p.id: p for p in scored_players}

    picks = my_team.get("picks", [])
    squad = []
    for pick in picks:
        player = by_id.get(pick["element"])
        if player:
            squad.append({
                **player.model_dump(),
                "position": pick.get("position"),
                "is_captain": pick.get("is_captain"),
                "is_vice_captain": pick.get("is_vice_captain"),
                "multiplier": pick.get("multiplier"),
            })
    squad.sort(key=lambda p: p.get("position") or 99)

    transfers_info = my_team.get("transfers", {})
    return {
        "squad": squad,
        "bank": transfers_info.get("bank"),
        "team_value": transfers_info.get("value"),
        "free_transfers": transfers_info.get("limit"),
    }


@app.get("/recommendations")
async def get_recommendations():
    team_id = await _require_connection()
    try:
        my_team = await fpl_client.get_my_team(team_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch squad from FPL: {e}")

    _, _, scored_players = await _get_scored_players()

    squad_ids = [pick["element"] for pick in my_team.get("picks", [])]
    transfers_info = my_team.get("transfers", {})
    bank = transfers_info.get("bank", 0)
    free_transfers = transfers_info.get("limit") or 1

    recs = recommend_transfers(squad_ids, bank, scored_players, free_transfers)
    if not recs:
        raise HTTPException(status_code=404, detail="No viable transfer found")
    return recs


@app.get("/players/search")
async def search_players(q: str = "", element_type: int | None = None, limit: int = 25):
    """Name search over all players, for building a transfer by hand."""
    _, _, scored_players = await _get_scored_players()

    needle = q.strip().lower()
    matches = [
        p for p in scored_players
        if (element_type is None or p.element_type == element_type)
        and (not needle or needle in p.web_name.lower() or needle in p.team_short_name.lower())
    ]
    matches.sort(key=lambda p: p.score, reverse=True)
    return matches[:limit]


async def _validate_transfer(my_team: dict, scored_players: list, element_out: int, element_in: int):
    """
    Manual transfers can be nonsense in ways the recommender never produces --
    wrong position, unaffordable, already owned -- so check before we ask FPL.
    """
    by_id = {p.id: p for p in scored_players}
    picks = my_team.get("picks", [])
    squad_ids = {p.get("element") for p in picks}

    out_pick = next((p for p in picks if p.get("element") == element_out), None)
    if out_pick is None:
        raise HTTPException(status_code=400, detail="That player isn't in your squad")
    if element_in in squad_ids:
        raise HTTPException(status_code=400, detail="You already own the player you're bringing in")

    player_out = by_id.get(element_out)
    player_in = by_id.get(element_in)
    if player_in is None or player_out is None:
        raise HTTPException(status_code=400, detail="Unknown player")

    if player_in.element_type != player_out.element_type:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Positions must match — {player_out.web_name} is a "
                f"{POSITION_NAMES[player_out.element_type]} but {player_in.web_name} is a "
                f"{POSITION_NAMES[player_in.element_type]}"
            ),
        )

    selling_price = out_pick.get("selling_price", player_out.now_cost)
    bank = (my_team.get("transfers") or {}).get("bank", 0)
    budget = selling_price + bank
    if player_in.now_cost > budget:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough money — {player_in.web_name} costs £{player_in.now_cost / 10:.1f}m "
                f"but you only have £{budget / 10:.1f}m available"
            ),
        )

    return out_pick, player_out, player_in, selling_price


@app.post("/transfer/preview")
async def preview_transfer(req: TransferPreviewRequest):
    """Validate a hand-built transfer and show its effect, without executing."""
    team_id = await _require_connection()
    my_team = await fpl_client.get_my_team(team_id)
    _, _, scored_players = await _get_scored_players()

    _, player_out, player_in, selling_price = await _validate_transfer(
        my_team, scored_players, req.element_out, req.element_in
    )

    bank = (my_team.get("transfers") or {}).get("bank", 0)
    free_transfers = (my_team.get("transfers") or {}).get("limit")

    return {
        "player_out": player_out,
        "player_in": player_in,
        "score_delta": round(player_in.score - player_out.score, 3),
        "reasons": build_reasons(player_out.breakdown, player_in.breakdown),
        "selling_price": selling_price,
        "purchase_price": player_in.now_cost,
        "bank_after": bank + selling_price - player_in.now_cost,
        "is_hit": free_transfers is not None and free_transfers <= 0,
        "free_transfers": free_transfers,
    }


@app.post("/transfer/execute")
async def execute_transfer(req: TransferExecuteRequest):
    team_id = await _require_connection()

    gw_info = await fpl_client.get_gameweek_info()
    event = req.event or gw_info.get("next_event") or gw_info.get("current_event")
    if event is None:
        raise HTTPException(status_code=400, detail="Could not determine target gameweek")

    my_team = await fpl_client.get_my_team(team_id)

    if not req.accept_hit:
        free_transfers = (my_team.get("transfers") or {}).get("limit")
        if free_transfers is not None and free_transfers <= 0:
            raise HTTPException(
                status_code=409,
                detail="This transfer would cost a 4-point hit. Resubmit with accept_hit=true to confirm.",
            )

    # Validate here too -- manual transfers can be invalid in ways the
    # recommender never produces. FPL pays out the pick's own selling_price,
    # which lags now_cost once the player's price has moved.
    _, _, scored_players = await _get_scored_players()
    _, _, _, selling_price = await _validate_transfer(
        my_team, scored_players, req.element_out, req.element_in
    )

    payload = TransferPayload(
        entry=team_id,
        element_in=req.element_in,
        purchase_price=req.element_in_cost,
        element_out=req.element_out,
        selling_price=selling_price,
        event=event,
    )

    try:
        result = await fpl_client.execute_transfer(payload)
    except FPLTransferError as e:
        raise HTTPException(status_code=422, detail={"message": str(e), "fpl_response": e.payload})

    transfer_id = await db.insert_transfer(
        gameweek=event,
        player_out_id=req.element_out,
        player_out_name=req.player_out_name,
        player_in_id=req.element_in,
        player_in_name=req.player_in_name,
        selling_price=selling_price,
        purchase_price=req.element_in_cost,
    )

    return {"status": "ok", "transfer_id": transfer_id, "fpl_response": result}


@app.get("/history")
async def get_history(limit: int = 100):
    return await db.get_transfers(limit=limit)


@app.get("/players")
async def get_players():
    _, _, scored_players = await _get_scored_players()
    return scored_players


@app.get("/gameweek")
async def get_gameweek() -> GameweekInfo:
    gw = await fpl_client.get_gameweek_info()
    return GameweekInfo(**gw)


@app.websocket("/ws/deadline")
async def ws_deadline(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Client doesn't need to send anything; just keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
