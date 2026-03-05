"""
LIMIT-Only Sliced Execution Engine for Bybit V5 LINEAR perpetuals.

Splits a target order into N child LIMIT orders placed simultaneously.
Uses aggressive pricing (buy at ask, sell at bid) for fast fills.
Tracks progress via order-level polling and position reconciliation.
Cancels remaining orders when target is met or timeout is reached.

No Market orders — ever. Relies on BybitLinearClient which enforces
LIMIT-only at the API boundary.
"""
import asyncio
import time
import structlog
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from app.execution.maker_engine import (
    round_price_to_tick,
    round_qty_to_step,
    validate_qty,
    compute_book_metrics,
    FillRecord,
)

log = structlog.get_logger()


# ─── Configuration ────────────────────────────────────────────────

@dataclass
class SlicerConfig:
    """Configuration for the LIMIT slicer."""
    num_slices: int = 5                      # split into N orders
    poll_interval_s: float = 1.0             # check fill status every N seconds
    max_runtime_s: float = 60.0              # hard timeout
    price_offset_bps: int = 0                # extra aggressiveness beyond touch
    cancel_remaining_on_done: bool = True     # cancel unfilled when target met
    reduce_only: bool = False


# ─── Result ───────────────────────────────────────────────────────

@dataclass
class SlicerResult:
    """Result of a sliced execution."""
    status: str = "error"                    # done | partial | timeout | error
    target_qty: Decimal = Decimal("0")
    filled_qty: Decimal = Decimal("0")
    remaining_qty: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")        # VWAP
    num_slices_placed: int = 0
    num_slices_filled: int = 0
    num_cancelled: int = 0
    elapsed_ms: float = 0.0
    fills: List[FillRecord] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "target_qty": str(self.target_qty),
            "filled_qty": str(self.filled_qty),
            "remaining_qty": str(self.remaining_qty),
            "avg_price": str(self.avg_price),
            "num_slices_placed": self.num_slices_placed,
            "num_slices_filled": self.num_slices_filled,
            "num_cancelled": self.num_cancelled,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "detail": self.detail,
        }


# ─── Slice Computation ───────────────────────────────────────────

def compute_slices(
    target_qty: Decimal,
    num_slices: int,
    qty_step: Decimal,
    min_qty: Decimal,
) -> List[Decimal]:
    """Split target_qty into N slices, each rounded to qty_step.

    Last slice absorbs the remainder so total == target_qty.
    Slices below min_qty are merged into the last valid slice.
    """
    if num_slices <= 0:
        raise ValueError("num_slices must be > 0")

    base_qty = round_qty_to_step(target_qty / num_slices, qty_step)

    # If base is below min, reduce slice count
    if base_qty < min_qty:
        effective_slices = max(1, int(target_qty / min_qty))
        base_qty = round_qty_to_step(target_qty / effective_slices, qty_step)
        if base_qty < min_qty:
            base_qty = min_qty
        num_slices = effective_slices

    slices: List[Decimal] = []
    allocated = Decimal("0")

    for i in range(num_slices):
        if i < num_slices - 1:
            slices.append(base_qty)
            allocated += base_qty
        else:
            # Last slice gets the remainder
            remainder = round_qty_to_step(target_qty - allocated, qty_step)
            if remainder < min_qty:
                # Merge into previous slice if possible
                if slices:
                    slices[-1] += remainder
                else:
                    slices.append(target_qty)
            else:
                slices.append(remainder)

    return slices


def compute_aggressive_price(
    side: str,
    book_metrics,
    tick_size: Decimal,
    offset_bps: int = 0,
) -> Decimal:
    """Compute aggressive limit price for fast fills.

    Buy: price at best_ask (crosses spread for immediate fill)
    Sell: price at best_bid (crosses spread for immediate fill)

    offset_bps adds extra ticks of aggressiveness beyond the touch.
    """
    if side == "Buy":
        base_price = book_metrics.best_ask
        if offset_bps > 0:
            offset = base_price * Decimal(offset_bps) / Decimal("10000")
            base_price += offset
        return round_price_to_tick(base_price, tick_size, "Buy")
    else:
        base_price = book_metrics.best_bid
        if offset_bps > 0:
            offset = base_price * Decimal(offset_bps) / Decimal("10000")
            base_price -= offset
        return round_price_to_tick(base_price, tick_size, "Sell")


