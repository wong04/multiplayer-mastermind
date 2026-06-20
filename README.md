# Multiplayer Mastermind

Real-time multiplayer [Mastermind](https://en.wikipedia.org/wiki/Mastermind_(board_game))
for 2–4 players in the browser. Create a room, share the 4-letter code, and play
across scored best-of rounds.

## Game modes

- **Classic** — one player is the **codemaker** and sets the secret code; the others
  race in real time on their own private boards to crack it. First to crack wins the
  round; if nobody cracks it within the guess limit, the codemaker scores. The
  codemaker role rotates each round.
- **Competition** — the server picks one shared secret. Play advances in
  **synchronized barrier rounds**: everyone privately submits a guess for round _N_,
  and round _N+1_ only begins once the last player has submitted. Guesses stay hidden
  from other players. First to crack the code (earliest submission in the resolving
  round) wins.

Standard rules by default: 4-slot code, 6 colors, duplicates allowed, 10 guesses.
Feedback uses the classic pegs — **black** = right color & position, **white** =
right color, wrong position. All of this (code length, colors, guesses, target
score) is host-configurable in the lobby.

## Architecture

```
backend/   FastAPI + WebSocket game server (stateful, in-memory rooms)  -> Railway
frontend/  Vanilla HTML/CSS/JS, no build step                           -> Vercel
```

The frontend and backend deploy separately: Vercel can't host a long-lived
WebSocket server, so the stateful game server runs on Railway and the static
client on Vercel. They talk over a single `/ws` WebSocket connection.

## Run locally

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

**1. Backend** (terminal 1):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (terminal 2):

```bash
cd frontend
python -m http.server 5500
```

Open <http://localhost:5500> in 2–4 browser tabs/windows. `config.js` auto-targets
`ws://localhost:8000/ws` when served from localhost.

## Tests

```bash
cd backend
uv run pytest
```

Covers peg scoring (incl. duplicate-heavy cases), room lifecycle, both round flows,
the competition barrier, disconnect-doesn't-deadlock, and an end-to-end WebSocket
pass over the real app.

## Deploy

### Backend → Railway
1. Create a new Railway project from this repo, root directory `backend/`.
2. Nixpacks auto-detects the `uv` project; the start command and `/healthz`
   healthcheck come from `railway.json`.
3. Copy the public URL, e.g. `your-app.up.railway.app`.

### Frontend → Vercel
1. Import the repo into Vercel, root directory `frontend/`, framework preset
   **Other** (no build step).
2. Edit `frontend/js/config.js` and set `PROD_WS_URL` to your Railway URL with the
   `wss://` scheme and `/ws` path, e.g. `wss://your-app.up.railway.app/ws`.
3. Deploy. Share the Vercel URL — anyone with the link can join a room by code.

## Limitations
- Room state is in-memory on a single instance: don't scale the backend past one
  replica, and a restart drops active games.
- Reconnect (refresh-safe via a stored session token) works as long as at least one
  player stays connected; if everyone drops, the room is cleaned up.
