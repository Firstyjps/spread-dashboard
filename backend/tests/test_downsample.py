"""Tests for get_all_spreads python-stride downsample."""
import os
import asyncio
import pytest
import time

os.environ["DB_PATH"] = ":memory:"


@pytest.mark.asyncio
async def test_downsample_returns_at_most_max_rows(tmp_path):
    db_file = tmp_path / "test.db"
    os.environ["DB_PATH"] = str(db_file)
    # Re-import after env change
    from importlib import reload
    from app.config import settings as _s
    _s.db_path = str(db_file)
    from app.storage import database
    reload(database)

    await database.init_db()

    # Insert 12_345 fake rows for 'AAA' and 12_345 for 'BBB' interleaved
    db = await database._get_db()
    for i in range(12345):
        ts = float(1_700_000_000_000 + i * 1000)
        for sym in ("AAA", "BBB"):
            await db.execute(
                """INSERT INTO spread_metrics
                   (ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
                    lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
                    short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
                    received_at)
                   VALUES (?, ?, 1, 1, 1, 1, 1, 1, 0.001, 0.001, 0.001, 0.0, 0.0, ?)""",
                (ts, sym, ts),
            )
    await db.commit()

    rows_aaa = await database.get_all_spreads("AAA", max_rows=100)
    rows_bbb = await database.get_all_spreads("BBB", max_rows=100)

    # Both symbols should return ~100 rows (not 0 — interleaved IDs would break id%step)
    assert 80 <= len(rows_aaa) <= 100
    assert 80 <= len(rows_bbb) <= 100
    # Rows should only be the slim 4 cols
    assert set(rows_aaa[0].keys()) == {"ts", "exchange_spread_mid", "long_spread", "short_spread"}
    # ts should be monotonic
    ts_aaa = [r["ts"] for r in rows_aaa]
    assert ts_aaa == sorted(ts_aaa)
    await database.close_db()


@pytest.mark.asyncio
async def test_downsample_under_max_rows_returns_all(tmp_path):
    db_file = tmp_path / "test.db"
    os.environ["DB_PATH"] = str(db_file)
    from importlib import reload
    from app.config import settings as _s
    _s.db_path = str(db_file)
    from app.storage import database
    reload(database)

    await database.init_db()
    db = await database._get_db()
    for i in range(50):
        ts = float(1_700_000_000_000 + i * 1000)
        await db.execute(
            """INSERT INTO spread_metrics
               (ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
                lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
                short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
                received_at)
               VALUES (?, ?, 1, 1, 1, 1, 1, 1, 0.001, 0.001, 0.001, 0.0, 0.0, ?)""",
            (ts, "TEST", ts),
        )
    await db.commit()

    rows = await database.get_all_spreads("TEST", max_rows=5000)
    assert len(rows) == 50
    await database.close_db()
