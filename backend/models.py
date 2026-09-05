"""Pydantic models shared across the backend."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str


class AuthStatus(BaseModel):
    """Whether the signed-in user has linked an FPL account."""
    connected: bool
    team_id: Optional[int] = None


class BrowserLoginStartRequest(BaseModel):
    fresh: bool = False  # wipe the browser profile so a different account can sign in


class BrowserLoginState(BaseModel):
    status: str  # idle | waiting | success | error
    error: Optional[str] = None


class TokenLoginRequest(BaseModel):
    access_token: str
    team_id: Optional[int] = None  # derived from the session when omitted


class TransferPayload(BaseModel):
    entry: int  # the manager's team id -- required by the transfers endpoint
    element_in: int
    purchase_price: int  # what the incoming player costs now, * 10
    element_out: int
    selling_price: int  # what FPL will actually pay you, * 10 (not the same as now_cost)
    event: int
    chip: Optional[str] = None


class ScoredPlayer(BaseModel):
    id: int
    web_name: str
    team: int
    team_short_name: str = ""
    team_code: Optional[int] = None  # used for the kit image on the pitch view
    element_type: int
    now_cost: int
    event_points: int = 0
    form: float
    selected_by_percent: float
    cost_change_event: int
    minutes: int
    score: float
    fixtures: list[dict] = []
    breakdown: dict = {}


class TransferRecommendation(BaseModel):
    player_out: ScoredPlayer
    player_in: ScoredPlayer
    score_delta: float
    is_hit: bool
    free_transfers: int
    reasons: list[str] = []


class TransferPreviewRequest(BaseModel):
    element_out: int
    element_in: int


class TransferExecuteRequest(BaseModel):
    element_in: int
    element_out: int
    element_in_cost: int
    element_out_cost: int
    event: int
    player_in_name: str
    player_out_name: str
    accept_hit: bool = False


class GameweekInfo(BaseModel):
    current_event: Optional[int]
    next_event: Optional[int]
    next_deadline_time: Optional[datetime]
    free_transfers: Optional[int] = None
