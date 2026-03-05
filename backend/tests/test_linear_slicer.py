"""
Tests for LIMIT-only sliced execution engine.

Covers:
- BybitLinearClient LIMIT-only enforcement
- Slice computation (qty splitting, rounding, remainder)
- Aggressive price computation
- Full slicer execution (mock client)
- Cancel-on-complete behavior
- Timeout behavior
- Source audit: no Market orders in BybitLinearClient
"""
import asyncio
import inspect
import time
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.execution.bybit_linear_client import BybitLinearClient
from app.execution.linear_limit_slicer import (
    SlicerConfig,
    SlicerResult,
    compute_slices,
    compute_aggressive_price,
    execute_linear_limit_sliced,
)
from app.execution.maker_engine import (
    round_price_to_tick,
    round_qty_to_step,
    BookMetrics,
)


# ─── Fixtures / Helpers ──────────────────────────────────────────

DEFAULT_INSTRUMENT = {
    "tick_size": Decimal("0.01"),
    "qty_step": Decimal("0.001"),
    "min_qty": Decimal("0.001"),
    "max_qty": Decimal("100"),
}

DEFAULT_ORDERBOOK = {
    "bids": [["50000.00", "1.5"], ["49999.00", "2.0"]],
    "asks": [["50001.00", "1.0"], ["50002.00", "3.0"]],
    "ts": 1700000000000,
}

DEFAULT_POSITION_EMPTY = {
    "amount": Decimal("0"),
    "side": "None",
    "entry_price": Decimal("0"),
    "pnl": Decimal("0"),
    "leverage": Decimal("0"),
}


def _make_order_status(filled_qty: str = "0", total_qty: str = "0.01", status: str = "New"):
    """Helper to build a mock order status response."""
    filled = Decimal(filled_qty)
    total = Decimal(total_qty)
    return {
        "status": status,
        "filled_qty": filled,
        "avg_price": Decimal("50001.00") if filled > 0 else Decimal("0"),
        "remaining_qty": total - filled,
    }


def mock_linear_client(
    instrument=None,
    orderbook=None,
    position=None,
    order_status_fn=None,
):
    """Build a mock BybitLinearClient with configurable responses."""
    client = AsyncMock(spec=BybitLinearClient)

    client.get_instrument_info.return_value = instrument or DEFAULT_INSTRUMENT
    client.get_orderbook.return_value = orderbook or DEFAULT_ORDERBOOK
    client.get_position.return_value = position or DEFAULT_POSITION_EMPTY

    # Default: place_limit_order returns success with incrementing order IDs
    _order_counter = {"n": 0}

    async def _place_limit(*args, **kwargs):
        _order_counter["n"] += 1
        return {"order_id": f"order_{_order_counter['n']}", "status": "success"}

    client.place_limit_order.side_effect = _place_limit

    # Default: order status returns "Filled" immediately
    if order_status_fn:
        client.get_order_status.side_effect = order_status_fn
    else:
        client.get_order_status.return_value = _make_order_status(
            filled_qty="0.01", total_qty="0.01", status="Filled"
        )

    # Cancel returns success
    client.cancel_order.return_value = {"status": "cancelled", "order_id": "x"}
    client.cancel_all_orders.return_value = {"status": "cancelled", "count": 0}

    return client


# ═══════════════════════════════════════════════════════════════════
# 1. LIMIT-Only Enforcement
# ═══════════════════════════════════════════════════════════════════

class TestLimitOnlyEnforcement:
    """Verify BybitLinearClient enforces LIMIT-only at the API boundary."""

    def test_no_market_order_method_exists(self):
        """BybitLinearClient must not have a place_market_order method."""
        assert not hasattr(BybitLinearClient, "place_market_order"), \
            "BybitLinearClient must NOT have a place_market_order method"

    def test_source_has_no_market_order_type(self):
        """Scan BybitLinearClient source for orderType='Market' — must be 0 matches."""
        source = inspect.getsource(BybitLinearClient)
        assert 'orderType="Market"' not in source, \
            "BybitLinearClient source must not contain orderType='Market'"
        assert "orderType='Market'" not in source, \
            "BybitLinearClient source must not contain orderType='Market'"

    def test_source_hardcodes_limit_order_type(self):
        """Verify orderType='Limit' is hardcoded in the source."""
        source = inspect.getsource(BybitLinearClient)
        assert 'orderType="Limit"' in source, \
            "BybitLinearClient must hardcode orderType='Limit'"

    @pytest.mark.asyncio
    async def test_place_limit_order_requires_price(self):
        """place_limit_order must assert when price is None."""
        # We can't easily call the real method (needs pybit HTTP),
        # but we can verify the assert exists in source.
        source = inspect.getsource(BybitLinearClient.place_limit_order)
        assert "assert price is not None" in source

    @pytest.mark.asyncio
    async def test_place_limit_order_rejects_empty_price(self):
        """place_limit_order must assert when price is empty string."""
        source = inspect.getsource(BybitLinearClient.place_limit_order)
        assert 'assert price != ""' in source


