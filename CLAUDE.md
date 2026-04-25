# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

Monorepo with three deployables:
- `backend/` — Python 3.13 FastAPI service (market data, spread engine, execution, alerts, SQLite)
- `frontend/` — React 18 + TypeScript + Vite + Tailwind SPA
- `ios-widget/` + `scripts/xau-spread-widget.js` — Swift app and Scriptable widget that poll the public API

Docs: `README.md` (user-facing), `DEPLOY.md` (VPS + NPM + Cloudflare ops), `docs/DESIGN.md` (detailed design), `plan.md` (stability optimization backlog, Thai).

## Commands

### Backend (run from `backend/`)
```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit

# Dev server (reload on change)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Tests
pytest                          # all tests
pytest tests/test_alert_engine.py::test_name  # one test
```

### Frontend (run from `frontend/`)
```bash
npm install
npm run dev     # Vite on :5173, proxies /api and /ws to VITE_BACKEND_URL (default http://localhost:8000)
npm run build   # tsc typecheck + vite build → dist/
```
There is no separate lint or format script; `npm run build` runs `tsc` as the type check.

### Docker
```bash
docker compose up -d --build                             # dev compose (binds 127.0.0.1:3000 + :8000)
docker compose -f docker-compose.prod.yml up -d --build  # prod (no host ports; uses external proxy-net)
```
Prod requires `docker network create proxy-net` first and assumes NPM runs in `~/proxy` on the host.

### Deploy
GitHub Actions (`.github/workflows/deploy.yml`) auto-deploys on push to `main` by SSHing into the VPS and running `git reset --hard origin/main && docker compose -f docker-compose.prod.yml up -d --build`. Do not push to `main` without intending to ship.

## Backend Architecture

Entry point: `backend/app/main.py`. At startup the `lifespan` handler:
1. Calls `init_db()` — opens one persistent `aiosqlite` connection with `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`. **Every DB function in `app/storage/database.py` reuses this single connection** (`_get_db()`); never call `aiosqlite.connect()` directly.
2. Loads Lighter market-ID map and starts its market-stats WebSocket.
3. Launches `_supervised_poll_loop()` — if `poll_loop()` crashes, it waits 2s and restarts.
4. Starts the Telegram bot task.

Each poll cycle (`POLL_INTERVAL_MS`, default 2000 ms):
- Fetches Bybit + Lighter tickers for every symbol concurrently with a 10s `asyncio.wait_for` timeout.
- Per-symbol exception isolation — one symbol's failure must not abort others.
- Writes ticks + computed spread via `insert_tick` / `insert_spread`, then **one batch `db_commit()` per cycle**.
- Broadcasts to WS clients. Each client stores a subscription set (`None` means "all symbols"); messages are filtered per-client before send.

### Shared state and concurrency
- `app/analytics/spread_engine.py`: `latest_ticks` dict is guarded by `asyncio.Lock`; writers take the lock, readers take `dict(latest_ticks)` snapshots. Preserve this pattern when adding new shared state.
- `app/services/auto_hedge.py` and `app/services/sl_tp.py` run as singleton background services with their own `asyncio.Lock`; `lifespan` stops them on shutdown.
- HTTP clients are persistent: `bybit_collector.close_session()`, `lighter_collector.close_session()`, `close_telegram_session()`, `close_db()` must all be awaited on shutdown.

### Settings and reload
`app/config/settings.py` uses `pydantic-settings` to load `.env`. All modules import the same `settings` singleton. `reload_settings()` **mutates the existing object in place** so downstream imports stay valid — do not replace the object or cache field values at import time. Env-driven knobs you will see referenced throughout the code: `SYMBOLS`, `POLL_INTERVAL_MS`, `ALERT_UPPER_BPS`/`ALERT_LOWER_BPS`, `ALERT_OVERRIDES` (per-symbol `SYM:UPPER:LOWER,…`), `LIGHTER_SYMBOL_MAP` (dashboard→Lighter symbol alias, e.g. `XAUTUSDT:XAUUSDT`), and the `MAKER_*` / `ICEBERG_*` / `ARB_*` execution tunables.

