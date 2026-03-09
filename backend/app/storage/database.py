# file: backend/app/storage/database.py
"""
SQLite storage with persistent connection, WAL mode, and busy timeout.
Single connection reused across all operations — no per-call overhead.
"""
import aiosqlite
import os
import time
import structlog
from typing import Optional
from app.config import settings
from app.models import NormalizedTick, FundingSnapshot, SpreadMetric, Alert

log = structlog.get_logger()

DB_PATH = settings.db_path

# ─── Persistent connection ───────────────────────────────────────
_db: Optional[aiosqlite.Connection] = None


async def _get_db() -> aiosqlite.Connection:
    """Get or create the persistent DB connection with WAL + busy_timeout."""
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH)
        # WAL mode: readers never block writers, writers never block readers
        await _db.execute("PRAGMA journal_mode=WAL")
        # Wait up to 5s if DB is locked (instead of instant SQLITE_BUSY)
        await _db.execute("PRAGMA busy_timeout=5000")
        # Faster writes: OS handles fsync (safe with WAL + battery/UPS)
        await _db.execute("PRAGMA synchronous=NORMAL")
        # Limit WAL file size to ~32MB
        await _db.execute("PRAGMA wal_autocheckpoint=1000")
        log.info("db_connection_opened", path=DB_PATH, mode="WAL")
    return _db


async def close_db():
    """Close the persistent connection. Call on shutdown."""
    global _db
    if _db is not None:
        try:
            await _db.close()
        except Exception as e:
            log.warning("db_close_error", error=str(e))
        _db = None
        log.info("db_connection_closed")


async def init_db():
    """Create tables if they don't exist."""
    db = await _get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            market_type TEXT NOT NULL,
            bid REAL NOT NULL,
            ask REAL NOT NULL,
            bid_size REAL,
            ask_size REAL,
            mid REAL NOT NULL,
            last_price REAL,
            mark_price REAL,
            index_price REAL,
            volume_24h REAL,
            open_interest REAL,
            received_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ticks_lookup
            ON ticks(exchange, symbol, ts);

        CREATE TABLE IF NOT EXISTS funding_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            funding_rate REAL NOT NULL,
            predicted_rate REAL,
            next_funding_time REAL,
            funding_interval_hours REAL,
            annualized_rate REAL
        );
        CREATE INDEX IF NOT EXISTS idx_funding_lookup
            ON funding_snapshots(exchange, symbol, ts);

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
            exchange_spread_mid REAL NOT NULL,
            long_spread REAL NOT NULL,
            short_spread REAL NOT NULL,
            bid_ask_spread_bybit REAL NOT NULL,
            bid_ask_spread_lighter REAL NOT NULL,
            funding_diff REAL,
            received_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spread_lookup
            ON spread_metrics(symbol, ts);

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            alert_type TEXT NOT NULL,
            symbol TEXT,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            value REAL,
            threshold REAL,
            acknowledged INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts DESC);
    """)
    await db.commit()

    # Migration: add new columns if they don't exist (safe for existing DBs)
    for col, col_type in [("basis_bybit", "REAL"), ("basis_bybit_bps", "REAL")]:
        try:
            await db.execute(f"ALTER TABLE spread_metrics ADD COLUMN {col} {col_type}")
            await db.commit()
            log.info("db_column_added", table="spread_metrics", column=col)
        except Exception:
            pass  # Column already exists

    log.info("database_initialized", path=DB_PATH)


# ─── Insert operations ──────────────────────────────────────────

async def insert_tick(tick: NormalizedTick):
    db = await _get_db()
    await db.execute(
        """INSERT INTO ticks
           (ts, exchange, symbol, market_type, bid, ask, bid_size, ask_size,
            mid, last_price, mark_price, index_price, volume_24h,
            open_interest, received_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tick.ts, tick.exchange, tick.symbol, tick.market_type,
         tick.bid, tick.ask, tick.bid_size, tick.ask_size,
         tick.mid, tick.last_price, tick.mark_price, tick.index_price,
         tick.volume_24h, tick.open_interest, tick.received_at),
    )



