from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.services.executor as executor_mod
from app.execution.maker_engine import MakerResult
from app.services.circuit_breaker import circuit_breaker


def _config(min_fill_pct: float = 10.0):
    return SimpleNamespace(
        lighter_aliases={},
        arb_maker_only=True,
        arb_min_fill_pct=min_fill_pct,
        maker_allow_market_fallback=True,
        maker_max_time_s=1.0,
        maker_reprice_interval_ms=10,
        maker_max_reprices=1,
        maker_aggressiveness="BALANCED",
        maker_fee_rate=0.0002,
        taker_fee_rate=0.00055,
        maker_spread_guard_ticks=1,
        maker_vol_window=20,
        maker_vol_limit_ticks=10,
        maker_max_deviation_ticks=50,
    )


def _maker_result(status="filled", filled="1", avg_price="100", detail="ok"):
    filled_qty = Decimal(filled)
    return MakerResult(
        status=status,
        filled_qty=filled_qty,
        remaining_qty=Decimal("0"),
        avg_price=Decimal(avg_price),
        estimated_fee=filled_qty * Decimal(avg_price) * Decimal("0.0002"),
        detail=detail,
    )


@pytest.fixture
def executor_harness(monkeypatch):
    circuit_breaker.reset()
    trades = []
    created = {}

    class MockBybitClient:
        next_position = {"amount": 0.0, "is_long": True}

        def __init__(self, _config):
            self.market_orders = []
            self.closed = False
            created["bybit"] = self

        async def place_market_order(self, symbol, amount, side, reduce_only=False):
            self.market_orders.append({
                "symbol": symbol,
                "amount": amount,
                "side": side,
                "reduce_only": reduce_only,
            })
            return {"status": "success", "order_id": "bybit-1"}

        async def get_position(self, symbol):
            return dict(self.next_position)

        async def close(self):
            self.closed = True

    class MockLighterClient:
        next_position = {"amount": 0.0, "is_long": True}
        fail_orders = False
        preflight_error = None

        def __init__(self, _config):
            self.market_orders = []
            self.closed = False
            created["lighter"] = self

        def check_trading_ready(self):
            return self.preflight_error

        async def place_market_order(self, symbol, amount, is_ask, reduce_only=False):
            self.market_orders.append({
                "symbol": symbol,
                "amount": amount,
                "is_ask": is_ask,
                "reduce_only": reduce_only,
            })
            if self.fail_orders:
                raise RuntimeError("lighter rejected")
            return {"status": "success", "tx_hash": "lighter-1"}

        async def get_position(self, symbol):
            return dict(self.next_position)

        async def close(self):
            self.closed = True

    async def fake_record_trade(trade):
        trades.append(trade)

    async def fake_system_alert(*_args, **_kwargs):
        return True

    monkeypatch.setattr(executor_mod, "BybitClient", MockBybitClient)
    monkeypatch.setattr(executor_mod, "LighterClient", MockLighterClient)
    monkeypatch.setattr(executor_mod, "record_trade", fake_record_trade)
    monkeypatch.setattr(executor_mod, "send_system_alert", fake_system_alert)
    monkeypatch.setattr(executor_mod, "compute_spread", lambda _symbol: None)
    MockLighterClient.fail_orders = False
    MockLighterClient.preflight_error = None

    yield created, trades, MockBybitClient, MockLighterClient
    circuit_breaker.reset()


@pytest.mark.asyncio
async def test_arb_success(monkeypatch, executor_harness):
    created, trades, _, _ = executor_harness

    async def fake_maker(**_kwargs):
        return _maker_result(status="filled", filled="1")

    monkeypatch.setattr(executor_mod, "smart_execute_maker", fake_maker)

    executor = executor_mod.ArbitrageExecutor(_config())
    lighter_res, bybit_res = await executor.run_arb("XAUTUSDT", "BUY_LIGHTER_SELL_BYBIT", 1.0)

    assert lighter_res["status"] == "success"
    assert bybit_res.status == "filled"
    assert created["lighter"].market_orders == [{
        "symbol": "XAUTUSDT",
        "amount": 1.0,
        "is_ask": False,
        "reduce_only": False,
    }]
    assert trades[-1].status == "success"
    assert trades[-1].qty_filled == 1.0


@pytest.mark.asyncio
async def test_arb_bybit_aborted(monkeypatch, executor_harness):
    created, trades, _, _ = executor_harness

    async def fake_maker(**_kwargs):
        return _maker_result(status="aborted", filled="0", detail="post only rejected")

    monkeypatch.setattr(executor_mod, "smart_execute_maker", fake_maker)

    executor = executor_mod.ArbitrageExecutor(_config())
    lighter_res, bybit_res = await executor.run_arb("XAUTUSDT", "BUY_LIGHTER_SELL_BYBIT", 1.0)

    assert lighter_res is None
    assert bybit_res.status == "aborted"
    assert created["lighter"].market_orders == []
    assert trades[-1].status == "aborted"


