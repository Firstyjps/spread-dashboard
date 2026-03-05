"""
Tests for Maker-Only Sliced Execution Engine.

Covers:
- BybitLinearMakerClient: PostOnly enforcement, no Market orders
- Maker pricing: BUY <= best_bid, SELL >= best_ask
- Slice qty computation and min constraint handling
- Full executor flow with mocked client
- Cancel-on-complete behavior
- PostOnly rejection + shift-away retry
- Maker/taker verification via execution records
- Source audit: no Market orders, PostOnly hardcoded
"""
import inspect
import time
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.exchanges.bybit_linear.client import BybitLinearMakerClient, PostOnlyRejectError
from app.exchanges.bybit_linear.instruments import InstrumentInfo
from app.execution.maker_slicer_linear import (
    ExecutionSummary,
    MakerFill,
    _compute_maker_price,
    _round_price,
    _round_qty,
    _shift_away,
    execute_linear_maker_sliced,
)


# ─── Fixtures / Helpers ──────────────────────────────────────────

DEFAULT_INSTRUMENT = InstrumentInfo(
    symbol="BTCUSDT",
    tick_size=Decimal("0.01"),
    qty_step=Decimal("0.001"),
    min_qty=Decimal("0.001"),
    max_qty=Decimal("100"),
    min_notional=Decimal("5"),
)

DEFAULT_ORDERBOOK = {
    "bids": [["50000.00", "1.5"], ["49999.00", "2.0"]],
    "asks": [["50001.00", "1.0"], ["50002.00", "3.0"]],
    "ts": 1700000000000,
}


def _make_order_status(
    filled_qty="0", total_qty="0.01", status="New", avg_price="0", cum_value="0"
):
    filled = Decimal(filled_qty)
    total = Decimal(total_qty)
    return {
        "status": status,
        "filled_qty": filled,
        "avg_price": Decimal(avg_price) if avg_price != "0" else Decimal("0"),
        "remaining_qty": total - filled,
        "cum_exec_value": Decimal(cum_value),
    }


def mock_maker_client(
    instrument=None,
    orderbook=None,
    order_status_fn=None,
    exec_records=None,
):
    """Build a mock BybitLinearMakerClient."""
    client = AsyncMock(spec=BybitLinearMakerClient)

    # Instrument info
    client.get_instrument_info.return_value = instrument or DEFAULT_INSTRUMENT

    # Orderbook
    client.get_orderbook.return_value = orderbook or DEFAULT_ORDERBOOK

    # Position (empty)
    client.get_position.return_value = {
        "amount": Decimal("0"), "side": "None",
        "entry_price": Decimal("0"), "unrealised_pnl": Decimal("0"),
    }

    # Place order: returns incrementing order IDs
    _counter = {"n": 0}

    async def _place(*args, **kwargs):
        _counter["n"] += 1
        return {"order_id": f"ord_{_counter['n']}", "status": "placed"}

    client.place_postonly_limit.side_effect = _place

    # Order status: immediate fill by default
    if order_status_fn:
        client.get_order_status.side_effect = order_status_fn
    else:
        client.get_order_status.return_value = _make_order_status(
            filled_qty="0.01", total_qty="0.01",
            status="Filled", avg_price="50000.00",
            cum_value="500.00",
        )

    # Cancel
    client.cancel_order.return_value = {"status": "cancelled", "order_id": "x"}
    client.cancel_all_orders.return_value = {"status": "cancelled", "count": 0}

    # Execution records (for maker/taker verification)
    if exec_records is not None:
        client.get_execution_records.return_value = exec_records
    else:
        client.get_execution_records.return_value = [
            {
                "exec_id": "exec_1",
                "order_id": "ord_1",
                "price": Decimal("50000.00"),
                "qty": Decimal("0.01"),
                "value": Decimal("500.00"),
                "fee": Decimal("0.10"),
                "fee_rate": "0.0002",
                "is_maker": True,
                "exec_type": "Trade",
                "exec_time": "1700000000000",
            }
        ]

    return client


# ═══════════════════════════════════════════════════════════════════
# 1. Source Audit — No Market Orders, PostOnly Hardcoded
# ═══════════════════════════════════════════════════════════════════

