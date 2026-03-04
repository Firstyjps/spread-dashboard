# file: backend/tests/test_database_batch.py
"""Tests for database batch commit behavior."""
import time
import pytest
import pytest_asyncio
import aiosqlite
from app.storage import database
from app.models import NormalizedTick, SpreadMetric, Alert


@pytest_asyncio.fixture
async def fresh_db(tmp_path):
    """Set up a fresh in-memory-like temp DB, tear down after test."""
    original_path = database.DB_PATH
    original_db = database._db
    database.DB_PATH = str(tmp_path / "test.db")
    database._db = None
    await database.init_db()
    yield
    await database.close_db()
    database.DB_PATH = original_path
    database._db = original_db


def _make_tick(exchange="bybit", symbol="BTCUSDT") -> NormalizedTick:
    now = time.time() * 1000
    return NormalizedTick(
        ts=now,
        exchange=exchange,
        symbol=symbol,
        market_type="linear",
        bid=100.0,
        ask=101.0,
        mid=100.5,
        received_at=now,
    )


def _make_spread(symbol="BTCUSDT") -> SpreadMetric:
    now = time.time() * 1000
    return SpreadMetric(
        ts=now,
        symbol=symbol,
        bybit_mid=100.5,
        lighter_mid=101.0,
        bybit_bid=100.0,
        bybit_ask=101.0,
        lighter_bid=100.5,
        lighter_ask=101.5,
        exchange_spread_mid=0.005,
        long_spread=0.005,
        short_spread=0.005,
        bid_ask_spread_bybit=0.01,
        bid_ask_spread_lighter=0.01,
        received_at=now,
    )


def _make_alert(symbol="BTCUSDT") -> Alert:
    return Alert(
        ts=time.time() * 1000,
        alert_type="spread_alert",
        symbol=symbol,
        severity="critical",
        message="test alert",
        value=10.0,
        threshold=9.0,
    )


@pytest.mark.asyncio
class TestBatchCommit:
    async def test_insert_tick_does_not_auto_commit(self, fresh_db):
        """insert_tick should NOT commit — data invisible via separate connection."""
        tick = _make_tick()
        await database.insert_tick(tick)

        # Open a separate connection to verify uncommitted data
        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM ticks")
            (count,) = await cursor.fetchone()
            assert count == 0, "insert_tick should not auto-commit"

    async def test_insert_spread_does_not_auto_commit(self, fresh_db):
        """insert_spread should NOT commit."""
        spread = _make_spread()
        await database.insert_spread(spread)

        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM spread_metrics")
            (count,) = await cursor.fetchone()
            assert count == 0, "insert_spread should not auto-commit"

    async def test_insert_alert_does_not_auto_commit(self, fresh_db):
        """insert_alert should NOT commit."""
        alert = _make_alert()
        await database.insert_alert(alert)

        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM alerts")
            (count,) = await cursor.fetchone()
            assert count == 0, "insert_alert should not auto-commit"

    async def test_commit_makes_data_visible(self, fresh_db):
        """After explicit commit(), data should be visible to other connections."""
        tick = _make_tick()
        spread = _make_spread()
        await database.insert_tick(tick)
        await database.insert_spread(spread)
        await database.commit()

        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM ticks")
            (tick_count,) = await cursor.fetchone()
            cursor = await db2.execute("SELECT COUNT(*) FROM spread_metrics")
            (spread_count,) = await cursor.fetchone()
            assert tick_count == 1
            assert spread_count == 1

    async def test_alert_commit_independent(self, fresh_db):
        """Alert insert + commit works independently from tick/spread batch."""
        alert = _make_alert()
        await database.insert_alert(alert)
        await database.commit()

        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM alerts")
            (count,) = await cursor.fetchone()
            assert count == 1

    async def test_multiple_inserts_single_commit(self, fresh_db):
        """Multiple inserts batched into a single commit."""
        for i in range(5):
            await database.insert_tick(_make_tick())
            await database.insert_spread(_make_spread())

        # Not committed yet
        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM ticks")
            (count,) = await cursor.fetchone()
            assert count == 0

        # Now commit
        await database.commit()

        async with aiosqlite.connect(database.DB_PATH) as db2:
            cursor = await db2.execute("SELECT COUNT(*) FROM ticks")
            (tick_count,) = await cursor.fetchone()
            cursor = await db2.execute("SELECT COUNT(*) FROM spread_metrics")
            (spread_count,) = await cursor.fetchone()
            assert tick_count == 5
            assert spread_count == 5