# ═══════════════════════════════════════════════════════════════════
# 2. Slice Computation
# ═══════════════════════════════════════════════════════════════════

class TestSliceComputation:
    """Test slice qty splitting and rounding."""

    def test_even_split(self):
        """5 slices of 0.05 → 5 x 0.01."""
        slices = compute_slices(
            target_qty=Decimal("0.05"),
            num_slices=5,
            qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
        )
        assert len(slices) == 5
        assert all(s == Decimal("0.01") for s in slices)
        assert sum(slices) == Decimal("0.05")

    def test_remainder_in_last_slice(self):
        """0.05 / 3 = 0.016... → first 2 get 0.016, last gets remainder."""
        slices = compute_slices(
            target_qty=Decimal("0.05"),
            num_slices=3,
            qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
        )
        assert len(slices) == 3
        # First 2 slices: floor(0.05/3 / 0.001) * 0.001 = 0.016
        assert slices[0] == Decimal("0.016")
        assert slices[1] == Decimal("0.016")
        # Last slice gets remainder: 0.05 - 0.032 = 0.018
        assert slices[2] == Decimal("0.018")
        assert sum(slices) == Decimal("0.05")

    def test_single_slice(self):
        """1 slice == entire target qty."""
        slices = compute_slices(
            target_qty=Decimal("0.1"),
            num_slices=1,
            qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
        )
        assert len(slices) == 1
        assert slices[0] == Decimal("0.1")

    def test_slices_rounded_to_qty_step(self):
        """All slices must be multiples of qty_step."""
        slices = compute_slices(
            target_qty=Decimal("0.1"),
            num_slices=7,
            qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
        )
        for s in slices:
            # s / qty_step should be an integer
            ratio = s / Decimal("0.001")
            assert ratio == int(ratio), f"Slice {s} is not a multiple of qty_step 0.001"

    def test_too_many_slices_auto_reduces(self):
        """If base_qty < min_qty, reduce effective slice count."""
        slices = compute_slices(
            target_qty=Decimal("0.003"),
            num_slices=10,
            qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
        )
        # Can't split 0.003 into 10 slices of min 0.001 each
        # Should auto-reduce to 3 slices
        assert len(slices) == 3
        assert all(s >= Decimal("0.001") for s in slices)
        assert sum(slices) == Decimal("0.003")

    def test_larger_qty_step(self):
        """qty_step=0.01 with target=0.15, slices=4."""
        slices = compute_slices(
            target_qty=Decimal("0.15"),
            num_slices=4,
            qty_step=Decimal("0.01"),
            min_qty=Decimal("0.01"),
        )
        assert len(slices) == 4
        # floor(0.15/4 / 0.01) * 0.01 = floor(3.75) * 0.01 = 0.03
        assert slices[0] == Decimal("0.03")
        assert slices[1] == Decimal("0.03")
        assert slices[2] == Decimal("0.03")
        # remainder: 0.15 - 0.09 = 0.06
        assert slices[3] == Decimal("0.06")
        assert sum(slices) == Decimal("0.15")

    def test_invalid_num_slices(self):
        """num_slices <= 0 should raise."""
        with pytest.raises(ValueError):
            compute_slices(Decimal("0.05"), 0, Decimal("0.001"), Decimal("0.001"))


# ═══════════════════════════════════════════════════════════════════
# 3. Aggressive Price Computation
# ═══════════════════════════════════════════════════════════════════

