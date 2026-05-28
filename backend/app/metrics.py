"""Prometheus metric registry for runtime observability."""
import os

from app.config import settings

try:
    from prometheus_client import Gauge, Histogram, Counter, Info, generate_latest, CONTENT_TYPE_LATEST
except ImportError:  # pragma: no cover - local dev can run without optional deps installed
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _NoopMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def set(self, *args, **kwargs):
            return None

        def inc(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

    Gauge = Histogram = Counter = Info = _NoopMetric

    def generate_latest():
        return b""


SPREAD_BPS = Gauge("spread_bps", "Current spread in bps", ["symbol", "type"])
POLL_CYCLE_DURATION = Histogram("poll_cycle_duration_seconds", "Poll cycle duration")
WS_CLIENTS = Gauge("ws_clients_connected", "WebSocket clients connected")
EXCHANGE_LATENCY = Histogram("exchange_api_latency_seconds", "Exchange API latency", ["exchange"])
EXECUTION_DURATION = Histogram("execution_duration_seconds", "Trade execution duration", ["strategy"])
CONSECUTIVE_ERRORS = Gauge("consecutive_poll_errors", "Consecutive poll errors")
TRADES_TOTAL = Counter("trades_total", "Total trades executed", ["symbol", "status"])
DB_SIZE_BYTES = Gauge("db_size_bytes", "SQLite database file size")
APP_INFO = Info("spread_dashboard", "Spread Dashboard application info")
APP_INFO.info({"version": "0.1.0"})


def update_db_size_metric() -> None:
    """Update DB size gauge from the configured SQLite file path."""
    try:
        if settings.db_path != ":memory:" and os.path.exists(settings.db_path):
            DB_SIZE_BYTES.set(os.path.getsize(settings.db_path))
    except Exception:
        pass
