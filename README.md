# Spread Dashboard

Real-time cross-exchange spread monitoring and execution tool for **Bybit** (CEX) vs **Lighter** (DEX) arbitrage.

## Features

- **Real-time spread monitoring** — mid, long, short spreads in bps via WebSocket
- **Arbitrage execution** — one-click BUY L/SELL B and SELL L/BUY B with Smart Maker
- **Emergency close** — instantly flatten all positions across both exchanges
- **Funding rate tracking** — Bybit (8h) vs Lighter (1h) with arb favorability
- **Spread charts** — time-series with P10/P90 percentile bands
- **Telegram alerts** — configurable threshold notifications
- **Mobile responsive** — optimized for phone and desktop

## Architecture

```
Internet → Cloudflare → Nginx Proxy Manager (443)
                              │
                    ┌─────────┴─────────┐
                    │  frontend (nginx)  │
                    │  React / Vite      │
                    └────────┬──────────┘
                             │ /api/* & /ws
                    ┌────────┴──────────┐
                    │  backend (uvicorn) │
                    │  FastAPI           │
                    ├───────────────────┤
                    │ Bybit Collector    │ ← api.bytick.com
                    │ Lighter Collector  │ ← zklighter.elliot.ai
                    │ Spread Engine      │
                    │ Arb Executor       │
                    │ SQLite             │
                    └───────────────────┘
```

## Deployment (Docker)

```bash
# Copy and configure environment
cp backend/.env.example backend/.env
nano backend/.env

# Build and run
docker compose -f docker-compose.prod.yml up -d --build

# View logs
docker compose -f docker-compose.prod.yml logs -f backend

# Restart (reload .env requires recreate)
docker compose -f docker-compose.prod.yml up -d
```

## Configuration

Edit `backend/.env`:

```env
# Symbols to track
SYMBOLS=XAUTUSDT,HYPEUSDT

# Bybit API (required for execution)
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret

# Lighter API (required for execution)
LIGHTER_PRIVATE_KEY=0x...
LIGHTER_API_KEY_INDEX=2
LIGHTER_ACCOUNT_INDEX=123456

# Telegram alerts
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
ALERT_UPPER_BPS=9
ALERT_LOWER_BPS=-1
ALERT_OVERRIDES=XAUTUSDT:75:58
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Exchange connectivity |
| GET | `/api/v1/prices` | Current prices + spreads |
| GET | `/api/v1/spreads?symbol=XAUTUSDT&minutes=60` | Spread history |
| GET | `/api/v1/funding` | Funding rates |
| GET | `/api/v1/positions?symbol=XAUTUSDT` | Current positions |
| POST | `/api/v1/execute` | Execute arbitrage trade |
| POST | `/api/v1/execute/close_all` | Emergency close all |
| GET | `/api/v1/alerts` | Recent alerts |
| WS | `/ws` | Real-time price stream |

## Tech Stack

- **Backend**: Python 3.13, FastAPI, uvicorn, SQLite
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Recharts
- **Infra**: Docker Compose, Nginx Proxy Manager, Cloudflare

## Note

> `api.bybit.com` is blocked by some Thai ISPs. This project uses `api.bytick.com` (official alternative) by default.