class TestSourceAudit:
    """Verify source code guarantees at the module level."""

    def test_client_no_place_market_order(self):
        """BybitLinearMakerClient must not have place_market_order."""
        assert not hasattr(BybitLinearMakerClient, "place_market_order")

    def test_client_no_market_ordertype_in_source(self):
        """Source must not contain orderType='Market'."""
        src = inspect.getsource(BybitLinearMakerClient)
        assert 'orderType="Market"' not in src
        assert "orderType='Market'" not in src

    def test_client_hardcodes_limit_ordertype(self):
        """Source must hardcode orderType='Limit'."""
        src = inspect.getsource(BybitLinearMakerClient)
        assert 'orderType="Limit"' in src

    def test_client_hardcodes_postonly(self):
        """Source must hardcode timeInForce='PostOnly'."""
        src = inspect.getsource(BybitLinearMakerClient)
        assert 'timeInForce="PostOnly"' in src

    def test_slicer_no_market_in_source(self):
        """Slicer source must not reference Market orders."""
        import app.execution.maker_slicer_linear as mod
        src = inspect.getsource(mod)
        assert 'orderType="Market"' not in src
        assert "orderType='Market'" not in src

    def test_client_has_postonly_reject_error(self):
        """PostOnlyRejectError must be defined."""
        assert issubclass(PostOnlyRejectError, Exception)


# ═══════════════════════════════════════════════════════════════════
# 2. Maker Pricing — BUY <= bid, SELL >= ask
# ═══════════════════════════════════════════════════════════════════

class TestMakerPricing:
    """Verify maker pricing rules: never cross the spread."""

    def test_buy_at_best_bid(self):
        """BUY maker price = best_bid."""
        price = _compute_maker_price(
            "Buy",
            best_bid=Decimal("50000.00"),
            best_ask=Decimal("50001.00"),
            tick=Decimal("0.01"),
        )
        assert price == Decimal("50000.00")

    def test_sell_at_best_ask(self):
        """SELL maker price = best_ask."""
        price = _compute_maker_price(
            "Sell",
            best_bid=Decimal("50000.00"),
            best_ask=Decimal("50001.00"),
            tick=Decimal("0.01"),
        )
        assert price == Decimal("50001.00")

    def test_buy_never_exceeds_bid(self):
        """BUY price must be <= best_bid, never >= best_ask."""
        price = _compute_maker_price(
            "Buy",
            best_bid=Decimal("3000.50"),
            best_ask=Decimal("3000.75"),
            tick=Decimal("0.25"),
        )
        assert price <= Decimal("3000.50")
        assert price < Decimal("3000.75")

    def test_sell_never_below_ask(self):
        """SELL price must be >= best_ask, never <= best_bid."""
        price = _compute_maker_price(
            "Sell",
            best_bid=Decimal("3000.50"),
            best_ask=Decimal("3000.75"),
            tick=Decimal("0.25"),
        )
        assert price >= Decimal("3000.75")
        assert price > Decimal("3000.50")

    def test_buy_rounded_to_tick(self):
        """BUY price must be a multiple of tick (floored)."""
        tick = Decimal("0.50")
        price = _compute_maker_price(
            "Buy",
            best_bid=Decimal("50000.73"),
            best_ask=Decimal("50001.00"),
            tick=tick,
        )
        assert price % tick == 0
        assert price <= Decimal("50000.73")

    def test_sell_rounded_to_tick(self):
        """SELL price must be a multiple of tick (ceiled)."""
        tick = Decimal("0.50")
        price = _compute_maker_price(
            "Sell",
            best_bid=Decimal("50000.00"),
            best_ask=Decimal("50000.23"),
            tick=tick,
        )
        assert price % tick == 0
        assert price >= Decimal("50000.23")

    def test_shift_away_buy_lowers_price(self):
        """Shifting BUY away moves price down (more passive)."""
        price = Decimal("50000.00")
        shifted = _shift_away(price, Decimal("0.01"), "Buy")
        assert shifted == Decimal("49999.99")
        assert shifted < price

    def test_shift_away_sell_raises_price(self):
        """Shifting SELL away moves price up (more passive)."""
        price = Decimal("50001.00")
        shifted = _shift_away(price, Decimal("0.01"), "Sell")
        assert shifted == Decimal("50001.01")
        assert shifted > price


