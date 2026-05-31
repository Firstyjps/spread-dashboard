# file: backend/app/main.py
"""
Spread Dashboard -> Alphast - FastAPI Backend
Entry point for the application.

Run: uvicorn app.main:app --reload --port 8000
(from the backend/ directory)
"""
import asyncio
import json
import time
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request as _StarletteRequest
from starlette.responses import JSONResponse as _StarletteJSONResponse
from app.api.routes import router
from app.api.monitor_routes import router as monitor_router
from app.portfolio.router import router as portfolio_router
from app.api.auto_hedge_routes import router as auto_hedge_router
from app.api.sl_tp_routes import router as sl_tp_router
from app.api.risk_routes import router as risk_router
from app.api.ai_routes import router as ai_router
from app.api.settings_routes import router as settings_router
from app.collectors import bybit_collector, lighter_collector
from app.analytics.spread_engine import update_tick, compute_spread, get_all_current_data, get_latest_tick
from app.storage.database import init_db, insert_tick, insert_spread, close_db, commit as db_commit, cleanup_old_data
from app.alerts import on_spread_update, close_telegram_session, start_telegram_bot, send_system_alert
from app.metrics import POLL_CYCLE_DURATION, WS_CLIENTS, CONSECUTIVE_ERRORS
from app.services.circuit_breaker import circuit_breaker
from app.services.reconciliation import get_reconciliation_service
from app.services.monitor import get_monitor_service
from app.risk import get_risk_engine

log = structlog.get_logger()

# --- Connected WebSocket clients ---
# Maps each WebSocket to its subscribed symbols.
# None means "subscribe to all" (backward compatible default).
ws_clients: dict[WebSocket, set[str] | None] = {}
ws_send_locks: dict[WebSocket, asyncio.Lock] = {}

# --- Background task handles ---
_poll_task: asyncio.Task | None = None
_monitor_task: asyncio.Task | None = None
_bot_task: asyncio.Task | None = None
_cleanup_task: asyncio.Task | None = None


_consecutive_errors = 0


async def _send_ws_text(ws: WebSocket, message: str) -> None:
    lock = ws_send_locks.setdefault(ws, asyncio.Lock())
    async with lock:
        await ws.send_text(message)


def _remove_ws_client(ws: WebSocket) -> None:
    ws_clients.pop(ws, None)
    ws_send_locks.pop(ws, None)


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
            # Fetch ALL symbols from ALL exchanges — with 10s timeout
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
                CONSECUTIVE_ERRORS.set(_consecutive_errors)
                if _consecutive_errors >= 5:
                    await send_system_alert(
                        "poll_degraded",
                        f"Poll loop has {_consecutive_errors} consecutive errors after timeout",
                        severity="warning",
                        value=float(_consecutive_errors),
                    )
                POLL_CYCLE_DURATION.observe(time.time() - t0)
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
            await _check_feed_staleness(symbols)

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
                            await _send_ws_text(ws, all_msg)
                        else:
                            filtered = {s: all_data[s] for s in subscribed if s in all_data}
                            if filtered:
                                await _send_ws_text(
                                    ws,
                                    json.dumps({"type": "update", "data": filtered, "ts": ts}),
                                )
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    _remove_ws_client(ws)

            # Reset error counter on success
            _consecutive_errors = 0
            CONSECUTIVE_ERRORS.set(_consecutive_errors)
            WS_CLIENTS.set(len(ws_clients))

            cycle_ms = (time.time() - t0) * 1000
            POLL_CYCLE_DURATION.observe(cycle_ms / 1000)
            if cycle_ms > 1500:
                log.warning("poll_cycle_slow", cycle_ms=round(cycle_ms))

        except Exception as e:
            _consecutive_errors += 1
            log.error("poll_loop_error", error=str(e), consecutive=_consecutive_errors)
            if _consecutive_errors >= 5:
                log.warning("poll_loop_degraded", consecutive_errors=_consecutive_errors)
                await send_system_alert(
                    "poll_degraded",
                    f"Poll loop degraded with {_consecutive_errors} consecutive errors: {e}",
                    severity="warning",
                    value=float(_consecutive_errors),
                )
            CONSECUTIVE_ERRORS.set(_consecutive_errors)
            POLL_CYCLE_DURATION.observe(time.time() - t0)

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
            await send_system_alert("poll_crash", f"Poll loop crashed: {e}", severity="critical")
            await asyncio.sleep(2)
            log.info("poll_loop_restarting")