class TestAggressivePrice:
    """Test aggressive limit price calculation."""

    def _book(self, bid="50000.00", ask="50001.00"):
        return BookMetrics(
            best_bid=Decimal(bid),
            best_ask=Decimal(ask),
            bid_size=Decimal("1.0"),
            ask_size=Decimal("1.0"),
            spread=Decimal(ask) - Decimal(bid),
            mid=(Decimal(bid) + Decimal(ask)) / 2,
            microprice=(Decimal(bid) + Decimal(ask)) / 2,
        )

    def test_buy_uses_ask(self):
        """Buy aggressive price = best_ask (crosses spread)."""
        book = self._book("50000.00", "50001.00")
        price = compute_aggressive_price("Buy", book, Decimal("0.01"), offset_bps=0)
        assert price == Decimal("50001.00")

    def test_sell_uses_bid(self):
        """Sell aggressive price = best_bid (crosses spread)."""
        book = self._book("50000.00", "50001.00")
        price = compute_aggressive_price("Sell", book, Decimal("0.01"), offset_bps=0)
        assert price == Decimal("50000.00")

    def test_buy_with_offset(self):
        """Buy with offset_bps > 0 adds aggressiveness."""
        book = self._book("50000.00", "50001.00")
        price = compute_aggressive_price("Buy", book, Decimal("0.01"), offset_bps=10)
        # 50001 + 50001*10/10000 = 50001 + 50.001 = 50051.001 → floor to 0.01 = 50051.00
        assert price > Decimal("50001.00")

    def test_sell_with_offset(self):
        """Sell with offset_bps > 0 subtracts for more aggressiveness."""
        book = self._book("50000.00", "50001.00")
        price = compute_aggressive_price("Sell", book, Decimal("0.01"), offset_bps=10)
        # 50000 - 50000*10/10000 = 50000 - 50 = 49950 → ceil to 0.01 = 49950.00
        assert price < Decimal("50000.00")

    def test_price_rounded_to_tick(self):
        """Price must be a multiple of tick_size."""
        book = self._book("50000.05", "50001.15")
        tick = Decimal("0.50")
        price = compute_aggressive_price("Buy", book, tick, offset_bps=0)
        # 50001.15 rounded down to tick 0.50 → 50001.00
        remainder = price % tick
        assert remainder == 0, f"Price {price} is not a multiple of tick {tick}"


# ═══════════════════════════════════════════════════════════════════
# 4. Full Slicer Execution
# ═══════════════════════════════════════════════════════════════════

