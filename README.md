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
6. [Key Design Decisions](#key-design-decisions)

</details>

---

## About The Project

<!-- Add a screenshot here:  ![FPL Auto-Manager](docs/screenshot.png)  -->

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
| Backend | FastAPI + PostgreSQL (asyncpg) |
| Cache & sessions | Redis |
| Background jobs | APScheduler |
| HTTP client | httpx |
| Security | Argon2id password hashing, Fernet token encryption |
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
| `APP_SECRET_KEY` | **Required in production.** Encrypts stored FPL tokens — if it changes, every user must reconnect |
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

Set `FRONTEND_ORIGIN` on the backend to the deployed frontend URL. Without it the session cookie stays `SameSite=Lax` and is dropped on cross-origin requests, so users appear signed out immediately after logging in.

---

## Key Design Decisions

<details>
<summary><b>Why a bookmarklet instead of "Sign in with FPL"</b></summary>

FPL's login is its own OIDC client, and its redirect URI only ever returns to `fantasy.premierleague.com`, so a third-party app cannot participate in that flow. Opening FPL in a tab is easy; reading the result is the blocked part, because the same-origin policy prevents this app's JavaScript from touching `fantasy.premierleague.com`'s `localStorage`.

A bookmarklet is the one legitimate path: it runs *inside* the FPL tab, invoked explicitly by the user, so it is allowed to read that page's own storage. It hands the token back by navigating rather than by `fetch`, so FPL's Content-Security-Policy cannot block it.
</details>

<details>
<summary><b>Why FPL tokens are encrypted at rest</b></summary>

An FPL access token grants full control of someone's team, including transfers. Storing other people's tokens is a real responsibility, so they are encrypted with Fernet before they touch the database — a leaked dump alone is not enough to take over an account. The key comes from `APP_SECRET_KEY` and never leaves the environment.
</details>

<details>
<summary><b>Why the server-side browser sign-in is local-only</b></summary>

Locally the backend can launch Chrome, let you sign in, and read the token back over Chrome's DevTools port, because the browser and the backend are on the same machine. Deployed, that breaks for a physical reason: the server has no display, and the user is on a different computer entirely. Rather than delete a genuinely nice local flow, it sits behind `ENABLE_BROWSER_LOGIN`, and the frontend asks `/config` which methods this deployment actually supports.
</details>

<details>
<summary><b>Why selling price comes from the squad, not the market price</b></summary>

FPL pays out a pick's own `selling_price`, which lags `now_cost` because you only receive half of any price rise since you bought the player. Sending the current market price gets the transfer rejected, so the selling price is always read from the user's actual squad data.
</details>

<details>
<summary><b>Why an empty 200 response counts as success</b></summary>

A successful transfer returns `200` with an empty body. Parsing that as JSON raises, which originally made completed transfers look like failures — the transfer went through on FPL, the app reported an error, and nothing was logged. Empty bodies are now treated as success.
</details>

<details>
<summary><b>Why unhandled errors are returned with CORS headers</b></summary>

A bare `500` from an unhandled exception carries no CORS headers, so the browser reports it as an opaque "Failed to fetch" and hides the real cause. A catch-all handler returns the actual error with the right headers, which turns silent debugging dead-ends into readable messages.
</details>

<details>
<summary><b>Why bootstrap-static is cached for 30 minutes</b></summary>

FPL rate-limits aggressively, and `bootstrap-static` is a large payload containing every player. It is identical for every user, so it is cached once in Redis and refreshed by a background job rather than fetched per request or per account.
</details>

<details>
<summary><b>Why there is a recommendation for every player</b></summary>

A single "best transfer" is a take-it-or-leave-it suggestion, and dismissing it left the user with nothing. Instead the optimiser returns one best replacement per squad player, ranked by score gain, so the panel becomes a browsable list of options — and the reasoning stays honest, surfacing the downsides of each pick rather than only its upsides.
</details>