### Execution stack
REST routes live in `app/api/routes.py` (+ `auto_hedge_routes.py`, `sl_tp_routes.py`); portfolio routes in `app/portfolio/router.py`. Order execution flows through:
- `app/services/executor.py` `ArbitrageExecutor` — used as an `async with` context manager; default mode is **sequential**: Bybit PostOnly LIMIT via `maker_engine.smart_execute_maker()` first, then Lighter MARKET for the exact filled qty. If Lighter fails after Bybit fills, Bybit is reversed. `arb_maker_only=True` disables market fallback.
- `app/execution/maker_engine.py`, `iceberg_executor.py`, `linear_limit_slicer.py`, `maker_slicer_linear.py` — use `Decimal` (never `float`) for all price/qty math.
- `app/collectors/bybit_client.py` wraps `pybit`'s sync HTTP with `asyncio.to_thread` + `asyncio.wait_for` (see `utils/async_helpers.thread_with_timeout`) to avoid thread-pool hangs.

### Exchange notes
- `api.bybit.com` is blocked on some Thai ISPs; defaults point at `api.bytick.com` / `stream.bytick.com` and the `pybit` session is constructed with `domain="bytick"`. Do not hardcode `bybit.com`.
- Bybit funding is 8h, Lighter funding is 1h; spread/funding math in `analytics/spread_engine.py` and `analytics/cost_model.py` relies on this.

### Alerts
`app/alerts/alert_engine.py` is a per-symbol state machine (`NORMAL` ↔ `ALERTING`) with hysteresis between `alert_lower_bps` and `alert_upper_bps`, a post-recovery flapping guard, and a cooldown that only suppresses the *notification* — state always reflects truth. Telegram sends go through `telegram_notifier.py`; runtime mute/threshold overrides live in `telegram_bot.py`.

## Frontend Architecture

`frontend/src/App.tsx` is the shell: a simple page switcher (`overview` / `portfolio` / `history` / `health`). Realtime data flows via `useWebSocket` (`src/hooks/useWebSocket.ts`):
- Heartbeat: `ping` text frame every 15s; if no `pong` in 5s, close and reconnect.
- Exponential backoff with jitter: 1s → 30s cap, 30-retry ceiling.
- Connection states: `connecting | connected | reconnecting | disconnected`.
- WS URL is protocol-aware: `wss://` on HTTPS, `ws://` on HTTP — preserve this when editing.

WS messages are buffered in a ref and flushed to React state at ~4 fps (`WS_FLUSH_INTERVAL_MS = 250`) to avoid render storms. When WS is disconnected, TanStack Query polls `/api/v1/prices` every 2s as a fallback.

REST calls go through `frontend/src/services/api.ts`, which adds `AbortController` timeouts (15s default, 60s for execute). All requests hit same-origin `/api/v1/*` — in prod nginx proxies to `backend:8000`; in dev Vite proxies to `VITE_BACKEND_URL`.

## Testing Conventions

- `backend/tests/conftest.py` auto-runs `alert_engine.reset_states()` around every test — don't remove it if adding alert tests.
- Tests use `pytest-asyncio`, `unittest.mock.AsyncMock`, and mock outbound I/O (`send_telegram`, exchange clients). No live exchange calls in tests.
- No tests exist for the frontend or iOS widget.

## Deployment Topology (prod)

```
Cloudflare → NPM (443) → frontend nginx (serves /assets, proxies /api + /ws) → backend:8000
```
- Frontend and backend do not expose public ports. `frontend` joins both `app-internal` (to reach `backend`) and the external `proxy-net` (so NPM can reach it).
- SQLite DB is persisted via `./backend/data:/app/data` bind mount — preserve this when changing compose files.
- See `DEPLOY.md` for NPM proxy-host settings (WebSocket upgrade headers are required in the Advanced tab).
