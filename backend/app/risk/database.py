from __future__ import annotations

import json
import os
import time
from typing import Any

import aiosqlite

from app.config import settings

DB_PATH = settings.db_path
_MEMORY_URI = "file:risk_framework_memory?mode=memory&cache=shared"
_memory_anchor: aiosqlite.Connection | None = None


async def _connect() -> aiosqlite.Connection:
    global _memory_anchor
    if DB_PATH == ":memory:":
        if _memory_anchor is None:
            _memory_anchor = await aiosqlite.connect(_MEMORY_URI, uri=True)
            await _configure(_memory_anchor)
        db = await aiosqlite.connect(_MEMORY_URI, uri=True)
        await _configure(db)
        return db

    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    await _configure(db)
    return db


async def _configure(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA synchronous=NORMAL")
    db.row_factory = aiosqlite.Row


async def init_risk_db() -> None:
    db = await _connect()
    try:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS risk_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_ms REAL NOT NULL,
                decision_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL,
                exchange TEXT NOT NULL,
                order_type TEXT NOT NULL,
                source TEXT NOT NULL,
                reason TEXT NOT NULL,
                dry_run_mode INTEGER NOT NULL,
                kill_switch_active INTEGER NOT NULL,
                circuit_breaker_tripped INTEGER NOT NULL,
                cooldown_active INTEGER NOT NULL,
                positions_json TEXT NOT NULL,
                notional_exposure_usd REAL NOT NULL,
                order_rates_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_risk_audit_ts ON risk_audit(timestamp_ms DESC);
            CREATE INDEX IF NOT EXISTS idx_risk_audit_symbol ON risk_audit(symbol);
            CREATE INDEX IF NOT EXISTS idx_risk_audit_decision ON risk_audit(decision_type);

            CREATE TABLE IF NOT EXISTS risk_kill_switch_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                active INTEGER NOT NULL,
                reason TEXT NOT NULL,
                activation_ts REAL NOT NULL
            );
            """
        )
        await db.commit()
    finally:
        await db.close()


async def insert_audit_record(record: dict[str, Any]) -> None:
    order = record["order"]
    db = await _connect()
    try:
        await db.execute(
            """
            INSERT INTO risk_audit (
                timestamp_ms, decision_type, symbol, side, qty, price, exchange,
                order_type, source, reason, dry_run_mode, kill_switch_active,
                circuit_breaker_tripped, cooldown_active, positions_json,
                notional_exposure_usd, order_rates_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["timestamp_ms"],
                record["decision"],
                order["symbol"],
                order["side"],
                order["qty"],
                order.get("price"),
                order["exchange"],
                order["order_type"],
                order["source"],
                record["reason"],
                int(record["dry_run_mode"]),
                int(record["kill_switch_active"]),
                int(record["circuit_breaker_tripped"]),
                int(record["cooldown_active"]),
                json.dumps(record["positions"], separators=(",", ":")),
                record["notional_exposure_usd"],
                json.dumps(record["order_rates"], separators=(",", ":")),
                time.time(),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def query_audit_records(
    *,
    symbol: str | None = None,
    decision_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    filters: list[str] = []
    params: list[Any] = []
    if symbol:
        filters.append("symbol = ?")
        params.append(symbol)
    if decision_type:
        filters.append("decision_type = ?")
        params.append(decision_type)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    offset = (page - 1) * page_size
    db = await _connect()
    try:
        count_row = await db.execute_fetchall(f"SELECT COUNT(*) AS n FROM risk_audit {where}", params)
        rows = await db.execute_fetchall(
            f"""
            SELECT * FROM risk_audit
            {where}
            ORDER BY timestamp_ms DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )
    finally:
        await db.close()

    return {
        "items": [_row_to_audit_item(dict(row)) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": int(count_row[0]["n"]) if count_row else 0,
    }


async def set_kill_switch_state(active: bool, reason: str, activation_ts: float) -> None:
    db = await _connect()
    try:
        await db.execute(
            """
            INSERT INTO risk_kill_switch_state (id, active, reason, activation_ts)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                active = excluded.active,
                reason = excluded.reason,
                activation_ts = excluded.activation_ts
            """,
            (int(active), reason, activation_ts),
        )
        await db.commit()
    finally:
        await db.close()


async def get_kill_switch_state() -> dict[str, Any] | None:
    db = await _connect()
    try:
        rows = await db.execute_fetchall("SELECT active, reason, activation_ts FROM risk_kill_switch_state WHERE id = 1")
    finally:
        await db.close()
    if not rows:
        return None
    row = dict(rows[0])
    return {"active": bool(row["active"]), "reason": row["reason"], "activation_ts": row["activation_ts"]}


async def purge_old_audit_records(retention_days: int) -> None:
    cutoff = time.time() * 1000 - retention_days * 86_400_000
    db = await _connect()
    try:
        await db.execute("DELETE FROM risk_audit WHERE timestamp_ms < ?", (cutoff,))
        await db.commit()
    finally:
        await db.close()


def _row_to_audit_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "timestamp_ms": row["timestamp_ms"],
        "decision_type": row["decision_type"],
        "symbol": row["symbol"],
        "side": row["side"],
        "qty": row["qty"],
        "price": row["price"],
        "exchange": row["exchange"],
        "order_type": row["order_type"],
        "source": row["source"],
        "reason": row["reason"],
        "dry_run_mode": bool(row["dry_run_mode"]),
        "kill_switch_active": bool(row["kill_switch_active"]),
        "circuit_breaker_tripped": bool(row["circuit_breaker_tripped"]),
        "cooldown_active": bool(row["cooldown_active"]),
        "positions": json.loads(row["positions_json"] or "{}"),
        "notional_exposure_usd": row["notional_exposure_usd"],
        "order_rates": json.loads(row["order_rates_json"] or "{}"),
        "created_at": row["created_at"],
    }
