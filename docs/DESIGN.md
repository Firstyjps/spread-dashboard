# Spread Dashboard - System Design Document

## Executive Summary

Spread Dashboard คือระบบ real-time price monitoring และ analytics platform
สำหรับเปรียบเทียบราคาระหว่าง **Bybit** (CEX) และ **Lighter** (DEX/zkRollup)
เป้าหมายระยะสั้นคือ MVP dashboard แสดงราคา/spread แบบ real-time
เป้าหมายระยะยาวคือ statistics engine + execution tool สำหรับ arbitrage R&D

### Verified API Endpoints

**Bybit V5 API** (base: `https://api.bybit.com`)
- REST: `GET /v5/market/tickers` (category=linear/spot)
- REST: `GET /v5/market/orderbook` (category, symbol, limit)
- WS Public Linear: `wss://stream.bybit.com/v5/public/linear`
- WS Public Spot: `wss://stream.bybit.com/v5/public/spot`
- WS Topics: `orderbook.{depth}.{symbol}`, `tickers.{symbol}`, `publicTrade.{symbol}`
- Ping interval: 20 seconds

**Lighter API** (base: `https://mainnet.zklighter.elliot.ai`)
- REST: `GET /api/v1/orderBookOrders` (market_id, limit)
- REST: `GET /api/v1/orderBookDetails` (market stats)
- REST: `GET /api/v1/fundings` (funding history)
- REST: `GET /api/v1/funding-rates` (cross-exchange funding comparison)
- REST: `GET /api/v1/exchangeStats` (volume, price change)
- REST: `GET /` (status/health)
- WS: `wss://mainnet.zklighter.elliot.ai/stream`
- WS Channels: `order_book/{market_id}`, `ticker/{market_id}`, `market_stats/{market_id}`, `trade/{market_id}`

---

## Section A: System Architecture

### Stack Recommendation: Python + FastAPI + React

| Criteria | Python+FastAPI | Node+NestJS |
|----------|---------------|-------------|
| Crypto library support | pybit, ccxt, lighter-python SDK | bybit-api (npm), ต้อง wrap Lighter เอง |
| Quant/analytics | numpy, pandas, scipy native | ต้อง port หรือใช้ child process |
| WebSocket handling | websockets, asyncio native | ws, socket.io (ดี) |
| Async performance | ดี (uvicorn + asyncio) | ดีมาก (event loop native) |
| Future ML/backtest | scikit-learn, statsmodels ready | ต้อง bridge ไป Python |
| Community for trading | มากกว่า | น้อยกว่า |

**Recommendation: Python + FastAPI** เพราะ:
1. Lighter มี official Python SDK (lighter-python)
2. Quant analytics ต้องใช้ numpy/pandas เป็นหลัก
3. Backtest framework ส่วนใหญ่เป็น Python
4. Community support สำหรับ crypto trading ดีกว่า

### Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  React + Vite + TanStack Query + Recharts + shadcn/ui        │
│  Port 5173                                                   │
└──────────────┬────────────────────────┬──────────────────────┘
               │ REST (polling)         │ WebSocket
               ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                          │
