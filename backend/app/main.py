# file: backend/app/main.py
"""
Spread Dashboard - FastAPI Backend
Entry point for the application.

Run: uvicorn app.main:app --reload --port 8000
(from the backend/ directory)
"""
import asyncio
import json
import time
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router
from app.portfolio.router import router as portfolio_router
from app.collectors import bybit_collector, lighter_collector
from app.analytics.spread_engine import update_tick, compute_spread, get_all_current_data
from app.storage.database import init_db, insert_tick, insert_spread, cleanup_old_data, close_db, commit as db_commit
from app.alerts import on_spread_update, close_telegram_session

log = structlog.get_logger()

# --- Connected WebSocket clients ---
# Maps each WebSocket to its subscribed symbols.
# None means "subscribe to all" (backward compatible default).
ws_clients: dict[WebSocket, set[str] | None] = {}

# --- Background task handle ---
_poll_task: asyncio.Task | None = None


_consecutive_errors = 0


async def poll_loop():
    """
    Background polling loop with resilience.
    - Timeout per cycle (10s) prevents hang
    - Calculates remaining sleep to keep consistent interval
    - Consecutive error tracking with warning escalation
    """
    global _consecutive_errors
    symbols = settings.symbol_list
    interval = settings.poll_interval_seconds
    log.info("poll_loop_started", interval_s=interval, symbols=symbols)

    while True:
        t0 = time.time()
        try:
            # Fetch ALL symbols from BOTH exchanges — with 10s timeout
            tasks = []
            for symbol in symbols:
                tasks.append(bybit_collector.fetch_ticker(symbol, category="linear"))
                tasks.append(lighter_collector.fetch_ticker(symbol))

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                log.error("poll_cycle_timeout", symbols=symbols)
                _consecutive_errors += 1
                await asyncio.sleep(max(0.5, interval))
                continue

            # Process results in pairs (bybit, lighter) per symbol
            # Each symbol is isolated — one failure won't block others
            for i, symbol in enumerate(symbols):
                try:
                    bybit_tick = results[i * 2]
                    lighter_tick = results[i * 2 + 1]

                    if isinstance(bybit_tick, Exception):
                        log.error("bybit_poll_error", symbol=symbol, error=str(bybit_tick))
                    elif bybit_tick:
                        await update_tick(bybit_tick)
                        await insert_tick(bybit_tick)

                    if isinstance(lighter_tick, Exception):
                        log.error("lighter_poll_error", symbol=symbol, error=str(lighter_tick))
                    elif lighter_tick:
                        await update_tick(lighter_tick)
                        await insert_tick(lighter_tick)

                    spread = compute_spread(symbol)
                    if spread:
                        await insert_spread(spread)
                        await on_spread_update(spread)
                except Exception as e:
                    log.error("symbol_processing_error", symbol=symbol, error=str(e))

            # Single batch commit for all inserts this cycle
            await db_commit()

            # Broadcast to connected WS clients (filtered by subscription)
            if ws_clients:
                all_data = get_all_current_data()
                ts = time.time() * 1000
                # Pre-serialize full payload once for unfiltered clients
                all_msg = json.dumps({"type": "update", "data": all_data, "ts": ts})
                disconnected = []
                for ws, subscribed in list(ws_clients.items()):
                    try:
                        if subscribed is None:
                            await ws.send_text(all_msg)
                        else:
                            filtered = {s: all_data[s] for s in subscribed if s in all_data}
                            if filtered:
                                await ws.send_text(json.dumps({"type": "update", "data": filtered, "ts": ts}))
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    ws_clients.pop(ws, None)

            # Reset error counter on success
            _consecutive_errors = 0

            cycle_ms = (time.time() - t0) * 1000
            if cycle_ms > 1500:
                log.warning("poll_cycle_slow", cycle_ms=round(cycle_ms))

        except Exception as e:
            _consecutive_errors += 1
            log.error("poll_loop_error", error=str(e), consecutive=_consecutive_errors)
            if _consecutive_errors >= 5:
                log.warning("poll_loop_degraded", consecutive_errors=_consecutive_errors)

        # Sleep remaining interval (maintain consistent timing)
        elapsed = time.time() - t0
        sleep_s = max(0.1, interval - elapsed)
        await asyncio.sleep(sleep_s)


async def _supervised_poll_loop():
    """Supervisor: if poll_loop crashes, wait 2s and restart."""
    while True:
        try:
            await poll_loop()
        except asyncio.CancelledError:
            raise  # Propagate cancellation from shutdown
        except Exception as e:
            log.error("poll_loop_crashed", error=str(e))
            await asyncio.sleep(2)
            log.info("poll_loop_restarting")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    log.info("app_starting", env=settings.app_env)
    await init_db()

    # Load Lighter market ID mapping
    await lighter_collector.fetch_market_ids()

    # Cleanup old data on startup (keep last 7 days)
    deleted = await cleanup_old_data(days=7)
    if deleted > 0:
        log.info("db_cleanup_on_startup", rows_deleted=deleted)

    # Start background polling with supervision (auto-restart on crash)
    global _poll_task
    _poll_task = asyncio.create_task(_supervised_poll_loop())

    yield

    # Shutdown
    log.info("app_shutting_down")
    if _poll_task:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
    # Close persistent HTTP sessions + DB
    await bybit_collector.close_session()
    await lighter_collector.close_session()
    await close_telegram_session()
    await close_db()


# --- FastAPI App ---
app = FastAPI(
    title="Spread Dashboard API",
    version="0.1.0",
    description="Real-time price spread dashboard for Bybit & Lighter",
    lifespan=lifespan,
)

# CORS - allow frontend dev server (configurable via CORS_ORIGINS env)
_cors_origins = [
    o.strip()
    for o in (settings.cors_origins or "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
app.include_router(router)
app.include_router(portfolio_router)


# Pre-serialized static message — avoids json.dumps on every ping
_PONG_MSG = json.dumps({"type": "pong"})


# --- WebSocket endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients[ws] = None  # None = subscribed to all (backward compatible)
    log.info("ws_client_connected", total=len(ws_clients))
    try:
        # Send initial snapshot (all data)
        data = get_all_current_data()
        await ws.send_text(json.dumps({"type": "snapshot", "data": data, "ts": time.time() * 1000}))

        # Listen for client messages
        while True:
            raw = await ws.receive_text()
            if raw == "ping":
                await ws.send_text(_PONG_MSG)
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "subscribe":
                symbols = msg.get("symbols", [])
                if isinstance(symbols, list):
                    current = ws_clients.get(ws)
                    if current is None:
                        current = set()
                    current.update(s for s in symbols if isinstance(s, str))
                    ws_clients[ws] = current
                    log.info("ws_subscribe", symbols=list(current))
                    # Send immediate snapshot for subscribed symbols
                    all_data = get_all_current_data()
                    filtered = {s: all_data[s] for s in current if s in all_data}
                    if filtered:
                        await ws.send_text(json.dumps({
                            "type": "snapshot", "data": filtered, "ts": time.time() * 1000
                        }))

            elif msg_type == "unsubscribe":
                symbols = msg.get("symbols", [])
                if isinstance(symbols, list):
                    current = ws_clients.get(ws)
                    if current is not None:
                        current.difference_update(symbols)

    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.pop(ws, None)
        log.info("ws_client_disconnected", total=len(ws_clients))


@app.get("/")
async def root():
    return {
        "name": "Spread Dashboard API",
        "version": "0.1.0",
        "docs": "/docs",
    }