# ─── Order Tracking ──────────────────────────────────────────────

@dataclass
class _SliceOrder:
    """Internal state for a single slice order."""
    idx: int
    order_id: str
    qty: Decimal
    price: Decimal
    filled_qty: Decimal = Decimal("0")
    status: str = "New"   # New | PartiallyFilled | Filled | Cancelled


# ─── Main Executor ────────────────────────────────────────────────

async def execute_linear_limit_sliced(
    client,
    symbol: str,
    side: str,
    target_qty: Decimal,
    config: SlicerConfig,
) -> SlicerResult:
    """Execute a LIMIT-only sliced order.

    1. Fetch instrument info + orderbook
    2. Compute slice quantities + aggressive price
    3. Place all slices as LIMIT orders
    4. Poll for fills until target met or timeout
    5. Cancel remaining unfilled orders
    6. Return result with VWAP and fill details

    Args:
        client: BybitLinearClient instance
        symbol: e.g. "BTCUSDT"
        side: "Buy" or "Sell"
        target_qty: total quantity to execute
        config: SlicerConfig parameters

    Returns:
        SlicerResult with fill details and status
    """
    t_start = time.time()
    result = SlicerResult(
        target_qty=target_qty,
        remaining_qty=target_qty,
    )

    try:
        # ═══ 1. Fetch instrument info ═══
        inst = await client.get_instrument_info(symbol)
        tick_size = inst["tick_size"]
        qty_step = inst["qty_step"]
        min_qty = inst["min_qty"]
        max_qty = inst["max_qty"]

        # Validate target qty
        target_qty = round_qty_to_step(target_qty, qty_step)
        validate_qty(target_qty, min_qty, max_qty)
        result.target_qty = target_qty

        # ═══ 2. Compute slices ═══
        slice_qtys = compute_slices(target_qty, config.num_slices, qty_step, min_qty)

        log.info(
            "slicer_start",
            symbol=symbol, side=side,
            target_qty=str(target_qty),
            num_slices=len(slice_qtys),
            slice_qtys=[str(q) for q in slice_qtys],
        )

        # ═══ 3. Fetch orderbook + compute price ═══
        ob = await client.get_orderbook(symbol)
        book = compute_book_metrics(ob)
        price = compute_aggressive_price(side, book, tick_size, config.price_offset_bps)

        log.info(
            "slicer_price",
            side=side, price=str(price),
            best_bid=str(book.best_bid), best_ask=str(book.best_ask),
            offset_bps=config.price_offset_bps,
        )

        # ═══ 4. Place all slices ═══
        active_orders: List[_SliceOrder] = []

        for i, qty in enumerate(slice_qtys):
            try:
                resp = await client.place_limit_order(
                    symbol=symbol,
                    side=side,
                    qty=str(qty),
                    price=str(price),
                    time_in_force="GTC",
                    reduce_only=config.reduce_only,
                )
                order_id = resp["order_id"]
                active_orders.append(_SliceOrder(
                    idx=i,
                    order_id=order_id,
                    qty=qty,
                    price=price,
                ))
                result.num_slices_placed += 1
                log.info("slicer_slice_placed", idx=i, order_id=order_id, qty=str(qty))
            except Exception as e:
                log.error("slicer_place_error", idx=i, qty=str(qty), error=str(e))

        if not active_orders:
            result.status = "error"
            result.detail = "Failed to place any slice orders"
            result.elapsed_ms = (time.time() - t_start) * 1000
            return result

        # ═══ 5. Poll loop — track fills ═══
        vwap_num = Decimal("0")  # sum(price * qty) for VWAP
        total_filled = Decimal("0")
        all_fills: List[FillRecord] = []

        while True:
            elapsed = time.time() - t_start

            # Timeout check
            if elapsed >= config.max_runtime_s:
                log.warning("slicer_timeout", elapsed_s=round(elapsed, 1))
                result.detail = f"Timeout after {config.max_runtime_s}s"
                break

            await asyncio.sleep(config.poll_interval_s)

            # Poll each active order
            all_done = True
            for order in active_orders:
                if order.status in ("Filled", "Cancelled"):
                    continue

                try:
                    status = await client.get_order_status(symbol, order.order_id)
                except Exception as e:
                    log.warning("slicer_poll_error", order_id=order.order_id, error=str(e))
                    all_done = False
                    continue

                new_filled = status["filled_qty"]
                if new_filled > order.filled_qty:
                    delta = new_filled - order.filled_qty
                    fill_price = status["avg_price"] if status["avg_price"] > 0 else order.price
                    all_fills.append(FillRecord(price=fill_price, qty=delta, ts=time.time()))
                    vwap_num += fill_price * delta
                    total_filled += delta
                    order.filled_qty = new_filled

                    log.info(
                        "slicer_fill",
                        order_id=order.order_id, idx=order.idx,
                        delta=str(delta), total_filled=str(total_filled),
                    )

                order.status = status["status"]
                if status["status"] not in ("Filled", "Cancelled"):
                    all_done = False

            # Check if target filled
            if total_filled >= target_qty:
                log.info("slicer_target_reached", filled=str(total_filled))
                break

            # All orders are terminal (filled or cancelled)
            if all_done:
                log.info("slicer_all_orders_terminal", filled=str(total_filled))
                break

        # ═══ 6. Cancel remaining unfilled orders ═══
        num_cancelled = 0
        if config.cancel_remaining_on_done:
            for order in active_orders:
                if order.status in ("Filled", "Cancelled"):
                    continue
                try:
                    await client.cancel_order(symbol, order.order_id)
                    order.status = "Cancelled"
                    num_cancelled += 1
                except Exception as e:
                    log.warning(
                        "slicer_cancel_error",
                        order_id=order.order_id, error=str(e),
                    )

        # ═══ 7. Final reconciliation ═══
        # One last poll to catch fills between last check and cancel
        for order in active_orders:
            if order.status == "Filled":
                continue
            try:
                status = await client.get_order_status(symbol, order.order_id)
                if status["filled_qty"] > order.filled_qty:
                    delta = status["filled_qty"] - order.filled_qty
                    fill_price = status["avg_price"] if status["avg_price"] > 0 else order.price
                    all_fills.append(FillRecord(price=fill_price, qty=delta, ts=time.time()))
                    vwap_num += fill_price * delta
                    total_filled += delta
                    order.filled_qty = status["filled_qty"]
            except Exception:
                pass

        # ═══ 8. Build result ═══
        remaining = target_qty - total_filled
        num_slices_filled = sum(1 for o in active_orders if o.filled_qty >= o.qty)

        result.filled_qty = total_filled
        result.remaining_qty = remaining
        result.num_slices_filled = num_slices_filled
        result.num_cancelled = num_cancelled
        result.fills = all_fills
        result.elapsed_ms = (time.time() - t_start) * 1000

        # VWAP
        if total_filled > 0 and vwap_num > 0:
            result.avg_price = vwap_num / total_filled

        # Status
        if total_filled >= target_qty:
            result.status = "done"
        elif (time.time() - t_start) >= config.max_runtime_s:
            result.status = "timeout"
            if total_filled > 0:
                result.status = "partial"
        elif total_filled > 0:
            result.status = "partial"
        else:
            result.status = "error"
            result.detail = result.detail or "No fills received"

        log.info(
            "slicer_result",
            status=result.status,
            filled=str(total_filled),
            remaining=str(remaining),
            avg_price=str(result.avg_price),
            slices_placed=result.num_slices_placed,
            slices_filled=num_slices_filled,
            cancelled=num_cancelled,
            elapsed_ms=round(result.elapsed_ms),
        )

        return result

    except Exception as e:
        result.status = "error"
        result.detail = str(e)
        result.elapsed_ms = (time.time() - t_start) * 1000
        log.error("slicer_error", error=str(e), elapsed_ms=round(result.elapsed_ms))
        return result
