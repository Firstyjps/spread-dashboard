# file: backend/app/storage/database.py
import aiosqlite
import os
import time
import structlog
from app.config import settings
from app.models import NormalizedTick, FundingSnapshot, SpreadMetric, Alert

log = structlog.get_logger()

DB_PATH = settings.db_path


async def init_db():
    """Create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
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


async def insert_tick(tick: NormalizedTick):
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()


async def insert_spread(spread: SpreadMetric):
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()


async def insert_alert(alert: Alert):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO alerts (ts, alert_type, symbol, severity, message, value, threshold)
               VALUES (?,?,?,?,?,?,?)""",
            (alert.ts, alert.alert_type, alert.symbol, alert.severity,
             alert.message, alert.value, alert.threshold),
        )
        await db.commit()


async def get_recent_spreads(symbol: str, limit: int = 500):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM spread_metrics
               WHERE symbol = ? ORDER BY ts DESC LIMIT ?""",
            (symbol, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]


async def get_spreads_by_time(symbol: str, minutes: int = 5):
    """Get spread data for the last N minutes."""
    since_ts = (time.time() - minutes * 60) * 1000
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM spread_metrics
               WHERE symbol = ? AND ts > ? ORDER BY ts ASC""",
            (symbol, since_ts),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_recent_alerts(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