async def monitor_poll_loop():
    """Background monitor loop for multi-exchange spread snapshots."""
    service = get_monitor_service()
    interval = settings.monitor_poll_interval_ms / 1000.0
    log.info("monitor_poll_loop_started", interval_s=interval)

    while True:
        t0 = time.time()
        try:
            snapshot = await service.fetch_current_spreads(group="gold", store_history=True)
            if ws_clients:
                await _broadcast_monitor_update(snapshot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("monitor_poll_loop_error", error=str(e))

        elapsed = time.time() - t0
        await asyncio.sleep(max(0.1, interval - elapsed))


async def _supervised_monitor_poll_loop():
    """Supervisor for monitor_poll_loop."""
    while True:
        try:
            await monitor_poll_loop()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("monitor_poll_loop_crashed", error=str(e))
            await asyncio.sleep(2)
            log.info("monitor_poll_loop_restarting")


async def _broadcast_monitor_update(snapshot: dict) -> None:
    msg = json.dumps({"type": "monitor_update", "data": snapshot, "ts": snapshot.get("ts")})
    disconnected = []
    for ws in list(ws_clients.keys()):
        try:
            await _send_ws_text(ws, msg)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _remove_ws_client(ws)


async def _check_feed_staleness(symbols: list[str]):
    now_ms = time.time() * 1000
    for symbol in symbols:
        for exchange in ("bybit", "lighter"):
            tick = get_latest_tick(exchange, symbol)
            if not tick:
                continue
            last_ts = tick.received_at or tick.ts
            if circuit_breaker.check_feed_staleness(last_ts):
                age_s = (now_ms - last_ts) / 1000
                await send_system_alert(
                    "feed_stale",
                    f"{exchange} feed for {symbol} is stale for {age_s:.1f}s; circuit breaker tripped",
                    severity="critical",
                    value=age_s,
                    threshold=circuit_breaker.feed_gap_threshold_s,
                )
        try:
            await get_risk_engine().check_feed_health(symbol)
            await get_risk_engine().check_spread_inversion(symbol)
        except Exception as e:
            log.error("risk_background_check_error", symbol=symbol, error=str(e))



async def daily_cleanup_loop():
    """Background task: prune rows older than settings.data_retention_days every 24h.

    First run waits 60s after startup so the DB is settled, then runs once
    per day. Never crashes the process — cleanup_old_data swallows errors.
    """
    await asyncio.sleep(60)
    while True:
        try:
            deleted = await cleanup_old_data(days=settings.data_retention_days)
            await get_risk_engine().cleanup()
            log.info("daily_cleanup_ran", days=settings.data_retention_days, deleted=deleted)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("daily_cleanup_error", error=str(e))
        await asyncio.sleep(86400)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    log.info("app_starting", env=settings.app_env)
    await init_db()
    await get_risk_engine().initialize()

    # Load Lighter market ID mapping
    await lighter_collector.fetch_market_ids()

    # Data is preserved across restarts — no auto-cleanup.
    # To manually purge old data, call: DELETE FROM spread_metrics WHERE ts < ?

    # Start Lighter WebSocket for mark/index prices
    lighter_collector.start_market_stats_ws()

    # Start background polling with supervision (auto-restart on crash)
    global _poll_task, _monitor_task, _bot_task, _cleanup_task
    _poll_task = asyncio.create_task(_supervised_poll_loop())
    _monitor_task = asyncio.create_task(_supervised_monitor_poll_loop())
    _cleanup_task = asyncio.create_task(daily_cleanup_loop())
    await get_reconciliation_service().start()

    # Start Telegram bot command listener
    _bot_task = asyncio.create_task(start_telegram_bot())

    yield

    # Shutdown
    log.info("app_shutting_down")
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    if _bot_task:
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
    if _poll_task:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    await get_reconciliation_service().stop()
    # Stop auto-hedge if running
    from app.services.auto_hedge import get_auto_hedge_service
    _hedge_svc = get_auto_hedge_service()
    if _hedge_svc._running:
        await _hedge_svc.stop()
    # Stop SL/TP if running
    from app.services.sl_tp import get_sl_tp_service
    _sltp_svc = get_sl_tp_service()
    if _sltp_svc._running:
        await _sltp_svc.stop()

    # Close persistent HTTP sessions + DB
    await lighter_collector.stop_market_stats_ws()
    await get_monitor_service().close()
    await bybit_collector.close_session()
    await lighter_collector.close_session()
    await close_telegram_session()
    await close_db()


# --- FastAPI App ---
app = FastAPI(
    title="Alphast API",
    version="0.1.0",
    description="Real-time price spread dashboard for Bybit & Lighter",
    lifespan=lifespan,
)
app.state.limiter = limiter

async def _rate_limit_handler(request: _StarletteRequest, exc: RateLimitExceeded):
    return _StarletteJSONResponse(status_code=429, content={"detail": f"Rate limit exceeded: {exc.detail}"})

app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS - allow frontend dev server (configurable via CORS_ORIGINS env)
_cors_origins = [
    o.strip()
    for o in (settings.cors_origins or "https://dash.firstyjps.com,http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Include REST routes
app.include_router(router)
app.include_router(monitor_router)
app.include_router(portfolio_router)
app.include_router(auto_hedge_router)
app.include_router(sl_tp_router)
app.include_router(risk_router)
app.include_router(ai_router)
app.include_router(settings_router)


# Pre-serialized static message — avoids json.dumps on every ping
_PONG_MSG = json.dumps({"type": "pong"})


# --- WebSocket endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str | None = Query(default=None)):
    await ws.accept()
    ws_clients[ws] = None  # None = subscribed to all (backward compatible)
    ws_send_locks[ws] = asyncio.Lock()
    WS_CLIENTS.set(len(ws_clients))
    log.info("ws_client_connected", total=len(ws_clients))
    try:
        # Send initial snapshot (all data)
        data = get_all_current_data()
        await _send_ws_text(ws, json.dumps({"type": "snapshot", "data": data, "ts": time.time() * 1000}))

        # Listen for client messages
        while True:
            raw = await ws.receive_text()
            if raw == "ping":
                await _send_ws_text(ws, _PONG_MSG)
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
                        await _send_ws_text(
                            ws,
                            json.dumps({"type": "snapshot", "data": filtered, "ts": time.time() * 1000}),
                        )

            elif msg_type == "unsubscribe":
                symbols = msg.get("symbols", [])
                if isinstance(symbols, list):
                    current = ws_clients.get(ws)
                    if current is not None:
                        current.difference_update(symbols)

    except WebSocketDisconnect:
        pass
    finally:
        _remove_ws_client(ws)
        WS_CLIENTS.set(len(ws_clients))
        log.info("ws_client_disconnected", total=len(ws_clients))


@app.get("/")
async def root():
    return {
        "name": "Alphast API",
        "version": "0.1.0",
        "docs": "/docs",
    }
