# Spread Dashboard

Real-time price spread dashboard comparing **Bybit** (CEX) and **Lighter** (DEX).
Built for cross-exchange arbitrage research and monitoring.

![Python](https://img.shields.io/badge/Python-3.12+-blue)
![React](https://img.shields.io/badge/React-18-61dafb)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![License](https://img.shields.io/badge/License-Private-red)

## Features

- **Real-time prices** from Bybit V5 API and Lighter zkRollup API
- **Spread metrics** — mid spread, long spread, short spread (in bps)
- **Analytics** — Z-score, orderbook imbalance, bid-ask spread
- **Funding rate comparison** — Bybit (8h) vs Lighter (1h) with annualized rates
- **Live charts** — spread time-series with Recharts
- **WebSocket streaming** with REST polling fallback
- **Health monitoring** — exchange connectivity, latency tracking

## Quick Start

### Prerequisites

- Python 3.12+ (3.13 recommended)
- Node.js 18+
- npm 

### 1. Backend

```bash
cd backend
python3.13 -m venv .venv

# Activate venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs at **http://localhost:8000/docs**

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at **http://localhost:5173**

## Architecture

```
frontend (React/Vite :5173)
    │
    ├── REST /api/v1/*  ──►  backend (FastAPI :8000)
    └── WS   /ws        ──►       │
                                   ├── Bybit Collector (api.bytick.com)
                                   ├── Lighter Collector (zklighter API)
                                   ├── Spread Engine (analytics)
                                   └── SQLite (persistence)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Exchange connectivity check |
| GET | `/api/v1/prices` | Current prices + spreads |
| GET | `/api/v1/spreads?symbol=BTCUSDT` | Spread history |
| GET | `/api/v1/funding` | Funding rates comparison |
| GET | `/api/v1/alerts` | Recent alerts |
| WS | `/ws` | Real-time price stream |

## Configuration

Edit `backend/.env`:

```env
# Symbols to track
SYMBOLS=BTCUSDT,ETHUSDT

# Polling interval
POLL_INTERVAL_MS=2000

# Alert thresholds
SPREAD_ALERT_BPS=5.0
STALE_FEED_TIMEOUT_S=10
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── collectors/          # Exchange API collectors
│   │   │   ├── bybit_collector.py
│   │   │   └── lighter_collector.py
│   │   ├── analytics/           # Spread computation engine
│   │   ├── api/                 # REST routes
│   │   ├── models/              # Data models (Pydantic)
│   │   ├── storage/             # SQLite database
│   │   └── config/              # Settings (.env)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── overview/        # Price cards, spread chart
│   │   │   └── health/          # Exchange health status
│   │   ├── hooks/               # WebSocket hook
│   │   └── services/            # API client
│   ├── package.json
│   └── vite.config.ts
└── docs/
    └── DESIGN.md                # Full system design document
```

## Spread Formulas

| Metric | Formula | Interpretation |
|--------|---------|---------------|
| Mid Spread | `(lighter_mid - bybit_mid) / bybit_mid` | + = Lighter expensive |
| Long Spread | `(lighter_ask - bybit_ask) / bybit_ask` | Cost to buy Lighter, sell Bybit |
| Short Spread | `(lighter_bid - bybit_bid) / bybit_bid` | Cost to sell Lighter, buy Bybit |
| Z-Score | `(spread - rolling_mean) / rolling_std` | \|z\| > 2 = unusual deviation |

## Roadmap

See [docs/DESIGN.md](docs/DESIGN.md) for the full design document including:

- Production-grade plan (PostgreSQL, Redis, Prometheus)
- Execution tool design (signal, risk, router, reconciliation modules)
- Backtesting harness
- Risk framework (kill switch, circuit breaker, position limits)

## Note

> **Thai ISP DNS block**: `api.bybit.com` is blocked by some Thai ISPs.
> This project uses `api.bytick.com` (official Bybit alternative) by default.
