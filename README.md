<div align="center">

# ⚽ FPL Auto-Manager

**A Fantasy Premier League co-manager that scores your squad, explains which transfer to make, and executes it against your real FPL team once you approve.**

🔗 **Live Demo:** https://fpl-auto-manager.vercel.app

</div>

---

<details open>
<summary><b>📋 Table of Contents</b></summary>

1. [About The Project](#about-the-project)
   - [Features](#features)
   - [Built With](#built-with)
2. [Getting Started](#getting-started)
3. [Connecting an FPL Account](#connecting-an-fpl-account)
4. [How Scoring Works](#how-scoring-works)
5. [Deployment](#deployment)

</details>

---

## About The Project

<img width="2531" height="1168" alt="image" src="https://github.com/user-attachments/assets/5fdf1f43-73ae-40c1-a6ad-44b1a587256e" />



**FPL Auto-Manager** is a multi-user web app that connects to the official (undocumented) Fantasy Premier League API. It scores all ~700 players on form, fixture difficulty, ownership, price movement and rotation risk, then ranks a replacement for every player in your squad and explains its reasoning in plain English.

It is not a chatbot or a read-only recommender. Approving a transfer sends a real `POST` to FPL's transfer endpoint, and the change appears on the official site immediately.

### Features

- **Ranked transfer suggestions** — one best affordable replacement for every player in your squad, sorted by score gain, so you can browse alternatives instead of accepting a single take-it-or-leave-it pick
- **Plain-English reasoning** — every suggestion explains itself ("Recent form is better: 6.7 vs 0.3", "Next 3 fixtures look harder"), including the downsides of the pick it is recommending
- **Real transfer execution** — approving submits the transfer to FPL and logs it, with a confirmation step when it would cost a 4-point hit
- **Manual transfer builder** — search any player, and the app validates position, budget and ownership before you commit
- **Pitch view** — your line-up in formation with real club kits, captain and vice-captain armbands, and live gameweek points, alongside a fixture-difficulty list view
- **Multi-user accounts** — each user signs up, links their own FPL team, and only ever sees their own squad, suggestions and transfer history
- **Live deadline countdown** — pushed over a WebSocket, turning red inside the final hour

### Built With

| Layer | Tech |
|---|---|
| Backend | FastAPI + PostgreSQL |
| Cache & sessions | Redis |
| Frontend | React 18 + Vite + TanStack Query |
| Realtime | WebSocket |
| Deployment | Railway (backend) + Vercel (frontend) |

---

## Getting Started

**Backend** (API on `:8010`):

```bash
cd backend
uv venv .venv
uv pip install -r requirements.txt --python .venv/Scripts/python.exe   # Windows
# uv pip install -r requirements.txt --python .venv/bin/python          # macOS/Linux

cp .env.example .env
# set DATABASE_URL, REDIS_URL and a random APP_SECRET_KEY

.venv/Scripts/python -m uvicorn main:app --reload --port 8010
```

**Frontend** (UI on `:5173`, in a separate terminal):

```bash
cd frontend
npm install
cp .env.local.example .env.local     # VITE_API_URL=http://localhost:8010
npm run dev
```

Postgres and Redis are the only external services. The database schema is created automatically on startup.

**Environment variables**

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |
| `APP_SECRET_KEY` | **Required in production** — the app refuses to start without it. Encrypts stored FPL tokens; if it changes, every user must reconnect |
| `FRONTEND_ORIGIN` | The UI's origin. Sets CORS, and switches session cookies to `SameSite=None; Secure` when it is `https://` |
| `ENABLE_BROWSER_LOGIN` | Local only. Enables the server-side browser sign-in described below |

---

## Connecting an FPL Account

FPL has no public OAuth for third-party apps — its login client is locked to redirecting back to `fantasy.premierleague.com` — so there is no "Sign in with FPL" button any app can implement. The user's own browser has to hand over the session instead.

The app offers a **bookmarklet**: you drag it to your bookmarks bar once, then click it while on `fantasy.premierleague.com`. It runs inside that tab, reads the access token the FPL site stores in `localStorage`, and redirects back with it. No extension install and no DevTools.

A manual token paste is available as a fallback, and when `ENABLE_BROWSER_LOGIN` is set the backend can open a real Chrome window and lift the token itself — useful for local development only.

---

## How Scoring Works

Each player gets a single score from five weighted factors:

| Factor | Weight | Signal |
|---|---|---|
| Recent form | `2.0` | Rolling average points |
| Fixture difficulty | `1.5` | Average FDR over the next 3 gameweeks, inverted |
| Ownership | `0.05` | `selected_by_percent`, as a template/differential signal |
| Price movement | `1.0` | `cost_change_event` — buying before a rise |
| Rotation risk | `-1.0` | Minutes played and chance of playing next round |

Weights are hand-tuned rather than fitted to data. A transfer's value is simply the incoming player's score minus the outgoing player's, and the same itemised breakdown drives the written explanation.

---

## Deployment

The frontend deploys to **Vercel** from `frontend/`. The backend deploys to **Railway** from `backend/` with **Root Directory** set to `backend`, alongside Railway's Postgres and Redis plugins.


---