│                     Port 8000                                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  REST API    │  │  WS Gateway  │  │  Background Tasks│    │
│  │  /api/v1/*   │  │  /ws         │  │  (asyncio)       │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
│         │                │                    │              │
│         ▼                ▼                    ▼              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              Analytics Engine                        │     │
│  │  spread calc, funding analysis, z-score, imbalance  │     │
│  └─────────────────────────────────────────────────────┘     │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              Data Normalizer                         │     │
│  │  exchange-agnostic tick format                       │     │
│  └─────────────────────────────────────────────────────┘     │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────┐  ┌──────────┐                                 │
│  │  Redis    │  │ Postgres │   (MVP: SQLite only)           │
│  │  (cache)  │  │ (persist)│                                 │
│  └──────────┘  └──────────┘                                 │
│         ▲                                                    │
│         │                                                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              Data Collectors                         │     │
│  │  ┌───────────┐        ┌────────────┐                │     │
│  │  │  Bybit    │        │  Lighter   │                │     │
│  │  │ Collector │        │ Collector  │                │     │
│  │  └───────────┘        └────────────┘                │     │
│  └─────────────────────────────────────────────────────┘     │
│         │                        │                           │
│  ┌──────────────┐  ┌──────────────────┐                     │
│  │ Alert Engine  │  │ (Future)         │                     │
│  │              │  │ Execution Service │                     │
│  └──────────────┘  └──────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
```

### MVP Stack (สัปดาห์ 1-2)
- Backend: Python 3.11+, FastAPI, aiohttp, websockets, SQLite (via aiosqlite)
- Frontend: React 18, Vite, TanStack Query, Recharts, Tailwind CSS
- No Redis, no Postgres in MVP (ใช้ in-memory + SQLite)

### Production Stack (สัปดาห์ 4-8)
- เพิ่ม Redis (pub/sub + cache)
- เพิ่ม PostgreSQL + TimescaleDB (time-series)
- เพิ่ม Prometheus + Grafana (monitoring)
- Container: Docker Compose

---

## Section B: Data Model & Metrics Specs

### B.1 Normalized Tick Data Schema

```sql
-- file: migrations/001_create_tables.sql

CREATE TABLE IF NOT EXISTS ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                    -- unix timestamp (ms)
    exchange TEXT NOT NULL,              -- 'bybit' | 'lighter'
    symbol TEXT NOT NULL,                -- 'BTCUSDT', 'ETHUSDT'
    market_type TEXT NOT NULL,           -- 'perp' | 'spot'
    bid REAL NOT NULL,                   -- best bid price
    ask REAL NOT NULL,                   -- best ask price
    bid_size REAL,                       -- best bid size
    ask_size REAL,                       -- best ask size
    mid REAL NOT NULL,                   -- (bid + ask) / 2
    last_price REAL,                     -- last trade price
    mark_price REAL,                     -- mark price (perp)
    index_price REAL,                    -- index price (perp)
    volume_24h REAL,                     -- 24h volume
    open_interest REAL,                  -- open interest (perp)
    received_at REAL NOT NULL            -- local receive timestamp (ms)
);

CREATE INDEX idx_ticks_lookup ON ticks(exchange, symbol, ts);

CREATE TABLE IF NOT EXISTS funding_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                    -- snapshot timestamp
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    funding_rate REAL NOT NULL,          -- current/last funding rate
    predicted_rate REAL,                 -- predicted next funding (if available)
    next_funding_time REAL,             -- next funding timestamp
    funding_interval_hours REAL,        -- hours between fundings (8h Bybit, variable Lighter)
    annualized_rate REAL                -- funding_rate * (365 * 24 / interval_hours)
);

CREATE INDEX idx_funding_lookup ON funding_snapshots(exchange, symbol, ts);

CREATE TABLE IF NOT EXISTS spread_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    symbol TEXT NOT NULL,
    bybit_mid REAL NOT NULL,
    lighter_mid REAL NOT NULL,
    bybit_bid REAL NOT NULL,
    bybit_ask REAL NOT NULL,
    lighter_bid REAL NOT NULL,
    lighter_ask REAL NOT NULL,
    exchange_spread_mid REAL NOT NULL,   -- (lighter_mid - bybit_mid) / bybit_mid
    long_spread REAL NOT NULL,           -- (lighter_ask - bybit_ask) / bybit_ask
    short_spread REAL NOT NULL,          -- (lighter_bid - bybit_bid) / bybit_bid
    bid_ask_spread_bybit REAL NOT NULL,  -- (bybit_ask - bybit_bid) / bybit_mid
    bid_ask_spread_lighter REAL NOT NULL,-- (lighter_ask - lighter_bid) / lighter_mid
    funding_diff REAL,                   -- lighter_funding - bybit_funding
    received_at REAL NOT NULL
);

CREATE INDEX idx_spread_lookup ON spread_metrics(symbol, ts);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    alert_type TEXT NOT NULL,            -- 'spread_threshold' | 'stale_feed' | 'high_latency'
    symbol TEXT,
    severity TEXT NOT NULL,              -- 'info' | 'warning' | 'critical'
    message TEXT NOT NULL,
    value REAL,                          -- trigger value
    threshold REAL,                      -- configured threshold
    acknowledged INTEGER DEFAULT 0
);
```

### B.2 Metric Formulas & Conventions

```
1. Mid Price
   mid = (bid + ask) / 2

2. Exchange Spread (Mid-based)
   exchange_spread_mid = (lighter_mid - bybit_mid) / bybit_mid
   - บวก (+): Lighter แพงกว่า Bybit
   - ลบ (-): Lighter ถูกกว่า Bybit
   - ใช้ Bybit เป็น reference เพราะเป็น CEX ที่มี liquidity สูงกว่า

3. Long Spread (ต้นทุนเปิด long arb: ซื้อ Bybit ask, ขาย Lighter ask)
   long_spread = (lighter_ask - bybit_ask) / bybit_ask
   - ถ้า > 0 : มี opportunity ซื้อ Bybit ขาย Lighter
   - ต้องหักค่า fee ทั้งสองฝั่งก่อนสรุปว่า profitable

4. Short Spread (ต้นทุนเปิด short arb: ขาย Bybit bid, ซื้อ Lighter bid)
   short_spread = (lighter_bid - bybit_bid) / bybit_bid
   - ถ้า < 0 : มี opportunity ขาย Lighter ซื้อ Bybit

5. Bid-Ask Spread (per exchange, as % of mid)
   ba_spread = (ask - bid) / mid

6. Orderbook Imbalance
   imbalance = (bid_size - ask_size) / (bid_size + ask_size)
   - Range: [-1, +1]
   - +1 = bid heavy (bullish pressure)
   - -1 = ask heavy (bearish pressure)

7. Basis (perp vs index)
   basis = (mark_price - index_price) / index_price

8. Feed Latency
   latency_ms = received_at - exchange_ts
   - วัดจาก timestamp ที่ exchange ส่ง vs timestamp ที่เรารับ

9. Rolling Z-Score (of exchange spread)
   z = (current_spread - rolling_mean) / rolling_std
   - Window: configurable (default 100 ticks or 5 min)
   - |z| > 2 = unusual spread deviation

10. Funding Rate Annualized
    annualized = funding_rate * (365 * 24 / interval_hours)
    - Bybit: interval = 8h, annualized = rate * 1095
    - Lighter: ต้องตรวจสอบ interval จาก docs (อาจเป็น 1h)

11. Funding Differential
    funding_diff = lighter_rate - bybit_rate
    - บวก: Lighter longs จ่ายมากกว่า
    - ลบ: Bybit longs จ่ายมากกว่า

12. Expected Funding PnL Proxy (per $1 notional, per period)
    pnl_proxy = funding_diff * notional
    - ASSUMPTION: linear funding, no price movement during period
    - Label: "indicative only, does not account for execution cost"

13. Volatility Proxy (Parkinson estimator from hi/lo)
    vol = sqrt(1/(4*ln(2)) * (ln(high/low))^2) * sqrt(365)
    - ใช้ 24h high/low จาก ticker

14. Slippage Estimate
    slippage_ask = ask - mid  (buying cost above mid)
    slippage_bid = mid - bid  (selling cost below mid)
    - เป็น estimate สำหรับ top-of-book only
    - Full slippage ต้องใช้ orderbook depth
```

### B.3 Lighter Market ID Mapping

```
ต้องตรวจสอบจาก GET /api/v1/orderBooks endpoint
เพื่อ map market_id (integer) กับ symbol (string)
เช่น: market_id=0 อาจ = BTCUSDT, market_id=1 = ETHUSDT
จะ fetch mapping นี้ตอน startup
```

---

## Section C: MVP Implementation Plan

### Checkpoint 1: Project Setup + Health Checks
- [x] Folder structure
- [ ] Python venv + dependencies
- [ ] Config management (.env)
- [ ] Health check: Lighter `GET /` -> status
- [ ] Health check: Bybit `GET /v5/market/tickers?category=linear&symbol=BTCUSDT`

### Checkpoint 2: REST Polling MVP
- [ ] Bybit collector: poll tickers + orderbook every 2s
- [ ] Lighter collector: poll orderBookOrders + orderBookDetails every 2s
- [ ] Normalizer: unify into tick format
- [ ] Store to SQLite
- [ ] Compute spread metrics

### Checkpoint 3: WebSocket Upgrade
- [ ] Bybit WS: subscribe `orderbook.1.BTCUSDT`, `tickers.BTCUSDT`
- [ ] Lighter WS: subscribe `ticker/{market_id}`, `order_book/{market_id}`
- [ ] Fallback to REST if WS disconnects

### Checkpoint 4: Backend API
- [ ] `GET /api/v1/prices` - current prices both exchanges
- [ ] `GET /api/v1/spreads` - current + historical spreads
- [ ] `GET /api/v1/funding` - funding rates
- [ ] `GET /api/v1/health` - system health
- [ ] `WS /ws` - real-time price/spread stream to frontend

### Checkpoint 5: Frontend Dashboard
- [ ] Overview page: price table, spread chart
- [ ] Symbol detail page: time-series, orderbook
- [ ] Health page: latency, connection status
- [ ] Auto-refresh via WebSocket

### Checkpoint 6: Alerts
- [ ] Spread threshold alert (configurable)
- [ ] Stale feed detection (no update > 10s)
- [ ] Abnormal latency alert (> 500ms)
- [ ] Alert display in dashboard

---

## Section D: Production-Grade Plan (4-8 weeks)

### D.1 Resilience
- WebSocket auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 60s)
- Sequence ID tracking (Bybit `u` field, Lighter `nonce`)
- Dedup by (exchange, symbol, sequence_id)
- Clock sync: NTP check on startup, warn if drift > 100ms
- Circuit breaker: stop trading if feed gap > 30s

### D.2 Data Quality
- Outlier filter: reject tick if |price_change| > 5% in 1 tick (configurable)
- Stale detection: mark feed as stale after configurable timeout
- Gap handling: log gaps, interpolate for display only (not analytics)
- Cross-validate: compare REST snapshot vs WS state periodically

### D.3 Observability
- Structured logging: structlog -> JSON -> file + stdout
- Metrics: prometheus_client (Python)
  - feed_latency_seconds (histogram, per exchange)
  - ws_reconnect_total (counter, per exchange)
  - spread_value (gauge, per symbol)
  - tick_processing_seconds (histogram)
- Tracing: OpenTelemetry (optional, phase 2)
- Dashboard: Grafana dashboards for ops metrics

### D.4 Database Migration
- SQLite -> PostgreSQL + TimescaleDB
- Hypertable for ticks (partition by time)
- Retention policy: raw ticks 30 days, 1min aggregates 1 year
- Continuous aggregates for common queries

### D.5 Backtesting Harness
- Replay historical ticks from DB
- Paper trading mode: simulated fills with configurable slippage
- Strategy interface: receive tick -> emit signal -> track PnL
- Report: Sharpe, max drawdown, win rate, PnL curve

### D.6 Risk Framework (for Execution Service)
```
max_position_per_symbol: 0.1 BTC (configurable)
max_notional_exposure: $10,000 (configurable)
max_order_rate: 10 orders/minute per exchange
price_sanity_band: reject if |order_price - reference_mid| > 0.5%
kill_switch: manual trigger via API + automatic on:
  - total loss > $500
  - 3 consecutive failed orders
  - feed gap > 30s
  - spread inversion > 2%
circuit_breaker_cooldown: 5 minutes
dry_run_mode: default ON, must explicitly disable
audit_trail: log every decision with full context
```

---

## Section E: Execution Tool Design

### E.1 Module Architecture

```
Signal Module ──► Decision/Risk Module ──► Router Module ──► Execution Module
     │                    │                      │                  │
     │              [approve/reject]        [exchange +         [place/cancel]
     │                    │               order type]              │
     │                    │                      │                  │
     └────────────────────┴──────────────────────┴──► Reconciliation Module
                                                          │
                                                    [confirm fills,
                                                     update position,
                                                     compute PnL]
```

### E.2 Module Responsibilities

**Signal Module**
- Input: normalized tick stream, spread metrics
- Output: OpportunityEvent {symbol, direction, spread_value, confidence, timestamp}
- Logic: z-score threshold, min spread, min liquidity check

**Decision/Risk Module**
- Input: OpportunityEvent + current positions + risk state
- Output: Approved/Rejected + reason
- Checks:
  1. Position limit not exceeded
  2. Notional exposure within budget
  3. Order rate not exceeded
  4. Kill switch not active
  5. Both feeds are fresh (< 2s old)
  6. Spread still exists (re-check before approve)
  7. Dry-run mode check

**Router Module**
- Input: Approved opportunity
- Output: OrderPlan {exchange, side, order_type, price, size}
- Logic:
  - Prefer limit orders (maker) for lower fees
  - If spread is wide enough, use IOC on taker side
  - Split large orders if size > top-of-book

**Execution Module**
- Input: OrderPlan
- Output: OrderResult {order_id, status, filled_size, avg_price}
- Features:
  - Simultaneous submission (asyncio.gather)
  - Timeout per leg (e.g., 5s)
  - Cancel unfilled leg if other leg fails

**Reconciliation Module**
- Input: OrderResults from both legs
- Output: TradeRecord {entry_prices, sizes, fees, net_pnl}
- Features:
  - Confirm fills via REST (don't trust WS only)
  - Update position tracker
  - Compute realized PnL including fees
  - Alert if partial fill (one leg filled, other not)

### E.3 Pseudocode: Two-Leg Arbitrage Flow

```python
async def execute_arb(opportunity: OpportunityEvent):
    """
    Example: Lighter ask < Bybit bid (buy Lighter, sell Bybit)
    """
    # ──── PRE-TRADE CHECKS ────
    if kill_switch.is_active():
        log.warning("Kill switch active, skipping")
        return

    if dry_run_mode:
        log.info(f"DRY RUN: would execute {opportunity}")
        record_paper_trade(opportunity)
        return

    # Re-fetch current prices (don't rely on stale signal)
    lighter_book = await lighter.get_orderbook(opportunity.symbol)
    bybit_book = await bybit.get_orderbook(opportunity.symbol)

    # Validate spread still exists
    current_spread = calc_spread(lighter_book, bybit_book)
    if current_spread < MIN_PROFIT_THRESHOLD:
        log.info("Spread closed before execution")
        return

    # Risk checks
    risk_result = risk_manager.check(opportunity, current_positions)
    if not risk_result.approved:
        log.warning(f"Risk rejected: {risk_result.reason}")
        return

    # Determine order size (min of available qty and position limit)
    size = min(
        lighter_book.best_ask_size,
        bybit_book.best_bid_size,
        risk_manager.max_order_size(opportunity.symbol)
    )

    # ──── EXECUTION (simultaneous) ────
    try:
        leg_buy, leg_sell = await asyncio.gather(
            lighter.place_order(
                symbol=opportunity.symbol,
                side="buy",
                price=lighter_book.best_ask,
                size=size,
                order_type="LIMIT",  # or IOC
                time_in_force="IOC",
                timeout=5.0
            ),
            bybit.place_order(
                symbol=opportunity.symbol,
                side="sell",
                price=bybit_book.best_bid,
                size=size,
                order_type="Limit",
                time_in_force="IOC",
                timeout=5.0
            ),
            return_exceptions=True
        )
    except Exception as e:
        log.error(f"Execution error: {e}")
        await emergency_cancel_all(opportunity.symbol)
        return

    # ──── POST-TRADE RECONCILIATION ────
    # Wait briefly for fill confirmations
    await asyncio.sleep(0.5)

    buy_fill = await lighter.get_order_status(leg_buy.order_id)
    sell_fill = await bybit.get_order_status(leg_sell.order_id)

    if buy_fill.is_filled and sell_fill.is_filled:
        # Both legs filled - success
        pnl = calc_pnl(buy_fill, sell_fill)
        position_tracker.update(opportunity.symbol, buy_fill, sell_fill)
        log.info(f"Arb complete: PnL={pnl}")

    elif buy_fill.is_filled and not sell_fill.is_filled:
        # One leg filled - DANGER: we have unhedged exposure
        log.critical("PARTIAL FILL: buy filled, sell not filled")
        alert_manager.send_critical("Partial fill - manual intervention needed")
        # Attempt to market-sell on Bybit to flatten
        await bybit.place_order(
            symbol=opportunity.symbol,
            side="sell",
            size=buy_fill.filled_size,
            order_type="Market",
        )

    elif not buy_fill.is_filled and sell_fill.is_filled:
        log.critical("PARTIAL FILL: sell filled, buy not filled")
        alert_manager.send_critical("Partial fill - manual intervention needed")
        await lighter.place_order(
            symbol=opportunity.symbol,
            side="buy",
            size=sell_fill.filled_size,
            order_type="MARKET",
        )

    else:
        # Neither filled - safe, no action needed
        log.info("Both legs unfilled, no exposure")

    # Cancel any remaining open orders
    await cancel_remaining_orders(opportunity.symbol)
```

### E.4 Order Type Recommendations

| Scenario | Taker Side | Maker Side | Rationale |
|----------|-----------|-----------|-----------|
| Wide spread, high urgency | IOC on both | - | Ensure fill, accept taker fee |
| Moderate spread | IOC on one, Limit on other | Limit with short TTL | Reduce fee on one leg |
| Narrow spread | Post-only both | Both | Minimize fees, risk of no fill |
| Large size | Split into chunks | - | Reduce market impact |

### E.5 Failure Modes & Mitigations

| Failure Mode | Impact | Mitigation |
|-------------|--------|------------|
| One leg filled, other rejected | Unhedged exposure | Market order to flatten + alert |
| Both legs timeout | No exposure but missed opp | Log, retry on next signal |
| Exchange API down | Cannot trade | Circuit breaker, switch to dry-run |
| Stale price data | Trade on wrong price | Max age check (2s), re-fetch before exec |
| Network partition | Orders in flight, status unknown | Query order status after reconnect, cancel unknowns |
| Rate limit hit | Orders rejected | Backoff, queue with rate limiter |
| Price moved during execution | Worse fill than expected | Slippage tolerance param, post-trade check |
| Position limit exceeded | Risk breach | Pre-check in risk module, hard reject |
| Kill switch triggered mid-trade | Must flatten | Cancel all open orders, alert operator |
| Database unavailable | Cannot persist audit trail | Buffer to file, alert, continue trading (configurable) |

---

## Section F: UI/UX Spec

### F.1 Page Layout

```
┌─────────────────────────────────────────────────┐
│  [Logo] Spread Dashboard    [BTC] [ETH] [Health]│  <- Top nav
├─────────────────────────────────────────────────┤
│                                                  │
│  Page Content (see below per page)               │
│                                                  │
└─────────────────────────────────────────────────┘
```

### F.2 Page 1: Overview

```
┌─────────────────────────────────────────────────┐
│  CONNECTION STATUS                               │
│  Bybit: [●] Connected  Lighter: [●] Connected   │
│  Bybit Latency: 45ms   Lighter Latency: 120ms   │
├─────────────────────────────────────────────────┤
│  PRICE TABLE                                     │
│  ┌─────────┬────────┬────────┬────────┬───────┐ │
│  │ Symbol  │ Bybit  │Lighter │ Spread │ Trend │ │
│  │         │Mid/B/A │Mid/B/A │  (bps) │       │ │
│  ├─────────┼────────┼────────┼────────┼───────┤ │
│  │ BTCUSDT │67,234  │67,245  │ +1.6   │  ↑    │ │
│  │ ETHUSDT │ 3,412  │ 3,415  │ +0.9   │  →    │ │
│  └─────────┴────────┴────────┴────────┴───────┘ │
├─────────────────────────────────────────────────┤
│  SPREAD CHART (last 1h, all symbols)             │
│  [=============== Line Chart ================]   │
├─────────────────────────────────────────────────┤
│  FUNDING RATES                                   │
│  ┌─────────┬────────┬────────┬─────────┐        │
│  │ Symbol  │ Bybit  │Lighter │  Diff   │        │
│  │         │  Rate  │  Rate  │ (ann.)  │        │
│  ├─────────┼────────┼────────┼─────────┤        │
│  │ BTCUSDT │0.01%   │0.008%  │ -2.19%  │        │
│  │ ETHUSDT │0.015%  │0.012%  │ -3.29%  │        │
│  └─────────┴────────┴────────┴─────────┘        │
├─────────────────────────────────────────────────┤
│  ALERTS (latest 5)                               │
│  [!] 14:23 BTCUSDT spread > 5bps (triggered)    │
│  [i] 14:20 Lighter feed latency 450ms            │
└─────────────────────────────────────────────────┘
```

### F.3 Page 2: Symbol Detail

```
┌─────────────────────────────────────────────────┐
│  BTCUSDT Detail                   [1m][5m][1h]  │
├────────────────────┬────────────────────────────┤
│  TOP OF BOOK       │  SPREAD TIME SERIES        │
│  Bybit             │  [=== Line Chart ===]      │
│  Bid: 67,230 (1.2) │  exchange_spread_mid       │
│  Ask: 67,238 (0.8) │  long_spread               │
│  Mid: 67,234       │  short_spread              │
│                    │                            │
│  Lighter           │                            │
│  Bid: 67,240 (0.5) │                            │
│  Ask: 67,250 (0.3) │                            │
│  Mid: 67,245       │                            │
├────────────────────┼────────────────────────────┤
│  METRICS           │  FUNDING TIMELINE          │
│  Spread: +1.6 bps  │  [=== Step Chart ===]      │
│  Z-Score: 0.4      │  Bybit rate                │
│  Imbalance: +0.2   │  Lighter rate              │
│  Basis: +0.02%     │  Differential              │
│  Vol Proxy: 42%    │                            │
│  Latency B: 45ms   │  Next funding:             │
│  Latency L: 120ms  │  Bybit: 2h 15m             │
│                    │  Lighter: 45m              │
└────────────────────┴────────────────────────────┘
```

### F.4 Page 3: Latency / Health

```
┌─────────────────────────────────────────────────┐
│  SYSTEM HEALTH                                   │
├─────────────────────────────────────────────────┤
│  FEED FRESHNESS                                  │
│  ┌──────────┬──────────┬──────────┬───────────┐ │
│  │ Exchange │ Symbol   │ Last Upd │ Status    │ │
│  ├──────────┼──────────┼──────────┼───────────┤ │
│  │ Bybit    │ BTCUSDT  │ 0.2s    │ [●] Fresh │ │
│  │ Bybit    │ ETHUSDT  │ 0.3s    │ [●] Fresh │ │
│  │ Lighter  │ BTCUSDT  │ 1.2s    │ [●] Fresh │ │
│  │ Lighter  │ ETHUSDT  │ 8.5s    │ [◐] Warn  │ │
│  └──────────┴──────────┴──────────┴───────────┘ │
├─────────────────────────────────────────────────┤
│  LATENCY HISTOGRAM (last 5 min)                  │
│  [======= Histogram Chart ========]              │
├─────────────────────────────────────────────────┤
│  RECONNECT LOG                                   │
│  14:15 Lighter WS reconnected (attempt 2)        │
│  13:50 Bybit WS reconnected (attempt 1)          │
├─────────────────────────────────────────────────┤
│  SYSTEM INFO                                     │
│  Uptime: 4h 23m                                  │
│  Ticks processed: 45,231                         │
│  DB size: 12.4 MB                                │
│  Memory: 128 MB                                  │
└─────────────────────────────────────────────────┘
```

### F.5 Page 4: Settings

```
┌─────────────────────────────────────────────────┐
│  SETTINGS                                        │
├─────────────────────────────────────────────────┤
│  SYMBOLS                                         │
│  [x] BTCUSDT   [x] ETHUSDT   [ ] SOLUSDT       │
│  [ ] ARBUSDT   [ ] OPUSDT    [+ Add Symbol]     │
├─────────────────────────────────────────────────┤
│  ALERT THRESHOLDS                                │
│  Spread alert (bps):     [___5___]               │
│  Stale feed timeout (s): [___10__]               │
│  Latency warning (ms):   [___500_]               │
│  Z-score alert:          [___2.0_]               │
├─────────────────────────────────────────────────┤
│  DATA SETTINGS                                   │
│  Poll interval (ms):     [___2000]               │
│  Chart history (min):    [___60__]               │
│  DB retention (days):    [___7___]               │
├─────────────────────────────────────────────────┤
│  [Save Settings]  [Reset to Defaults]            │
└─────────────────────────────────────────────────┘
```

---

## Section G: 10 Questions That Would Change the Design

1. **Symbols**: นอกจาก BTC, ETH แล้ว ต้องการ track กี่ symbol? Lighter รองรับ symbol อะไรบ้าง?
   (ส่งผลต่อ: WS connection count, DB sizing, UI layout)

2. **Market Type**: ต้องการ Bybit spot, perp, หรือทั้งคู่? ถ้าทั้งคู่ต้อง track spot-perp basis ด้วยหรือไม่?
   (ส่งผลต่อ: collector complexity, metrics set)

3. **Hosting**: จะ run บน local Windows เท่านั้น หรือต้อง deploy ขึ้น cloud (AWS/GCP)?
   (ส่งผลต่อ: Docker, CI/CD, latency optimization)

4. **Latency Requirement**: ต้องการ latency ระดับไหน? <100ms (colocation) หรือ <1s (ยอมรับได้)?
   (ส่งผลต่อ: architecture, WS vs REST, data center proximity)

5. **Execution Timeline**: จะเริ่มทำ execution tool จริงเมื่อไหร่? ต้องการ paper trading ก่อนหรือไม่?
   (ส่งผลต่อ: priority ของ risk framework vs dashboard features)

6. **Capital Size**: budget สำหรับ trading ประมาณเท่าไหร่? (ไม่ต้องตอบตัวเลขจริง แค่ order of magnitude)
   (ส่งผลต่อ: position sizing, risk parameters, order splitting logic)

7. **Authentication**: มี API key ของทั้ง Bybit และ Lighter แล้วหรือยัง? Lighter ต้อง on-chain wallet setup?
   (ส่งผลต่อ: MVP scope, auth flow complexity)

8. **Notification**: ต้องการ alert ช่องทางไหน? Dashboard เท่านั้น, หรือต้อง Telegram/Discord/Email?
   (ส่งผลต่อ: alert service design)

9. **Multi-User**: จะใช้คนเดียวหรือต้อง share dashboard กับ team?
   (ส่งผลต่อ: auth, access control, deployment)

10. **Regulatory**: มี concern เรื่อง compliance หรือ geo-restriction ที่ต้องคำนึงถึงไหม?
    (ส่งผลต่อ: API access, execution restrictions, audit requirements)

---

## PM Artifacts

### Milestones

| Milestone | Description | Acceptance Criteria |
|-----------|-------------|-------------------|
| M1: Foundation | Health checks + REST polling + DB | ทั้ง 2 exchange ดึงราคาได้, store ลง DB |
| M2: Real-time | WebSocket upgrade + spread calc | WS connected, spread คำนวณถูกต้อง |
| M3: Dashboard | Frontend MVP ครบ 4 pages | เปิด browser เห็นราคา real-time |
| M4: Alerts | Alert engine + threshold config | ได้ alert เมื่อ spread เกิน threshold |
| M5: Production | Postgres + monitoring + resilience | System stable 24h+ ไม่ crash |
| M6: Backtest | Historical replay + paper trading | Run backtest ได้, PnL report ออกมา |
| M7: Execution MVP | Dry-run execution + risk controls | Paper trade 100 arb cycles สำเร็จ |

### Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Lighter API เปลี่ยน/ล่ม | Medium | High | Abstract collector, fallback to REST, monitor status |
| Bybit rate limit | Low | Medium | Respect limits, use WS over REST, backoff |
| Lighter market_id mapping เปลี่ยน | Medium | Medium | Dynamic fetch on startup, cache with TTL |
| WS disconnect frequent | Medium | Medium | Auto-reconnect, sequence tracking, REST fallback |
| Partial fill on arb | Medium | Critical | Auto-flatten, kill switch, max position limit |
| Clock drift between exchanges | Low | Medium | NTP sync, use exchange timestamps |
| SQLite lock contention (MVP) | Medium | Low | Migrate to Postgres in production |
| Lighter low liquidity | High | High | Min liquidity check before execution, size limit |

### Task Board (Notion-style)

**Backlog:**
| Task | Complexity |
|------|-----------|
| Telegram/Discord alert integration | M |
| Orderbook depth visualization | M |
| Multi-timeframe z-score | S |
| Volatility surface for spreads | L |
| Position management UI | L |
| Backtest report generator | M |
| Docker Compose setup | S |
| CI/CD pipeline | M |
| Prometheus + Grafana setup | M |
| PostgreSQL + TimescaleDB migration | L |
| Paper trading engine | L |
| Execution module (dry-run) | L |
| Risk management UI | M |
| Historical data export (CSV) | S |
| Dark mode UI | S |

**Doing:**
| Task | Complexity |
|------|-----------|
| Project scaffolding + dependencies | S |
| Bybit REST collector | S |
| Lighter REST collector | M |

**Done:**
| Task | Complexity |
|------|-----------|
| API research (Bybit + Lighter) | M |
| System architecture design | L |
| Data model design | M |
| UI/UX wireframes | M |