@pytest.mark.asyncio
async def test_arb_lighter_preflight_failure_aborts_before_bybit(monkeypatch, executor_harness):
    created, trades, _, MockLighterClient = executor_harness
    MockLighterClient.preflight_error = "Lighter API private key does not match registered key"

    async def fake_maker(**_kwargs):
        raise AssertionError("Bybit maker should not run when Lighter preflight fails")

    monkeypatch.setattr(executor_mod, "smart_execute_maker", fake_maker)

    executor = executor_mod.ArbitrageExecutor(_config())
    lighter_res, bybit_res = await executor.run_arb("XAUTUSDT", "BUY_LIGHTER_SELL_BYBIT", 1.0)

    assert lighter_res is None
    assert bybit_res.status == "aborted"
    assert bybit_res.filled_qty == Decimal("0")
    assert created["lighter"].market_orders == []
    assert created["bybit"].market_orders == []
    assert trades[-1].status == "aborted"
    assert "Lighter API private key" in trades[-1].detail


@pytest.mark.asyncio
async def test_arb_below_threshold_reversal(monkeypatch, executor_harness):
    created, trades, _, _ = executor_harness

    async def fake_maker(**_kwargs):
        return _maker_result(status="partial", filled="0.05")

    monkeypatch.setattr(executor_mod, "smart_execute_maker", fake_maker)

    executor = executor_mod.ArbitrageExecutor(_config(min_fill_pct=10.0))
    lighter_res, bybit_res = await executor.run_arb("XAUTUSDT", "BUY_LIGHTER_SELL_BYBIT", 1.0)

    assert lighter_res is None
    assert bybit_res.status == "partial"
    assert created["lighter"].market_orders == []
    assert created["bybit"].market_orders[-1]["side"] == "Buy"
    assert created["bybit"].market_orders[-1]["reduce_only"] is True
    assert trades[-1].status == "reversed"


@pytest.mark.asyncio
async def test_arb_lighter_failure_reverses_bybit(monkeypatch, executor_harness):
    created, trades, _, MockLighterClient = executor_harness
    MockLighterClient.fail_orders = True

    async def fake_maker(**_kwargs):
        return _maker_result(status="filled", filled="1")

    monkeypatch.setattr(executor_mod, "smart_execute_maker", fake_maker)

    executor = executor_mod.ArbitrageExecutor(_config())
    with pytest.raises(Exception, match="Bybit position"):
        await executor.run_arb("XAUTUSDT", "BUY_LIGHTER_SELL_BYBIT", 1.0)

    assert created["bybit"].market_orders[-1]["side"] == "Buy"
    assert created["bybit"].market_orders[-1]["reduce_only"] is True
    assert trades[-1].status == "reversed"


@pytest.mark.asyncio
async def test_arb_below_lighter_min_reversal(monkeypatch, executor_harness):
    created, trades, _, _ = executor_harness
    monkeypatch.setitem(executor_mod.MARKET_META, "XAUTUSDT", {"min_base_amount": 0.5})

    async def fake_maker(**_kwargs):
        return _maker_result(status="filled", filled="0.1")

    monkeypatch.setattr(executor_mod, "smart_execute_maker", fake_maker)

    executor = executor_mod.ArbitrageExecutor(_config())
    lighter_res, _bybit_res = await executor.run_arb("XAUTUSDT", "BUY_LIGHTER_SELL_BYBIT", 1.0)

    assert lighter_res is None
    assert created["lighter"].market_orders == []
    assert created["bybit"].market_orders[-1]["reduce_only"] is True
    assert trades[-1].status == "reversed"


@pytest.mark.asyncio
async def test_emergency_close_auto(monkeypatch, executor_harness):
    created, trades, MockBybitClient, MockLighterClient = executor_harness
    MockBybitClient.next_position = {"amount": 1.0, "is_long": False}
    MockLighterClient.next_position = {"amount": 1.0, "is_long": True}

    executor = executor_mod.ArbitrageExecutor(_config())
    result = await executor.emergency_close_auto("XAUTUSDT")

    assert result["status"] == "success"
    assert created["lighter"].market_orders[-1]["reduce_only"] is True
    assert created["bybit"].market_orders[-1]["side"] == "Buy"
    assert trades[-1].strategy == "emergency_close"
    assert trades[-1].status == "success"


@pytest.mark.asyncio
async def test_emergency_close_no_positions(executor_harness):
    _created, trades, _, _ = executor_harness

    executor = executor_mod.ArbitrageExecutor(_config())
    result = await executor.emergency_close_auto("XAUTUSDT")

    assert result["status"] == "success"
    assert "No open positions" in result["detail"]
    assert trades[-1].status == "success"
    assert "No open positions" in trades[-1].detail


@pytest.mark.asyncio
async def test_context_manager_cleanup(executor_harness):
    cleanup_called = False
    executor = executor_mod.ArbitrageExecutor(_config())

    async def fake_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    executor._cleanup = fake_cleanup

    async with executor:
        pass

    assert cleanup_called is True