# ═══════════════════════════════════════════════════════════════════
# 3. Qty / Price Rounding
# ═══════════════════════════════════════════════════════════════════

class TestRounding:
    """Verify tick and step rounding."""

    def test_round_qty_to_step(self):
        """Qty must be floored to step."""
        assert _round_qty(Decimal("0.0157"), Decimal("0.001")) == Decimal("0.015")

    def test_round_price_buy_floors(self):
        """BUY price rounds down (lower = safer for maker)."""
        assert _round_price(Decimal("50000.56"), Decimal("0.10"), "Buy") == Decimal("50000.50")

    def test_round_price_sell_ceils(self):
        """SELL price rounds up (higher = safer for maker)."""
        assert _round_price(Decimal("50000.51"), Decimal("0.10"), "Sell") == Decimal("50000.60")


# ═══════════════════════════════════════════════════════════════════
# 4. Full Executor Tests
# ═══════════════════════════════════════════════════════════════════

class TestMakerSlicerExecution:
    """Test execute_linear_maker_sliced with mock client."""

    @pytest.mark.asyncio
    async def test_happy_path_all_slices_fill(self):
        """All slices fill as maker, status='done'."""
        client = mock_maker_client()
        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=2,
            pace_ms=10,
            stale_ms=100,
            max_duration_s=5,
            tolerance_usd=2.0,
        )
        assert result.status == "done"
        assert result.filled_usd > 0
        assert result.slices_placed >= 1

    @pytest.mark.asyncio
    async def test_every_order_is_postonly_limit(self):
        """Every call to place_postonly_limit must have been made (not place_market)."""
        client = mock_maker_client()
        await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=2,
            pace_ms=10,
            stale_ms=100,
            max_duration_s=5,
        )
        # place_postonly_limit was called (not place_market_order)
        assert client.place_postonly_limit.call_count >= 1
        # No market order method should exist or be called
        assert not hasattr(client, "place_market_order") or \
               not getattr(client.place_market_order, "called", False)

    @pytest.mark.asyncio
    async def test_buy_price_never_exceeds_bid(self):
        """All BUY orders must have price <= best_bid."""
        client = mock_maker_client()
        await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=2,
            pace_ms=10,
            stale_ms=100,
            max_duration_s=5,
        )
        best_bid = Decimal("50000.00")
        for call in client.place_postonly_limit.call_args_list:
            price = Decimal(call.kwargs.get("price", call.args[3] if len(call.args) > 3 else "0"))
            assert price <= best_bid, \
                f"BUY price {price} exceeds best_bid {best_bid}"

    @pytest.mark.asyncio
    async def test_sell_price_never_below_ask(self):
        """All SELL orders must have price >= best_ask."""
        client = mock_maker_client()
        await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Sell",
            target_usd=100.0,
            slices=2,
            pace_ms=10,
            stale_ms=100,
            max_duration_s=5,
        )
        best_ask = Decimal("50001.00")
        for call in client.place_postonly_limit.call_args_list:
            price = Decimal(call.kwargs.get("price", call.args[3] if len(call.args) > 3 else "0"))
            assert price >= best_ask, \
                f"SELL price {price} below best_ask {best_ask}"

    @pytest.mark.asyncio
    async def test_cancel_all_on_completion(self):
        """When target is reached, cancel_all_orders must be called."""
        client = mock_maker_client()
        await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=2,
            pace_ms=10,
            stale_ms=100,
            max_duration_s=5,
        )
        client.cancel_all_orders.assert_called()

    @pytest.mark.asyncio
    async def test_timeout_returns_partial_or_timeout(self):
        """Timeout with no fills → 'timeout' or 'error' status."""
        async def _never_fill(sym, oid):
            return _make_order_status("0", "0.01", "New")

        client = mock_maker_client(order_status_fn=_never_fill)
        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=2,
            pace_ms=10,
            stale_ms=50,
            max_duration_s=0.15,  # very short timeout
        )
        assert result.status in ("timeout", "error", "partial")

    @pytest.mark.asyncio
    async def test_postonly_reject_shifts_price(self):
        """PostOnly rejection → shift price away and retry."""
        reject_count = {"n": 0}

        async def _reject_then_accept(*args, **kwargs):
            reject_count["n"] += 1
            if reject_count["n"] <= 1:
                raise PostOnlyRejectError("Would take liquidity")
            return {"order_id": "ord_retry", "status": "placed"}

        client = mock_maker_client()
        client.place_postonly_limit.side_effect = _reject_then_accept

        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=1,
            pace_ms=10,
            stale_ms=200,
            max_duration_s=5,
        )
        assert result.postonly_rejects >= 1

    @pytest.mark.asyncio
    async def test_stale_order_cancelled_and_repriced(self):
        """Stale (unfilled) orders are cancelled, not converted to taker."""
        poll_count = {"n": 0}

        async def _stay_new(sym, oid):
            poll_count["n"] += 1
            if poll_count["n"] > 5:
                # Eventually fill to end the test
                return _make_order_status("0.002", "0.002", "Filled", "50000.00", "100.00")
            return _make_order_status("0", "0.002", "New")

        client = mock_maker_client(order_status_fn=_stay_new)
        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=1,
            pace_ms=10,
            stale_ms=80,
            max_duration_s=5,
        )
        # Should have cancelled at least one stale order
        assert result.slices_cancelled >= 1 or result.reprice_count >= 1

    @pytest.mark.asyncio
    async def test_maker_verification_records_maker(self):
        """Execution records with is_maker=True are counted correctly."""
        client = mock_maker_client(exec_records=[
            {
                "exec_id": "e1", "order_id": "ord_1",
                "price": Decimal("50000"), "qty": Decimal("0.01"),
                "value": Decimal("500"), "fee": Decimal("0.1"),
                "fee_rate": "0.0002", "is_maker": True,
                "exec_type": "Trade", "exec_time": "123",
            }
        ])
        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=1,
            pace_ms=10,
            stale_ms=200,
            max_duration_s=5,
        )
        assert result.maker_fill_count >= 1
        assert result.taker_fill_count == 0

    @pytest.mark.asyncio
    async def test_taker_fill_logged_as_error(self):
        """If execution record says is_maker=False, it's flagged."""
        client = mock_maker_client(exec_records=[
            {
                "exec_id": "e1", "order_id": "ord_1",
                "price": Decimal("50000"), "qty": Decimal("0.01"),
                "value": Decimal("500"), "fee": Decimal("0.275"),
                "fee_rate": "0.00055", "is_maker": False,
                "exec_type": "Trade", "exec_time": "123",
            }
        ])
        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=100.0,
            slices=1,
            pace_ms=10,
            stale_ms=200,
            max_duration_s=5,
        )
        assert result.taker_fill_count >= 1

    @pytest.mark.asyncio
    async def test_order_payload_contains_required_fields(self):
        """Every placed order must have category=linear, orderType=Limit, PostOnly."""
        # We verify this at the source level since the mock skips pybit
        src = inspect.getsource(BybitLinearMakerClient.place_postonly_limit)
        assert 'category="linear"' in src
        assert 'orderType="Limit"' in src
        assert 'timeInForce="PostOnly"' in src

    @pytest.mark.asyncio
    async def test_min_notional_adjustment(self):
        """If slice_usd < min_notional, slices should be auto-adjusted."""
        # min_notional=5, target=10, slices=100 → slice_usd=0.1 < 5
        # Should auto-reduce slices to 2 (10/5)
        client = mock_maker_client()
        result = await execute_linear_maker_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_usd=10.0,
            slices=100,  # way too many
            pace_ms=10,
            stale_ms=200,
            max_duration_s=5,
        )
        # Should still work, not error out
        assert result.status in ("done", "partial")
        # Should have placed far fewer than 100 slices
        assert result.slices_placed < 100


# ═══════════════════════════════════════════════════════════════════
# 5. InstrumentInfo
# ═══════════════════════════════════════════════════════════════════

class TestInstrumentInfo:
    """Test InstrumentInfo dataclass."""

    def test_frozen(self):
        """InstrumentInfo should be immutable."""
        inst = DEFAULT_INSTRUMENT
        with pytest.raises(Exception):
            inst.tick_size = Decimal("1.0")  # type: ignore

    def test_has_min_notional(self):
        """InstrumentInfo must include min_notional."""
        assert hasattr(DEFAULT_INSTRUMENT, "min_notional")
        assert DEFAULT_INSTRUMENT.min_notional == Decimal("5")
