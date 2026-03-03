# Test Coverage Analysis

## Current State: Zero Test Coverage

The codebase has **no test files, no testing frameworks installed, and no test scripts configured** — for both the backend (Python/FastAPI) and frontend (React/TypeScript). There is also no CI/CD pipeline to enforce quality gates.

---

## Priority 1 — Pure Computation Logic (Unit Tests, No Mocking Required)

These modules contain deterministic, side-effect-free functions that are the most valuable and easiest to test.

### 1.1 Spread Engine (`backend/app/analytics/spread_engine.py`)

| Function | Why It Matters | What to Test |
|---|---|---|
| `compute_spread()` | Core business logic — every dashboard number derives from this | Correct spread formulas (mid, long, short), basis calculation, zero-price guards, missing-tick guards |
| `compute_zscore()` | Statistical computation driving alerts/signals | Correct z-score math, behavior with <10 samples, behavior with zero variance, rolling window eviction |
| `compute_imbalance()` | Orderbook imbalance metric | Balanced book → 0, all bid → +1, all ask → -1, zero total guard, None size inputs |
| `get_all_current_data()` | Snapshot aggregation for WebSocket broadcast | Correct assembly of spread + zscore + imbalance per symbol, handling of missing exchanges |

**Example test scenarios for `compute_spread`:**
- Both exchanges present with normal prices → verify all spread fields
- Only one exchange present → returns `None`
- Zero mid/bid/ask prices → returns `None`
- Mark/index price present → basis computed in bps
- Mark/index price absent → basis fields are `None`

### 1.2 Maker Engine Helpers (`backend/app/execution/maker_engine.py`)

| Function | Why It Matters | What to Test |
|---|---|---|
| `round_price_to_tick()` | Price rounding for order placement (money math) | Buy rounds down, Sell rounds up, zero tick edge case, various tick sizes |
| `round_qty_to_step()` | Quantity rounding for exchange constraints | Floors to step, zero step edge case |
| `validate_qty()` | Order size validation | Below min → raises, above max → clamped, within range → pass-through |
| `compute_book_metrics()` | Orderbook analysis | Correct mid, spread, microprice, empty book → raises |
| `compute_maker_price()` | Maker-safe price computation | QUEUE_TOP vs STEP_AHEAD, Buy never crosses ask, Sell never crosses bid |
| `select_mode()` | Aggressiveness strategy selection | CONSERVATIVE → QUEUE_TOP, AGGRESSIVE → STEP_AHEAD, BALANCED + microprice signal |
| `VolTracker` | Volatility estimation | Push + get_move_ticks, window eviction, single-sample edge case |
| `_shift_away()` | PostOnly rejection recovery | Buy shifts down by tick, Sell shifts up by tick |

**This is the highest-ROI test target** — these functions handle real money math with `Decimal` precision and directly affect trade execution correctness.

### 1.3 Data Models (`backend/app/models/tick.py`)

| Model | What to Test |
|---|---|
| `NormalizedTick` | Auto-computed `mid` from bid/ask, auto `received_at`, latency computation (positive/reasonable only), clock-skew rejection (>30s or negative) |
| `SpreadMetric` | Field validation, optional fields default to None |
| `FundingSnapshot` | Field validation |
| `Alert` | Field validation |

### 1.4 Settings (`backend/app/config/settings.py`)

| Property | What to Test |
|---|---|
| `symbol_list` | Comma parsing, whitespace trimming, empty string handling |
| `poll_interval_seconds` | ms→s conversion |
| `lighter_aliases` | Alias map parsing, empty map, malformed entries |

---

## Priority 2 — Database Layer (Integration Tests, Requires SQLite)

### 2.1 Storage (`backend/app/storage/database.py`)

These tests need a temporary in-memory or file-based SQLite database but no network access.

