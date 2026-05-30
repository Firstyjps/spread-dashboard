import time

import pytest

from app.analytics import spread_engine
from app.models import NormalizedTick
from app.risk import OrderRequest, RiskConfig, RiskEngine
from app.risk import database as risk_db


async def _seed_ticks(symbol: str = "XAUTUSDT", mid: float = 4500.0) -> None:
    spread_engine.latest_ticks.clear()
    now = time.time() * 1000
    await spread_engine.update_tick(
        NormalizedTick(
            ts=now,
            exchange="bybit",
            symbol=symbol,
            market_type="perp",
            bid=mid - 0.5,
            ask=mid + 0.5,
            mid=mid,
        )
    )
    await spread_engine.update_tick(
        NormalizedTick(
            ts=now,
            exchange="lighter",
            symbol=symbol,
            market_type="perp",
            bid=mid - 0.4,
            ask=mid + 0.4,
            mid=mid,
        )
    )


async def _engine(tmp_path, monkeypatch, config: RiskConfig | None = None) -> RiskEngine:
    monkeypatch.setattr(risk_db, "DB_PATH", str(tmp_path / "risk.db"))
    engine = RiskEngine(config or RiskConfig(price_data_max_age_s=60.0))
    await engine.initialize()
    return engine


def _order(**overrides) -> OrderRequest:
    values = {
        "symbol": "XAUTUSDT",
        "side": "Buy",
        "qty": 0.001,
        "price": None,
        "exchange": "bybit",
        "order_type": "test",
        "source": "pytest",
    }
    values.update(overrides)
    return OrderRequest(**values)


@pytest.mark.asyncio
async def test_dry_run_simulates_and_writes_audit(tmp_path, monkeypatch):
    engine = await _engine(tmp_path, monkeypatch)
    await _seed_ticks()

    decision = await engine.evaluate_order(_order())

    assert decision.decision == "simulate"
    assert decision.reason == "dry-run mode active"

    audit = await engine.audit.query(page_size=5)
    assert audit["total"] == 1
    assert audit["items"][0]["decision_type"] == "simulate"


@pytest.mark.asyncio
async def test_price_sanity_rejects_out_of_band_limit(tmp_path, monkeypatch):
    engine = await _engine(tmp_path, monkeypatch)
    await _seed_ticks(mid=4500.0)

    decision = await engine.evaluate_order(_order(price=5000.0, order_type="limit"))

    assert decision.decision == "reject"
    assert "price deviation" in decision.reason


@pytest.mark.asyncio
async def test_manual_kill_switch_blocks_orders(tmp_path, monkeypatch):
    engine = await _engine(tmp_path, monkeypatch)
    await _seed_ticks()

    await engine.activate_kill_switch("manual stop")
    decision = await engine.evaluate_order(_order())

    assert decision.decision == "reject"
    assert "kill switch active" in decision.reason


@pytest.mark.asyncio
async def test_audit_log_failure_does_not_block_decision(tmp_path, monkeypatch):
    engine = await _engine(tmp_path, monkeypatch)
    await _seed_ticks()

    async def fail_audit(_evaluation):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(engine.audit, "log", fail_audit)

    await engine.activate_kill_switch("manual stop")
    decision = await engine.evaluate_order(_order())

    assert decision.decision == "reject"
    assert "kill switch active" in decision.reason
    assert engine.snapshot().last_decision is not None
    assert engine.snapshot().last_decision["decision"] == "reject"


@pytest.mark.asyncio
async def test_live_rate_limit_queues_then_times_out(tmp_path, monkeypatch):
    engine = await _engine(
        tmp_path,
        monkeypatch,
        RiskConfig(
            dry_run_enabled=False,
            max_order_rate_per_minute=1,
            rate_limit_queue_timeout_s=0.01,
            price_data_max_age_s=60.0,
        ),
    )
    await _seed_ticks()

    first = await engine.evaluate_order(_order(qty=0.001))
    second = await engine.evaluate_order(_order(qty=0.001))

    assert first.decision == "approve"
    assert second.decision == "reject"
    assert "rate limit timeout" in second.reason


@pytest.mark.asyncio
async def test_position_cap_uses_gross_exchange_exposure(tmp_path, monkeypatch):
    engine = await _engine(
        tmp_path,
        monkeypatch,
        RiskConfig(
            dry_run_enabled=False,
            max_position_per_symbol=0.001,
            price_data_max_age_s=60.0,
        ),
    )
    await _seed_ticks()

    decision = await engine.evaluate_order(_order(qty=0.002))

    assert decision.decision == "reject"
    assert "gross position" in decision.reason
