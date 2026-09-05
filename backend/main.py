"""FastAPI app: routes + WebSocket server for FPL Auto-Manager."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
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
import fpl_client as fpl
import security
from fpl_client import FPLAuthError, FPLClient, FPLTransferError
from models import (
    AuthStatus,
    BrowserLoginStartRequest,
    BrowserLoginState,
    GameweekInfo,
    LoginRequest,
    RegisterRequest,
    TokenLoginRequest,
    TransferExecuteRequest,
    TransferPayload,
    TransferPreviewRequest,
    UserOut,
)
from optimizer import POSITION_NAMES, build_reasons, build_scored_players, recommend_transfers
from scheduler import scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Server-side browser sign-in only works when a person is sitting at the
# machine running the backend, so it's a local-dev convenience and is off by
# default in a deployed environment.
ENABLE_BROWSER_LOGIN = os.environ.get("ENABLE_BROWSER_LOGIN", "").lower() in ("1", "true", "yes")


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
    start_scheduler(FPLClient(), ws_manager)
    yield
    scheduler.shutdown(wait=False)
    await fpl.aclose()
    await db.close_db()


app = FastAPI(title="FPL Auto-Manager", lifespan=lifespan)

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
IS_PRODUCTION = os.environ.get("ENVIRONMENT", "").lower() == "production" or FRONTEND_ORIGIN.startswith("https://")

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


# ------------------------------------------------------------ accounts --- #


async def current_user(request: Request) -> dict:
    """The signed-in app user, or 401."""
    session_id = request.cookies.get(security.SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not signed in")
    user_id = await cache.get_session_user_id(session_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Session expired -- sign in again")
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


async def current_fpl(user: dict = Depends(current_user)) -> tuple[dict, FPLClient, int]:
    """The user's linked FPL session, or 428 if they haven't connected one."""
    conn = await db.get_fpl_connection(user["id"])
    if not conn:
        raise HTTPException(status_code=428, detail="FPL account not connected")

    token = security.decrypt(conn["token_encrypted"])
    if not token:
        raise HTTPException(status_code=428, detail="Stored FPL session is unreadable -- reconnect")

    team_id = conn.get("team_id")
    if not team_id:
        raise HTTPException(status_code=428, detail="FPL account not connected")
    return user, FPLClient(token), team_id


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        security.SESSION_COOKIE,
        session_id,
        max_age=security.SESSION_TTL_SECONDS,
        httponly=True,
        # Frontend and API sit on different domains in production, so the
        # cookie has to be SameSite=None -- which browsers only accept when
        # it is also Secure.
        samesite="none" if IS_PRODUCTION else "lax",
        secure=IS_PRODUCTION,
        path="/",
    )


@app.post("/account/register")
async def register(req: RegisterRequest, response: Response) -> UserOut:
    email = req.email.lower().strip()
    user = await db.create_user(email, security.hash_password(req.password))
    if not user:
        raise HTTPException(status_code=409, detail="That email is already registered")

    session_id = security.new_session_id()
    await cache.create_session(session_id, user["id"])
    _set_session_cookie(response, session_id)
    return UserOut(**user)


@app.post("/account/login")
async def login(req: LoginRequest, response: Response) -> UserOut:
    email = req.email.lower().strip()
    user = await db.get_user_by_email(email)
    if not user or not security.verify_password(req.password, user["password_hash"]):
        # Same message either way so the endpoint can't be used to discover
        # which emails are registered.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if security.needs_rehash(user["password_hash"]):
        await db.update_password_hash(user["id"], security.hash_password(req.password))

    session_id = security.new_session_id()
    await cache.create_session(session_id, user["id"])
    _set_session_cookie(response, session_id)
    return UserOut(id=user["id"], email=user["email"])


@app.post("/account/logout")
async def account_logout(request: Request, response: Response):
    session_id = request.cookies.get(security.SESSION_COOKIE)
    if session_id:
        await cache.delete_session(session_id)
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    return {"status": "ok"}


@app.get("/account/me")
async def me(user: dict = Depends(current_user)) -> UserOut:
    return UserOut(**user)


# --------------------------------------------------- fpl account link --- #


@app.get("/auth/status")
async def auth_status(user: dict = Depends(current_user)) -> AuthStatus:
    conn = await db.get_fpl_connection(user["id"])
    if not conn or not conn.get("team_id"):
        return AuthStatus(connected=False)
    return AuthStatus(connected=True, team_id=conn["team_id"])


@app.post("/auth/token")
async def link_fpl_account(req: TokenLoginRequest, user: dict = Depends(current_user)):
    """Link an FPL access token the user captured in their own browser."""
    client = FPLClient(req.access_token)
    try:
        player = await client.verify()
    except FPLAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    team_id = req.team_id or player.get("entry")
    if not team_id:
        raise HTTPException(status_code=400, detail="Couldn't determine your team ID from that session")

    await db.save_fpl_connection(user["id"], int(team_id), security.encrypt(req.access_token))
    return {"status": "ok", "team_id": int(team_id)}


@app.post("/auth/logout")
async def unlink_fpl_account(user: dict = Depends(current_user)):
    await db.delete_fpl_connection(user["id"])
    return {"status": "ok"}


# Local-only convenience: opens a real browser on the machine running the
# backend. Useless when deployed (there's no desktop, and the user is
# elsewhere), so it stays behind ENABLE_BROWSER_LOGIN.
browser_login_state: dict = {"status": "idle", "error": None}


async def _run_browser_login(user_id: int, fresh: bool):
    global browser_login_state
    try:
        from browser_login import login_via_browser

        bundle = await login_via_browser(fresh=fresh)
        access_token = (bundle or {}).get("access_token")
        if not access_token:
            raise RuntimeError("No access token found in that sign-in")

        client = FPLClient(access_token)
        player = await client.verify()
        team_id = player.get("entry")
        if not team_id:
            raise RuntimeError("Signed in, but couldn't determine your team ID")

        await db.save_fpl_connection(user_id, int(team_id), security.encrypt(access_token))
        browser_login_state = {"status": "success", "error": None}
    except Exception as e:
        logger.exception("Browser sign-in failed")
        browser_login_state = {"status": "error", "error": str(e)}


@app.post("/auth/browser/start")
async def start_browser_login(req: BrowserLoginStartRequest | None = None,
                              user: dict = Depends(current_user)):
    global browser_login_state
    if not ENABLE_BROWSER_LOGIN:
        raise HTTPException(
            status_code=501,
            detail="Browser sign-in only works when running locally. Use the bookmarklet instead.",
        )
    if browser_login_state.get("status") == "waiting":
        raise HTTPException(status_code=409, detail="A sign-in is already in progress")
    browser_login_state = {"status": "waiting", "error": None}
    asyncio.create_task(_run_browser_login(user["id"], bool(req and req.fresh)))
    return browser_login_state


@app.get("/auth/browser/status")
async def browser_login_status(user: dict = Depends(current_user)) -> BrowserLoginState:
    return BrowserLoginState(**browser_login_state)


@app.get("/config")
async def config():
    """Lets the frontend show only the connect methods this deployment supports."""
    return {"browser_login": ENABLE_BROWSER_LOGIN}


# ------------------------------------------------------------- shared --- #


async def _get_scored_players(client: Optional[FPLClient] = None):
    client = client or FPLClient()
    bootstrap = await client.get_bootstrap()
    fixtures = await client.get_fixtures()
    return bootstrap, fixtures, build_scored_players(bootstrap, fixtures)


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


# -------------------------------------------------------------- squad --- #


@app.get("/squad")
async def get_squad(ctx: tuple = Depends(current_fpl)):
    _, client, team_id = ctx
    try:
        my_team = await client.get_my_team(team_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            raise HTTPException(status_code=428, detail="Your FPL session expired — reconnect your account")
        raise HTTPException(status_code=502, detail="FPL is not responding right now. Try again shortly.")
    except Exception:
        logger.exception("Failed to fetch squad for team %s", team_id)
        raise HTTPException(status_code=502, detail="FPL is not responding right now. Try again shortly.")

    _, _, scored_players = await _get_scored_players(client)
    by_id = {p.id: p for p in scored_players}

    squad = []
    for pick in my_team.get("picks", []):
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
async def get_recommendations(ctx: tuple = Depends(current_fpl)):
    _, client, team_id = ctx
    try:
        my_team = await client.get_my_team(team_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            raise HTTPException(status_code=428, detail="Your FPL session expired — reconnect your account")
        raise HTTPException(status_code=502, detail="FPL is not responding right now. Try again shortly.")
    except Exception:
        logger.exception("Failed to fetch squad for team %s", team_id)
        raise HTTPException(status_code=502, detail="FPL is not responding right now. Try again shortly.")

    _, _, scored_players = await _get_scored_players(client)

    squad_ids = [pick["element"] for pick in my_team.get("picks", [])]
    transfers_info = my_team.get("transfers", {})
    bank = transfers_info.get("bank", 0)
    free_transfers = transfers_info.get("limit") or 1

    recs = recommend_transfers(squad_ids, bank, scored_players, free_transfers)
    if not recs:
        raise HTTPException(status_code=404, detail="No viable transfer found")
    return recs


@app.get("/players/search")
async def search_players(q: str = "", element_type: Optional[int] = None, limit: int = 25,
                         user: dict = Depends(current_user)):
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


@app.post("/transfer/preview")
async def preview_transfer(req: TransferPreviewRequest, ctx: tuple = Depends(current_fpl)):
    """Validate a hand-built transfer and show its effect, without executing."""
    _, client, team_id = ctx
    my_team = await client.get_my_team(team_id)
    _, _, scored_players = await _get_scored_players(client)

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
async def execute_transfer(req: TransferExecuteRequest, ctx: tuple = Depends(current_fpl)):
    user, client, team_id = ctx

    gw_info = await client.get_gameweek_info()
    event = req.event or gw_info.get("next_event") or gw_info.get("current_event")
    if event is None:
        raise HTTPException(status_code=400, detail="Could not determine target gameweek")

    my_team = await client.get_my_team(team_id)

    if not req.accept_hit:
        free_transfers = (my_team.get("transfers") or {}).get("limit")
        if free_transfers is not None and free_transfers <= 0:
            raise HTTPException(
                status_code=409,
                detail="This transfer would cost a 4-point hit. Resubmit with accept_hit=true to confirm.",
            )

    # FPL pays out the pick's own selling_price, which lags now_cost once the
    # player's price has moved since you bought them.
    _, _, scored_players = await _get_scored_players(client)
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
        result = await client.execute_transfer(payload)
    except FPLTransferError as e:
        raise HTTPException(status_code=422, detail={"message": str(e), "fpl_response": e.payload})

    transfer_id = await db.insert_transfer(
        user_id=user["id"],
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
async def get_history(limit: int = 100, user: dict = Depends(current_user)):
    return await db.get_transfers(user["id"], limit=limit)


@app.get("/gameweek")
async def get_gameweek() -> GameweekInfo:
    gw = await FPLClient().get_gameweek_info()
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