| Function | What to Test |
|---|---|
| `init_db()` | Tables created, indexes exist, migration columns added idempotently |
| `insert_tick()` + `get_recent_spreads()` | Round-trip: insert spread → query returns correct data |
| `insert_spread()` | All fields persisted including nullable `basis_bybit`, `basis_bybit_bps` |
| `get_spreads_by_time()` | Time filtering works correctly, ordering is ASC |
| `get_recent_alerts()` | Ordering DESC, limit respected |
| `cleanup_old_data()` | Rows older than N days deleted, newer rows preserved, VACUUM doesn't crash, error resilience |
| `insert_alert()` | Round-trip persistence |

**Setup pattern:** Override `DB_PATH` to `:memory:` or a temp file, call `init_db()`, run tests, teardown.

---

## Priority 3 — API Route Tests (Integration Tests, Requires FastAPI TestClient)

### 3.1 REST API (`backend/app/api/routes.py`)

Use FastAPI's `TestClient` with mocked dependencies (spread engine, database, collectors).

| Endpoint | What to Test |
|---|---|
| `GET /api/v1/health` | Response structure, handles collector failures gracefully |
| `GET /api/v1/prices` | Returns current data snapshot |
| `GET /api/v1/spreads` | Query params (`symbol`, `limit`, `minutes`), limit validation (≤5000), minutes validation (≤1440) |
| `GET /api/v1/spreads/export` | CSV format, correct headers, correct filename |
| `GET /api/v1/funding` | Response structure per symbol, handles missing funding data |
| `GET /api/v1/config` | Returns non-sensitive config only (no API keys leaked) |
| `POST /api/v1/execute` | Side mapping (`LONG_LIGHTER` → `BUY_LIGHTER_SELL_BYBIT`), input validation |
| `POST /api/v1/execute/maker_test` | Side validation (only "Buy"/"Sell"), 400 on invalid side |
| `POST /api/v1/execute/close_all` | Request body validation |

**Security-relevant test:** Verify `/config` does NOT expose `bybit_api_key`, `bybit_api_secret`, `lighter_private_key`.

---

## Priority 4 — Collector Tests (Unit Tests with Mocked HTTP)

### 4.1 Bybit Collector (`backend/app/collectors/bybit_collector.py`)

Mock `aiohttp` responses to test parsing logic without network calls.

| Scenario | What to Test |
|---|---|
| Successful ticker response | Correct `NormalizedTick` fields parsed, funding cache populated |
| API returns `retCode != 0` | Returns `None`, no crash |
| Empty result list | Returns `None` |
| Zero bid/ask prices | Returns `None` |
| Funding rate parsing | Rate, annualized rate (×1095), next funding time |
| Funding cache TTL | Stale cache triggers fresh fetch |
| Network timeout/exception | Returns `None`, logs error |
| Health check | Response structure, latency measurement |

### 4.2 Lighter Collector (`backend/app/collectors/lighter_collector.py`)

| Scenario | What to Test |
|---|---|
| `_normalize_symbol()` | "ETH" → "ETHUSDT", "BTCUSDT" → "BTCUSDT" (no double suffix) |
| `fetch_market_ids()` | Parses order books response, populates mappings, filters by status/market_type |
| `_use_fallback()` | Fallback mapping is populated correctly |
| `_resolve_symbol()` | Alias resolution from settings |
| 429 rate limiting | Backoff period skips requests, counter resets on success |
| Empty orderbook | Returns `None` |
| Funding rate cache | TTL refresh, correct parsing |

---

## Priority 5 — Execution Layer (Unit Tests with Mocked Clients)

### 5.1 Arbitrage Executor (`backend/app/services/executor.py`)

| Scenario | What to Test |
|---|---|
| Happy path | Both sides succeed, correct result returned |
| Lighter fails, Bybit succeeds | Bybit position is reversed for safety |
| Bybit fails, Lighter succeeds | Lighter position is reversed |
| Both fail | Exception with both errors |
| Maker abort (not exception) | Detected as failure, triggers reversal |
| `_build_maker_config()` | Settings mapped correctly with defaults |
| `emergency_close_auto()` | Auto-detects positions, closes both sides |
| `emergency_close_both_sides()` | No positions → no-op, partial failure handling |

