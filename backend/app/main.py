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
from app.collectors import bybit_collector, lighter_collector
from app.analytics.spread_engine import update_tick, compute_spread, get_all_current_data
from app.storage.database import init_db, insert_tick, insert_spread, cleanup_old_data

log = structlog.get_logger()

# --- Connected WebSocket clients ---
# Maps each WebSocket to its subscribed symbols.
# None means "subscribe to all" (backward compatible default).
ws_clients: dict[WebSocket, set[str] | None] = {}

# --- Background task handle ---
_poll_task: asyncio.Task | None = None


async def poll_loop():
    """
    Background polling loop.
    Fetches ALL symbols from both exchanges in parallel (not sequentially),
    computes spreads, stores to DB, and broadcasts to WebSocket clients.
    """
    symbols = settings.symbol_list
    log.info("poll_loop_started", interval_s=settings.poll_interval_seconds, symbols=symbols)

    while True:
        t0 = time.time()
        try:
            # Fetch ALL symbols from BOTH exchanges in one parallel batch
            tasks = []
            for symbol in symbols:
                tasks.append(bybit_collector.fetch_ticker(symbol, category="linear"))
                tasks.append(lighter_collector.fetch_ticker(symbol))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results in pairs (bybit, lighter) per symbol
            for i, symbol in enumerate(symbols):
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

            # Broadcast to connected WS clients (filtered by subscription)
            if ws_clients:
                all_data = get_all_current_data()
                ts = time.time() * 1000
                disconnected = []
                for ws, subscribed in list(ws_clients.items()):
                    try:
                        if subscribed is None:
                            filtered = all_data
                        else:
                            filtered = {s: all_data[s] for s in subscribed if s in all_data}
                        if filtered:
                            await ws.send_text(json.dumps({"type": "update", "data": filtered, "ts": ts}))
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    ws_clients.pop(ws, None)

            cycle_ms = (time.time() - t0) * 1000
            if cycle_ms > 1500:
                log.warning("poll_cycle_slow", cycle_ms=round(cycle_ms))

        except Exception as e:
            log.error("poll_loop_error", error=str(e))

        await asyncio.sleep(settings.poll_interval_seconds)


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

    # Start background polling
    global _poll_task
    _poll_task = asyncio.create_task(poll_loop())

    yield

    # Shutdown
    log.info("app_shutting_down")
    if _poll_task:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
    # Close persistent HTTP sessions
    await bybit_collector.close_session()
    await lighter_collector.close_session()


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
                await ws.send_text(json.dumps({"type": "pong"}))
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
