# FPL Auto-Manager

Connects to the official (undocumented) Fantasy Premier League API, scores your
squad ahead of each gameweek deadline, recommends the best transfer, and — after
you approve it — executes it directly against your real FPL account.

## Stack

- **Backend**: FastAPI, PostgreSQL (asyncpg), Redis, APScheduler, httpx
- **Frontend**: React 18 + Vite, TanStack Query, Recharts, WebSocket
- **Deploy**: Railway (backend + Postgres + Redis), Vercel (frontend)

## Local setup

### Backend

```bash
cd backend
uv venv .venv
uv pip install -r requirements.txt --python .venv/Scripts/python.exe   # Windows
# uv pip install -r requirements.txt --python .venv/bin/python          # macOS/Linux

cp .env.example .env
# edit .env: DATABASE_URL, REDIS_URL

.venv\Scripts\uvicorn main:app --reload   # Windows
# .venv/bin/uvicorn main:app --reload      # macOS/Linux
```

There are no FPL credentials in `.env` — you connect your account from the UI
(see below). Only Postgres/Redis connection strings live in `.env`.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:5173.

## Build order (verify each step before moving on)

1. **FPL Auth** — start the backend and frontend, click "Connect FPL Account"
   in the top bar, and submit your email/password/team ID. This calls
   `POST /auth/login`, which runs `FPLClient.login()` server-side and stores
   the resulting session (not your password) in Redis.
2. **Read endpoints** — once connected, `GET /squad` should return your real squad.
3. **PostgreSQL** — tables are created automatically on startup (`db.init_db()`
   runs the schema in `db.py`). Confirm with `SELECT * FROM transfers;`.
4. **Optimizer** — `GET /players` and `GET /recommendation`; or unit-test
   `score_player` / `recommend_transfer` with hardcoded data (see git history /
   scratch scripts for an example).
5. **Transfer execution** — `POST /transfer/execute` with a low-stakes transfer
   during a real gameweek. Confirm it shows up on the FPL website.
6. **WebSocket** — connect to `ws://localhost:8000/ws/deadline` (e.g. via
   `wscat -c ws://localhost:8000/ws/deadline`) and confirm `{"minutes_left": ...}`
   frames arrive every minute.
7. **Frontend** — `SquadView` → `TransferCard` → `FixtureGrid` → `TransferHistory`
   → `DeadlineCountdown`, wired up in `App.jsx`.
8. **Deploy** — see below.

## Deployment

### Railway (backend + Postgres + Redis)

```bash
railway login
railway init
railway add --database postgres
railway add --database redis
railway up   # from backend/, deploys using railway.toml
```

Railway injects `DATABASE_URL` and `REDIS_URL` automatically once the Postgres
and Redis plugins are attached to the service — no need to set them manually.
Set `FRONTEND_ORIGIN` to your deployed Vercel URL once you have it.

### Vercel (frontend)

```bash
cd frontend
vercel
vercel env add VITE_API_URL   # your Railway backend URL
vercel --prod
```

## Notes and gotchas

- The FPL API is undocumented and reverse-engineered from browser traffic on
  fantasy.premierleague.com. If auth or the transfer endpoint start failing,
  check devtools on the live site first — these contracts can change.
- Prices are stored as integers × 10 (an £8.5m player is `85`).
- Transfers beyond your free transfer limit cost a 4-point hit; `/transfer/execute`
  refuses those unless the request includes `accept_hit: true` (the frontend
  surfaces this as a confirmation checkbox).
- FPL credentials are entered via the "Connect FPL Account" modal and sent
  once to the backend to log in; the password itself is never persisted —
  only the resulting session cookies are cached in Redis, so the backend
  doesn't need to re-login on every request or restart. If the session
  expires, reconnect from the UI.
- `bootstrap-static` is cached in Redis for 30 minutes and refreshed by an
  APScheduler job — never fetched on every request, per FPL's aggressive rate
  limiting.

## Resume bullets

- Built a full-stack FPL automation tool (FastAPI + React) that executes real
  Fantasy Premier League transfers via the undocumented FPL API, with a scoring
  algorithm that factors in fixture difficulty, form, and price trends across
  500+ players.
- Implemented a WebSocket-driven deadline countdown and a Redis-backed player
  cache refreshed every 30 minutes via APScheduler, reducing FPL API load and
  keeping fixture data current.
- Designed a PostgreSQL transfer log with gameweek snapshots, enabling post-hoc
  analysis of transfer ROI by backfilling points gained after each gameweek
  completes.