### 5.2 Smart Maker Engine (`backend/app/execution/maker_engine.py`)

The main `smart_execute_maker()` function requires a mock `client` object. Test the state machine:

| Scenario | What to Test |
|---|---|
| Immediate fill | Status = "filled", correct VWAP, timing |
| Timeout + market fallback | Status = "market_fallback", taker fee applied |
| Timeout, fallback disabled | Status = "partial" or "aborted" |
| PostOnly rejection + retry | Shifts price, increments reject count |
| Volatility guard triggered | Skips repricing cycle |
| Deviation guard triggered | Status = "aborted" with detail |
| Stall escalation | After N stall intervals, mode → STEP_AHEAD |
| Fee estimation | Maker vs taker fee split correct |
| Price improvement calculation | Buy below mid = positive, sell above mid = positive |

---

## Priority 6 — Frontend Tests

### 6.1 API Service (`frontend/src/services/api.ts`)

| What to Test |
|---|
| `fetchJSON` builds correct URLs, throws on non-OK response |
| `postJSON` sends correct headers/body, parses error detail |
| `api.spreads()` query param construction (minutes vs limit) |
| `api.exportCsvUrl()` returns correct URL string |

### 6.2 WebSocket Hook (`frontend/src/hooks/useWebSocket.ts`)

| What to Test |
|---|
| Connects to provided URL |
| `onMessage` callback fires with parsed JSON |
| Auto-subscribe sends subscribe message on open |
| Reconnects after close (3s delay) |
| `subscribe()` / `unsubscribe()` send correct message format |
| `send()` no-ops when not connected |

---

## Recommended Testing Stack

### Backend

```
# Add to backend/requirements.txt (dev section)
pytest==8.3.4
pytest-asyncio==0.24.0
pytest-cov==6.0.0
aioresponses==0.7.7        # mock aiohttp
httpx==0.28.1               # for FastAPI TestClient (async)
```

### Frontend

```bash
# Install dev dependencies
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

### Coverage Target

| Layer | Suggested initial target |
|---|---|
| Spread engine + maker helpers | 95%+ (pure logic, easy to test) |
| Data models | 90%+ |
| Database layer | 85%+ |
| API routes | 80%+ |
| Collectors (parsing logic) | 80%+ |
| Execution layer | 75%+ |
| Frontend services/hooks | 70%+ |

### Suggested File Structure

```
backend/
  tests/
    __init__.py
    conftest.py                  # shared fixtures (db, mock ticks, settings)
    test_spread_engine.py        # Priority 1.1
    test_maker_helpers.py        # Priority 1.2
    test_models.py               # Priority 1.3
    test_settings.py             # Priority 1.4
    test_database.py             # Priority 2
    test_api_routes.py           # Priority 3
    test_bybit_collector.py      # Priority 4.1
    test_lighter_collector.py    # Priority 4.2
    test_executor.py             # Priority 5.1
    test_maker_engine.py         # Priority 5.2

frontend/
  src/
    services/__tests__/
      api.test.ts                # Priority 6.1
    hooks/__tests__/
      useWebSocket.test.ts       # Priority 6.2
```

---

## Quick Wins (Start Here)

If you want immediate impact with minimal setup, write these three test files first:

1. **`test_spread_engine.py`** — Tests `compute_spread`, `compute_zscore`, `compute_imbalance`. Zero dependencies, pure math, catches formula bugs.

2. **`test_maker_helpers.py`** — Tests `round_price_to_tick`, `round_qty_to_step`, `validate_qty`, `compute_book_metrics`, `compute_maker_price`. These handle real money with `Decimal` — bugs here lose money.

3. **`test_models.py`** — Tests `NormalizedTick` auto-computation logic (`mid`, `received_at`, `latency_ms`). Catches data pipeline bugs early.

These three files cover the most critical business logic with zero mocking required.