class TestSlicerExecution:
    """Test execute_linear_limit_sliced with mock client."""

    @pytest.mark.asyncio
    async def test_all_slices_fill_immediately(self):
        """Happy path: all slices fill, status = 'done'."""
        client = mock_linear_client()
        config = SlicerConfig(num_slices=3, poll_interval_s=0.01, max_runtime_s=5.0)

        result = await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_qty=Decimal("0.03"),
            config=config,
        )

        assert result.status == "done"
        assert result.filled_qty >= Decimal("0.03")
        assert result.num_slices_placed == 3
        assert client.place_limit_order.call_count == 3

    @pytest.mark.asyncio
    async def test_cancel_on_complete(self):
        """Verify unfilled orders are cancelled when target is met."""
        call_count = {"n": 0}

        async def _order_status(symbol, order_id):
            call_count["n"] += 1
            # First 2 orders fill, third stays unfilled
            if order_id in ("order_1", "order_2"):
                return _make_order_status("0.01", "0.01", "Filled")
            return _make_order_status("0", "0.01", "New")

        client = mock_linear_client(order_status_fn=_order_status)
        config = SlicerConfig(
            num_slices=3,
            poll_interval_s=0.01,
            max_runtime_s=5.0,
            cancel_remaining_on_done=True,
        )

        result = await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_qty=Decimal("0.02"),
            config=config,
        )

        # Target was 0.02, first two orders filled 0.01 each = 0.02 total
        assert result.status == "done"
        assert result.filled_qty >= Decimal("0.02")
        # The third order should have been cancelled
        assert client.cancel_order.call_count >= 1

    @pytest.mark.asyncio
    async def test_timeout_returns_partial(self):
        """When timeout hits with partial fills, status = 'partial' or 'timeout'."""
        async def _never_fill(symbol, order_id):
            return _make_order_status("0", "0.01", "New")

        client = mock_linear_client(order_status_fn=_never_fill)
        config = SlicerConfig(
            num_slices=2,
            poll_interval_s=0.01,
            max_runtime_s=0.05,  # very short timeout
        )

        result = await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Sell",
            target_qty=Decimal("0.02"),
            config=config,
        )

        # Should timeout with no fills
        assert result.status in ("timeout", "error")
        assert result.filled_qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_partial_fill(self):
        """Some slices fill, some don't — status = 'partial'."""
        call_count = {"n": 0}

        async def _partial_fill(symbol, order_id):
            # Only order_1 fills
            if order_id == "order_1":
                return _make_order_status("0.01", "0.01", "Filled")
            return _make_order_status("0", "0.01", "Cancelled")

        client = mock_linear_client(order_status_fn=_partial_fill)
        config = SlicerConfig(
            num_slices=3,
            poll_interval_s=0.01,
            max_runtime_s=2.0,
        )

        result = await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_qty=Decimal("0.03"),
            config=config,
        )

        assert result.status == "partial"
        assert result.filled_qty == Decimal("0.01")
        assert result.remaining_qty == Decimal("0.02")

    @pytest.mark.asyncio
    async def test_place_failure_returns_error(self):
        """If all order placements fail, status = 'error'."""
        client = mock_linear_client()
        client.place_limit_order.side_effect = Exception("Connection refused")

        config = SlicerConfig(num_slices=2, poll_interval_s=0.01, max_runtime_s=2.0)

        result = await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_qty=Decimal("0.02"),
            config=config,
        )

        assert result.status == "error"
        assert "Failed to place" in result.detail

    @pytest.mark.asyncio
    async def test_limit_order_always_has_price(self):
        """Verify every place_limit_order call includes a non-empty price."""
        client = mock_linear_client()
        config = SlicerConfig(num_slices=3, poll_interval_s=0.01, max_runtime_s=5.0)

        await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_qty=Decimal("0.03"),
            config=config,
        )

        for call in client.place_limit_order.call_args_list:
            kwargs = call.kwargs if call.kwargs else {}
            args = call.args if call.args else ()
            # price is the 4th positional arg or a keyword arg
            price = kwargs.get("price", args[3] if len(args) > 3 else None)
            assert price is not None, "place_limit_order called without price"
            assert price != "", "place_limit_order called with empty price"

    @pytest.mark.asyncio
    async def test_vwap_computation(self):
        """VWAP should be weighted average of fill prices."""
        fill_prices = iter([Decimal("50001.00"), Decimal("50003.00")])

        async def _varied_fills(symbol, order_id):
            p = next(fill_prices, Decimal("50001.00"))
            return {
                "status": "Filled",
                "filled_qty": Decimal("0.01"),
                "avg_price": p,
                "remaining_qty": Decimal("0"),
            }

        client = mock_linear_client(order_status_fn=_varied_fills)
        config = SlicerConfig(num_slices=2, poll_interval_s=0.01, max_runtime_s=5.0)

        result = await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Buy",
            target_qty=Decimal("0.02"),
            config=config,
        )

        assert result.status == "done"
        # VWAP = (50001*0.01 + 50003*0.01) / 0.02 = 50002.00
        assert result.avg_price == Decimal("50002.00")

    @pytest.mark.asyncio
    async def test_reduce_only_passed_through(self):
        """reduce_only flag is forwarded to place_limit_order."""
        client = mock_linear_client()
        config = SlicerConfig(
            num_slices=1,
            poll_interval_s=0.01,
            max_runtime_s=5.0,
            reduce_only=True,
        )

        await execute_linear_limit_sliced(
            client=client,
            symbol="BTCUSDT",
            side="Sell",
            target_qty=Decimal("0.01"),
            config=config,
        )

        call_kwargs = client.place_limit_order.call_args_list[0].kwargs
        assert call_kwargs.get("reduce_only") is True


# ═══════════════════════════════════════════════════════════════════
# 5. Source Audit
# ═══════════════════════════════════════════════════════════════════

class TestSourceAudit:
    """Audit BybitLinearClient and slicer source for safety."""

    def test_linear_client_no_market_in_full_source(self):
        """Full source scan of bybit_linear_client.py for 'Market'."""
        import app.execution.bybit_linear_client as mod
        source = inspect.getsource(mod)
        # "Market" should only appear in comments/docstrings, not in API calls
        # Check for the actual API parameter pattern
        assert 'orderType="Market"' not in source
        assert "orderType='Market'" not in source

    def test_slicer_no_market_in_source(self):
        """Full source scan of linear_limit_slicer.py for 'Market'."""
        import app.execution.linear_limit_slicer as mod
        source = inspect.getsource(mod)
        assert 'orderType="Market"' not in source
        assert "orderType='Market'" not in source
