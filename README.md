# Alphast

Production: https://alphast.xyz

Alphast is a real-time spread monitoring, portfolio, risk, and execution dashboard
for gold perp arbitrage research. The core production pair is **Bybit XAUTUSDT**
versus **Lighter XAU**, with an expanded monitor for Binance, MEXC, Aster, GRVT,
Hyperliquid, and OKX.

## Current Status

- Local `main`, `origin/main`, and the VPS deployment should track the same commit.
- Production runs on a Hetzner VPS behind Cloudflare and Nginx Proxy Manager.
- The public app and API are served from `https://alphast.xyz`.
- The backend container is expected to be healthy, and the frontend container serves
  the static React build through nginx.

Quick production checks:

```bash
curl -fsS https://alphast.xyz/api/v1/health
curl -fsS https://alphast.xyz/api/v1/prices
curl -fsS https://alphast.xyz/api/v1/monitor/spreads
```

## What It Does

- Streams Bybit and Lighter prices over WebSocket.
- Calculates mid, long, short, executable, and net spreads in bps.
- Tracks funding rates, spread history, percentiles, and current positions.
- Shows a multi-exchange monitor for gold perp opportunities.
- Provides execution controls for manual arbitrage flows.
- Tracks SL/TP, auto-hedge status, trade journal, and recent alerts.
- Adds a risk framework with dry-run controls, position limits, notional limits,
  price sanity checks, rate limits, audit logs, and a kill switch.
- Includes optional AI/backtest modules for spread research.
- Sends Telegram alerts for configured spread, monitor, and system events.

## Architecture

```text
Internet
  -> Cloudflare
  -> Nginx Proxy Manager on VPS
  -> frontend nginx container
  -> backend FastAPI container
  -> SQLite database
  -> exchange APIs
```

Main services:

- `frontend`: React, TypeScript, Vite, Tailwind CSS, Recharts.
- `backend`: FastAPI, asyncio collectors, SQLite, risk services, execution services.
- `docker-compose.prod.yml`: production compose file used by the VPS.
- `scripts/backup_db.sh`: database backup helper.

## Repository Layout

```text
backend/
  app/
    api/          REST routes
    collectors/   exchange adapters and market data collectors
    services/     execution, monitor, SL/TP, auto-hedge, reconciliation
    risk/         risk engine, limits, audit, kill switch
    storage/      SQLite connection and queries
    analytics/    spread and cost calculations
  tests/          backend tests

frontend/
  src/
    components/   dashboard pages and UI shell
    hooks/        WebSocket hook
    services/     typed API clients
    types/        frontend API types

docs/
  DESIGN.md
  archive/

ios-widget/
scripts/
```

## Local Development

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite runs on `http://localhost:5173` and proxies `/api` and `/ws` to the backend.

Build check:

```bash
cd frontend
npm run build
```

Lint check:

```bash
cd frontend
npm run lint
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests from the repository root:

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```

Run lint from the repository root:

```bash
python -m ruff check backend/app backend/tests
```

## Configuration

Copy the example env file and edit secrets locally or on the VPS:

```bash
cp backend/.env.example backend/.env
```

Important settings:

```env
APP_ENV=production
CORS_ORIGINS=https://alphast.xyz

BYBIT_BASE_URL=https://api.bytick.com
LIGHTER_BASE_URL=https://mainnet.zklighter.elliot.ai

SYMBOLS=XAUTUSDT
DB_PATH=./data/spread_dashboard.db

TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

MONITOR_GROUPS=gold:bybit:XAUTUSDT,lighter:XAU,binance:XAUTUSDT,mexc:XAUT_USDT,aster:XAUUSDT,aster:PAXGUSDT
MONITOR_ALERT_THRESHOLD_BPS=40.0
```

Bybit note: some Thai ISPs block `api.bybit.com`, so this project defaults to
`api.bytick.com`.

## Production Deployment

The VPS deployment is expected to live in `~/spread-dashboard` and track
`origin/main`.

Check the deployed commit:

```bash
ssh -i ~/.ssh/<ssh-key> <user>@<server-ip> \
  'cd ~/spread-dashboard && git status --short --branch && git rev-parse --short HEAD'
```

Deploy the latest `main` manually:

```bash
ssh -i ~/.ssh/<ssh-key> <user>@<server-ip>
cd ~/spread-dashboard
git fetch origin --prune
git reset --hard origin/main
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

View logs:

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 frontend
```

## API Reference

Core:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Exchange and service health |
| GET | `/api/v1/prices` | Current prices and spreads |
| GET | `/api/v1/spreads?symbol=XAUTUSDT&minutes=60` | Spread history |
| GET | `/api/v1/funding` | Funding rates |
| GET | `/api/v1/positions?symbol=XAUTUSDT` | Current positions |
| GET | `/api/v1/alerts?limit=20` | Recent alerts |
| WS | `/ws` | Real-time price and monitor stream |

Execution and operations:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/execute` | Execute an arbitrage trade |
| POST | `/api/v1/execute/close_all` | Emergency close |
| GET | `/api/v1/trades` | Trade journal |
| GET | `/api/v1/auto-hedge/status` | Auto-hedge state |
| GET | `/api/v1/sl-tp/status` | SL/TP state |

Monitor and risk:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/monitor/pairs` | Configured monitor pairs |
| GET | `/api/v1/monitor/spreads` | Current multi-exchange spreads |
| GET | `/api/v1/monitor/history` | Monitor pair history |
| GET | `/api/v1/risk/status` | Risk engine status |
| GET | `/api/v1/risk/config` | Risk configuration |

## iOS Widget

The Scriptable widget lives at `scripts/xau-spread-widget.js`.

It should call:

```text
https://alphast.xyz/api/v1/spreads?symbol=XAUTUSDT&minutes=60
```

## Useful Checks

Compare local, GitHub, and VPS:

```bash
git fetch origin --prune
git status --short --branch
git rev-parse --short HEAD
git rev-parse --short origin/main

ssh -i ~/.ssh/<ssh-key> <user>@<server-ip> \
  'cd ~/spread-dashboard && git status --short --branch && git rev-parse --short HEAD && git rev-parse --short origin/main'
```

Check production containers:

```bash
ssh -i ~/.ssh/<ssh-key> <user>@<server-ip> \
  'cd ~/spread-dashboard && docker compose -f docker-compose.prod.yml ps'
```

## Known Maintenance Notes

- Keep `README.md`, `DEPLOY.md`, and `backend/.env.example` aligned when the public
  domain changes.
- Frontend build should pass before deployment.
- Backend tests require all test dependencies from `backend/requirements.txt`.
- Monitor pairs may include exchanges that are configured but temporarily missing
  live data when an external API rejects a symbol or returns no book.