async def insert_spread(spread: SpreadMetric):
    db = await _get_db()
    await db.execute(
        """INSERT INTO spread_metrics
           (ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
            lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
            short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
            basis_bybit, basis_bybit_bps, funding_diff, received_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (spread.ts, spread.symbol, spread.bybit_mid, spread.lighter_mid,
         spread.bybit_bid, spread.bybit_ask, spread.lighter_bid,
         spread.lighter_ask, spread.exchange_spread_mid, spread.long_spread,
         spread.short_spread, spread.bid_ask_spread_bybit,
         spread.bid_ask_spread_lighter, spread.basis_bybit,
         spread.basis_bybit_bps, spread.funding_diff,
         spread.received_at),
    )


async def insert_alert(alert: Alert):
    db = await _get_db()
    await db.execute(
        """INSERT INTO alerts (ts, alert_type, symbol, severity, message, value, threshold)
           VALUES (?,?,?,?,?,?,?)""",
        (alert.ts, alert.alert_type, alert.symbol, alert.severity,
         alert.message, alert.value, alert.threshold),
    )


async def commit():
    """Explicit commit. Call after a batch of inserts."""
    db = await _get_db()
    await db.commit()


# ─── Query operations ───────────────────────────────────────────

async def get_recent_spreads(symbol: str, limit: int = 500):
    db = await _get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        """SELECT id, ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
                  lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
                  short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
                  basis_bybit, basis_bybit_bps, funding_diff, received_at
           FROM spread_metrics
           WHERE symbol = ? ORDER BY ts DESC LIMIT ?""",
        (symbol, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]


async def get_spreads_by_time(symbol: str, minutes: int = 5, max_rows: int = 50000):
    """Get spread data for the last N minutes (downsampled to max_rows)."""
    since_ts = (time.time() - minutes * 60) * 1000
    db = await _get_db()
    db.row_factory = aiosqlite.Row

    # Count total rows first to decide if downsampling is needed
    cnt_cursor = await db.execute(
        "SELECT COUNT(*) FROM spread_metrics WHERE symbol = ? AND ts > ?",
        (symbol, since_ts),
    )
    total = (await cnt_cursor.fetchone())[0]

    if total <= max_rows:
        # No downsampling needed
        cursor = await db.execute(
            """SELECT id, ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
                      lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
                      short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
                      basis_bybit, basis_bybit_bps, funding_diff, received_at
               FROM spread_metrics
               WHERE symbol = ? AND ts > ? ORDER BY ts ASC""",
            (symbol, since_ts),
        )
    else:
        # Downsample: take every Nth row using rowid modulo
        step = total // max_rows + 1
        cursor = await db.execute(
            """SELECT id, ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
                      lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
                      short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
                      basis_bybit, basis_bybit_bps, funding_diff, received_at
               FROM spread_metrics
               WHERE symbol = ? AND ts > ? AND (id % ?) = 0
               ORDER BY ts ASC""",
            (symbol, since_ts, step),
        )

    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_recent_alerts(limit: int = 50):
    db = await _get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        """SELECT id, ts, alert_type, symbol, severity, message, value,
                  threshold, acknowledged
           FROM alerts ORDER BY ts DESC LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ─── Maintenance ─────────────────────────────────────────────────

async def cleanup_old_data(days: int = 7) -> int:
    """Delete data older than N days to prevent unbounded DB growth.
    Returns total number of rows deleted. Never crashes — best-effort only."""
    try:
        cutoff_ts = (time.time() - days * 86400) * 1000  # ms
        total_deleted = 0
        db = await _get_db()
        for table in ["ticks", "spread_metrics", "funding_snapshots", "alerts"]:
            try:
                cursor = await db.execute(
                    f"DELETE FROM {table} WHERE ts < ?", (cutoff_ts,)
                )
                total_deleted += cursor.rowcount
            except Exception as e:
                log.warning("db_cleanup_table_error", table=table, error=str(e))
        await db.commit()
        log.info("db_cleanup_complete", days=days, rows_deleted=total_deleted)
        return total_deleted
    except Exception as e:
        log.warning("db_cleanup_failed", error=str(e))
        return 0
