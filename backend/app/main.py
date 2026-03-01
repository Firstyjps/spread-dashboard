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
ws_clients: set[WebSocket] = set()

# --- Background task handle ---
_poll_task: asyncio.Task | None = None


async def poll_loop():
    """
    Background polling loop.
    Fetches prices from both exchanges, computes spreads, stores to DB,
    and broadcasts to WebSocket clients.
    """
    log.info("poll_loop_started", interval_s=settings.poll_interval_seconds, symbols=settings.symbol_list)

    while True:
        try:
            for symbol in settings.symbol_list:
                # Fetch ticks from both exchanges concurrently
                bybit_tick, lighter_tick = await asyncio.gather(
                    bybit_collector.fetch_ticker(symbol, category="linear"),
                    lighter_collector.fetch_ticker(symbol),
                    return_exceptions=True,
                )

                # Process Bybit tick
                if isinstance(bybit_tick, Exception):
                    log.error("bybit_poll_error", symbol=symbol, error=str(bybit_tick))
                elif bybit_tick:
                    await update_tick(bybit_tick)
                    await insert_tick(bybit_tick)

                # Process Lighter tick
                if isinstance(lighter_tick, Exception):
                    log.error("lighter_poll_error", symbol=symbol, error=str(lighter_tick))
                elif lighter_tick:
                    await update_tick(lighter_tick)
                    await insert_tick(lighter_tick)

                # Compute spread if both ticks available
                spread = compute_spread(symbol)
                if spread:
                    await insert_spread(spread)

            # Broadcast to all connected WS clients
            if ws_clients:
                data = get_all_current_data()
                message = json.dumps({"type": "update", "data": data, "ts": time.time() * 1000})
                disconnected = set()
                for ws in list(ws_clients):
                    try:
                        await ws.send_text(message)
                    except Exception:
                        disconnected.add(ws)
                ws_clients.difference_update(disconnected)

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
    ws_clients.add(ws)
    log.info("ws_client_connected", total=len(ws_clients))
    try:
        # Send initial snapshot
        data = get_all_current_data()
        await ws.send_text(json.dumps({"type": "snapshot", "data": data, "ts": time.time() * 1000}))
        # Keep connection alive, listen for client messages (e.g., ping)
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
        log.info("ws_client_disconnected", total=len(ws_clients))


@app.get("/")
async def root():
    return {
        "name": "Spread Dashboard API",
        "version": "0.1.0",
        "docs": "/docs",
    }
