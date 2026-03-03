"""
Synthetic Iceberg Executor for Bybit V5.

Bybit API does NOT expose icebergQty — we implement synthetic iceberg:
split a parent order into child GTC LIMIT orders, keep only N visible
at a time, replenish on fill, optionally chase price.

Uses GTC LIMIT (not PostOnly) — iceberg wants fills, just hides total size.
Uses amend_order for atomic repricing instead of cancel+replace.
"""
import asyncio
import enum
import time
import structlog
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

from app.execution.maker_engine import (
    round_price_to_tick,
    round_qty_to_step,
    validate_qty,
    compute_book_metrics,
    BookMetrics,
    FillRecord,
)
from app.execution.rate_limiter import TokenBucketRateLimiter

log = structlog.get_logger()


# ─── Enums ────────────────────────────────────────────────────────

class IcebergState(enum.Enum):
    IDLE = "IDLE"
    PLACING = "PLACING"
    WORKING = "WORKING"
    REPLENISH = "REPLENISH"
    DONE = "DONE"
    ABORTED = "ABORTED"


class PricePolicy(enum.Enum):
    PASSIVE = "PASSIVE"     # best bid (Buy) / best ask (Sell) — same side of book
    MID = "MID"             # midpoint between bid and ask
    CHASE = "CHASE"         # step ahead with bounded offset


class Urgency(enum.Enum):
    PASSIVE = "passive"
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"


# ─── Configuration ────────────────────────────────────────────────

@dataclass
class IcebergConfig:
    child_qty: Decimal                                    # visible size per child
    max_active_children: int = 1                          # simultaneous limit orders
    price_policy: PricePolicy = PricePolicy.PASSIVE
    urgency: Urgency = Urgency.NORMAL
    price_limit: Optional[Decimal] = None                 # hard guard price
    reduce_only: bool = False

    # Timing
    poll_interval_ms: int = 500                           # status check frequency
    cooldown_ms: int = 1500                               # min between amend/reprice
    max_runtime_s: float = 120.0                          # hard timeout

    # Safety
    reprice_threshold_bps: int = 5                        # only reprice if drift >= N bps
    max_cancels: int = 30                                 # budget for amend+cancel ops
    max_slippage_bps: int = 50                            # abort if VWAP too far from initial mid
    max_retries: int = 3                                  # per API request

    # Fees (for reporting)
    taker_fee_rate: float = 0.00055
    maker_fee_rate: float = 0.0002


# ─── State Tracking ───────────────────────────────────────────────

@dataclass
class ChildOrderState:
    """Tracks a single child order."""
    child_idx: int
    order_id: str
    order_link_id: str
    side: str
    price: Decimal
    qty: Decimal
    filled_qty: Decimal = Decimal("0")
    status: str = "New"                                   # New, PartiallyFilled, Filled, Cancelled
    placed_at: float = 0.0
    amend_count: int = 0


# ─── Result ───────────────────────────────────────────────────────

@dataclass
class IcebergResult:
    status: str                                           # done | partial | aborted | timeout
    parent_side: str = ""
    parent_qty: Decimal = Decimal("0")
    filled_qty: Decimal = Decimal("0")
    remaining_qty: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")                     # VWAP
    initial_mid: Decimal = Decimal("0")
    child_count: int = 0
    cancel_count: int = 0
    reprice_count: int = 0
    fill_count: int = 0
    time_elapsed_ms: float = 0.0
    estimated_fee: Decimal = Decimal("0")
    price_improvement_bps: float = 0.0
    fills: List[FillRecord] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "parent_side": self.parent_side,
            "parent_qty": str(self.parent_qty),
            "filled_qty": str(self.filled_qty),
            "remaining_qty": str(self.remaining_qty),
            "avg_price": str(self.avg_price),
            "initial_mid": str(self.initial_mid),
            "child_count": self.child_count,
            "cancel_count": self.cancel_count,
            "reprice_count": self.reprice_count,
            "fill_count": self.fill_count,
            "time_elapsed_ms": round(self.time_elapsed_ms, 1),
            "estimated_fee": str(self.estimated_fee),
            "price_improvement_bps": round(self.price_improvement_bps, 2),
            "detail": self.detail,
        }


# ─── Price Computation ────────────────────────────────────────────

_CHASE_OFFSET = {
    Urgency.PASSIVE: 0,
    Urgency.NORMAL: 1,
    Urgency.AGGRESSIVE: 2,
}


def compute_iceberg_price(
    side: str,
    book: BookMetrics,
    tick: Decimal,
    policy: PricePolicy,
    urgency: Urgency,
    price_limit: Optional[Decimal] = None,
) -> Decimal:
    """
    Compute limit price for an iceberg child.

    PASSIVE: best bid (Buy) / best ask (Sell) — rests on same side of book
    MID:     midpoint between bid and ask
    CHASE:   step ahead of best, bounded by price_limit
    """
    if side == "Buy":
        if policy == PricePolicy.PASSIVE:
            price = book.best_bid
        elif policy == PricePolicy.MID:
            price = (book.best_bid + book.best_ask) / 2
        else:  # CHASE
            price = book.best_bid + tick * _CHASE_OFFSET[urgency]
        if price_limit is not None:
            price = min(price, price_limit)
        return round_price_to_tick(price, tick, "Buy")
    else:
        if policy == PricePolicy.PASSIVE:
            price = book.best_ask
        elif policy == PricePolicy.MID:
            price = (book.best_bid + book.best_ask) / 2
        else:  # CHASE
            price = book.best_ask - tick * _CHASE_OFFSET[urgency]
        if price_limit is not None:
            price = max(price, price_limit)
        return round_price_to_tick(price, tick, "Sell")


def _should_reprice(
    current_price: Decimal,
    new_price: Decimal,
    mid: Decimal,
    threshold_bps: int,
) -> bool:
    """Only reprice if drift from current price exceeds threshold in bps."""
    if mid <= 0:
        return False
    drift_bps = abs(new_price - current_price) / mid * Decimal("10000")
    return drift_bps >= threshold_bps


def _check_price_limit_breached(
    side: str, book: BookMetrics, price_limit: Optional[Decimal]
) -> bool:
    """Return True if market has moved beyond price_limit."""
    if price_limit is None:
        return False
    if side == "Buy":
        return book.best_ask > price_limit
    else:
        return book.best_bid < price_limit


# ─── Helpers ──────────────────────────────────────────────────────

def _sum_active_unfilled(children: Dict[str, ChildOrderState]) -> Decimal:
    """Sum of unfilled qty across active children."""
    return sum((c.qty - c.filled_qty for c in children.values()), Decimal("0"))


async def _cancel_all_children(
    client,
    symbol: str,
    children: Dict[str, ChildOrderState],
    limiter: TokenBucketRateLimiter,
) -> int:
    """Best-effort cancel all active children. Returns number cancelled."""
    cancelled = 0
    for oid, child in list(children.items()):
        if child.status in ("Filled", "Cancelled"):
            continue
        try:
            async with limiter:
                await client.cancel_order(symbol, oid)
            cancelled += 1
        except Exception as e:
            log.warning("iceberg_cancel_failed", order_id=oid, error=str(e))
    return cancelled


# ─── Main Executor ────────────────────────────────────────────────

async def execute_iceberg(
    client,
    symbol: str,
    side: str,
    total_qty: Decimal,
    config: IcebergConfig,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
) -> IcebergResult:
    """
    Synthetic Iceberg Executor.

    Splits total_qty into child_qty-sized GTC LIMIT orders.
    Keeps max_active_children visible at a time.
    Replenishes as fills occur. Optionally reprices (chases) based on policy.

    State machine: IDLE → PLACING → WORKING → REPLENISH → DONE / ABORTED
    """
    t_start = time.time()
    limiter = rate_limiter or TokenBucketRateLimiter()
    result = IcebergResult(
        status="aborted", parent_side=side, parent_qty=total_qty,
        remaining_qty=total_qty,
    )

    parent_id = uuid4().hex[:12]
    child_idx_counter = 0
    active_children: Dict[str, ChildOrderState] = {}
    total_filled = Decimal("0")
    vwap_num = Decimal("0")           # sum(price * qty) for VWAP
    all_fills: List[FillRecord] = []
    total_cancel_count = 0
    total_reprice_count = 0
    last_reprice_mono = 0.0           # monotonic, for cooldown
    state = IcebergState.IDLE

    # Instrument info (set during IDLE)
    tick = Decimal("0")
    qty_step = Decimal("0")
    min_qty = Decimal("0")
    max_qty = Decimal("0")
    child_qty = Decimal("0")
    remaining = Decimal("0")
    book = None

    try:
        # ═══ IDLE — fetch instrument + orderbook ═══
        log.info("iceberg_start", symbol=symbol, side=side,
                 total_qty=str(total_qty), child_qty=str(config.child_qty),
                 policy=config.price_policy.value, urgency=config.urgency.value,
                 parent_id=parent_id)

        async with limiter:
            inst = await client.get_instrument_info(symbol)
        tick = inst["tick_size"]
        qty_step = inst["qty_step"]
        min_qty = inst["min_qty"]
        max_qty = inst["max_qty"]

        child_qty = round_qty_to_step(config.child_qty, qty_step)
        child_qty = validate_qty(child_qty, min_qty, max_qty)
        remaining = round_qty_to_step(total_qty, qty_step)
        validate_qty(remaining, min_qty, max_qty)

        async with limiter:
            ob = await client.get_orderbook(symbol)
        book = compute_book_metrics(ob)
        result.initial_mid = book.mid

        log.info("iceberg_book", bid=str(book.best_bid), ask=str(book.best_ask),
                 mid=str(book.mid), spread=str(book.spread))

        if _check_price_limit_breached(side, book, config.price_limit):
            result.detail = "Price limit already breached at start"
            log.warning("iceberg_price_limit_at_start")
            return result

        state = IcebergState.PLACING

        # ═══ MAIN LOOP ═══
        while state not in (IcebergState.DONE, IcebergState.ABORTED):
            elapsed = time.time() - t_start

            # — Hard timeout —
            if elapsed >= config.max_runtime_s:
                log.warning("iceberg_timeout", elapsed_s=round(elapsed, 1))
                n = await _cancel_all_children(client, symbol, active_children, limiter)
                total_cancel_count += n
                state = IcebergState.DONE
                result.detail = f"Max runtime {config.max_runtime_s}s exceeded"
                break

            # — Max cancels safety —
            if total_cancel_count >= config.max_cancels:
                log.error("iceberg_max_cancels_reached", count=total_cancel_count)
                n = await _cancel_all_children(client, symbol, active_children, limiter)
                total_cancel_count += n
                state = IcebergState.ABORTED
                result.detail = f"Max cancels ({config.max_cancels}) exceeded"
                break

            # ═══ PLACING ═══
            if state == IcebergState.PLACING:
                slots = config.max_active_children - len(active_children)
                unfilled_active = _sum_active_unfilled(active_children)

                for _ in range(slots):
                    this_qty = min(child_qty, remaining - unfilled_active)
                    this_qty = round_qty_to_step(this_qty, qty_step)
                    if this_qty < min_qty:
                        break

                    price = compute_iceberg_price(
                        side, book, tick, config.price_policy,
                        config.urgency, config.price_limit,
                    )
                    order_link_id = f"ice_{parent_id}_{child_idx_counter}"

                    try:
                        async with limiter:
                            resp = await client.place_limit_gtc(
                                symbol=symbol, side=side,
                                qty=str(this_qty), price=str(price),
                                reduce_only=config.reduce_only,
                                order_link_id=order_link_id,
                            )
                        oid = resp["order_id"]
                        active_children[oid] = ChildOrderState(
                            child_idx=child_idx_counter,
                            order_id=oid,
                            order_link_id=order_link_id,
                            side=side, price=price, qty=this_qty,
                            placed_at=time.time(),
                        )
                        unfilled_active += this_qty
                        child_idx_counter += 1
                        result.child_count += 1
                        log.info("iceberg_child_placed",
                                 order_id=oid, idx=child_idx_counter - 1,
                                 qty=str(this_qty), price=str(price))
                    except Exception as e:
                        log.error("iceberg_place_child_error", error=str(e),
                                  idx=child_idx_counter)

                if not active_children:
                    state = IcebergState.ABORTED
                    result.detail = "Failed to place any child orders"
                    break
                state = IcebergState.WORKING

            # ═══ WORKING ═══
            elif state == IcebergState.WORKING:
                await asyncio.sleep(config.poll_interval_ms / 1000.0)

                # Poll each active child
                completed_oids: List[str] = []
                for oid, child in list(active_children.items()):
                    try:
                        async with limiter:
                            status = await client.get_order_status(symbol, oid)
                    except Exception:
                        continue

                    new_filled = status["filled_qty"]
                    if new_filled > child.filled_qty:
                        delta = new_filled - child.filled_qty
                        fill_price = status["avg_price"] if status["avg_price"] > 0 else child.price
                        all_fills.append(FillRecord(price=fill_price, qty=delta, ts=time.time()))
                        vwap_num += fill_price * delta
                        total_filled += delta
                        child.filled_qty = new_filled
                        result.fill_count += 1
                        log.info("iceberg_child_fill",
                                 order_id=oid, delta=str(delta),
                                 total_filled=str(total_filled))

                    child.status = status["status"]
                    if status["status"] in ("Filled", "Cancelled"):
                        completed_oids.append(oid)

                for oid in completed_oids:
                    del active_children[oid]

                remaining = round_qty_to_step(total_qty - total_filled, qty_step)

                # Check if done
                if remaining < min_qty:
                    state = IcebergState.DONE
                    break

                # Check if need to replenish
                if len(active_children) < config.max_active_children:
                    unfilled_active = _sum_active_unfilled(active_children)
                    if remaining - unfilled_active >= min_qty:
                        state = IcebergState.REPLENISH
                        continue

                # Fetch fresh orderbook for guards + repricing
                try:
                    async with limiter:
                        ob = await client.get_orderbook(symbol)
                    book = compute_book_metrics(ob)
                except Exception:
                    continue

                # Price limit guard
                if _check_price_limit_breached(side, book, config.price_limit):
                    log.error("iceberg_price_limit_breached",
                              bid=str(book.best_bid), ask=str(book.best_ask))
                    n = await _cancel_all_children(client, symbol, active_children, limiter)
                    total_cancel_count += n
                    state = IcebergState.ABORTED
                    result.detail = "Price limit breached"
                    break

                # Slippage guard
                if result.initial_mid > 0 and total_filled > 0:
                    current_vwap = vwap_num / total_filled
                    if side == "Buy":
                        slippage = (current_vwap - result.initial_mid) / result.initial_mid * 10000
                    else:
                        slippage = (result.initial_mid - current_vwap) / result.initial_mid * 10000
                    if slippage > config.max_slippage_bps:
                        log.error("iceberg_slippage_abort", slippage_bps=float(slippage))
                        n = await _cancel_all_children(client, symbol, active_children, limiter)
                        total_cancel_count += n
                        state = IcebergState.ABORTED
                        result.detail = f"Slippage {float(slippage):.1f} bps exceeded limit {config.max_slippage_bps}"
                        break

                # Reprice check (only if cooldown elapsed)
                now_mono = time.monotonic()
                cooldown_ok = (now_mono - last_reprice_mono) >= (config.cooldown_ms / 1000.0)
                if cooldown_ok and active_children:
                    new_price = compute_iceberg_price(
                        side, book, tick, config.price_policy,
                        config.urgency, config.price_limit,
                    )
                    for oid, child in list(active_children.items()):
                        if child.status not in ("New", "PartiallyFilled"):
                            continue
                        if not _should_reprice(child.price, new_price, book.mid,
                                               config.reprice_threshold_bps):
                            continue
                        try:
                            async with limiter:
                                await client.amend_order(
                                    symbol=symbol,
                                    order_id=oid,
                                    price=str(new_price),
                                )
                            log.info("iceberg_child_amended",
                                     order_id=oid, old_price=str(child.price),
                                     new_price=str(new_price))
                            child.price = new_price
                            child.amend_count += 1
                            total_reprice_count += 1
                            total_cancel_count += 1   # amend counts toward cancel budget
                            last_reprice_mono = now_mono
                        except Exception as e:
                            log.warning("iceberg_amend_failed",
                                        order_id=oid, error=str(e))

            # ═══ REPLENISH ═══
            elif state == IcebergState.REPLENISH:
                try:
                    async with limiter:
                        ob = await client.get_orderbook(symbol)
                    book = compute_book_metrics(ob)
                except Exception:
                    state = IcebergState.WORKING
                    continue

                unfilled_active = _sum_active_unfilled(active_children)
                qty_to_place = remaining - unfilled_active
                slots = config.max_active_children - len(active_children)

                for _ in range(slots):
                    this_qty = min(child_qty, qty_to_place)
                    this_qty = round_qty_to_step(this_qty, qty_step)
                    if this_qty < min_qty:
                        break

                    price = compute_iceberg_price(
                        side, book, tick, config.price_policy,
                        config.urgency, config.price_limit,
                    )
                    order_link_id = f"ice_{parent_id}_{child_idx_counter}"

                    try:
                        async with limiter:
                            resp = await client.place_limit_gtc(
                                symbol=symbol, side=side,
                                qty=str(this_qty), price=str(price),
                                reduce_only=config.reduce_only,
                                order_link_id=order_link_id,
                            )
                        oid = resp["order_id"]
                        active_children[oid] = ChildOrderState(
                            child_idx=child_idx_counter,
                            order_id=oid,
                            order_link_id=order_link_id,
                            side=side, price=price, qty=this_qty,
                            placed_at=time.time(),
                        )
                        child_idx_counter += 1
                        result.child_count += 1
                        qty_to_place -= this_qty
                        log.info("iceberg_child_replenished",
                                 order_id=oid, idx=child_idx_counter - 1,
                                 qty=str(this_qty), price=str(price))
                    except Exception as e:
                        log.error("iceberg_replenish_error", error=str(e))

                state = IcebergState.WORKING

        # ═══ Finalize — last-moment fill reconciliation ═══
        for oid, child in list(active_children.items()):
            try:
                async with limiter:
                    status = await client.get_order_status(symbol, oid)
                if status["filled_qty"] > child.filled_qty:
                    delta = status["filled_qty"] - child.filled_qty
                    fill_price = status["avg_price"] if status["avg_price"] > 0 else child.price
                    all_fills.append(FillRecord(price=fill_price, qty=delta, ts=time.time()))
                    vwap_num += fill_price * delta
                    total_filled += delta
            except Exception:
                pass

        remaining = round_qty_to_step(total_qty - total_filled, qty_step)

        # Set final status
        if state == IcebergState.DONE:
            result.status = "done" if remaining < min_qty else "partial"
        elif state == IcebergState.ABORTED:
            result.status = "aborted"

        result.filled_qty = total_filled
        result.remaining_qty = remaining
        result.cancel_count = total_cancel_count
        result.reprice_count = total_reprice_count
        result.fills = all_fills
        result.time_elapsed_ms = (time.time() - t_start) * 1000

        # VWAP
        if total_filled > 0 and vwap_num > 0:
            result.avg_price = vwap_num / total_filled

        # Fee estimate (conservative: assume all taker since GTC can cross)
        if result.avg_price > 0:
            result.estimated_fee = (
                total_filled * result.avg_price * Decimal(str(config.taker_fee_rate))
            )

        # Price improvement vs initial mid
        if result.initial_mid > 0 and result.avg_price > 0:
            if side == "Buy":
                improvement = (result.initial_mid - result.avg_price) / result.initial_mid
            else:
                improvement = (result.avg_price - result.initial_mid) / result.initial_mid
            result.price_improvement_bps = float(improvement * Decimal("10000"))

        log.info("iceberg_result",
                 status=result.status, filled=str(total_filled),
                 remaining=str(remaining), avg_price=str(result.avg_price),
                 children=result.child_count, cancels=total_cancel_count,
                 reprices=total_reprice_count, fills=result.fill_count,
                 time_ms=round(result.time_elapsed_ms),
                 improvement_bps=round(result.price_improvement_bps, 2),
                 parent_id=parent_id)

        return result

    except Exception as e:
        # Emergency cleanup
        if active_children:
            await _cancel_all_children(client, symbol, active_children, limiter)
        result.status = "aborted"
        result.detail = str(e)
        result.time_elapsed_ms = (time.time() - t_start) * 1000
        result.filled_qty = total_filled
        result.remaining_qty = round_qty_to_step(total_qty - total_filled, qty_step)
        result.fills = all_fills
        if total_filled > 0 and vwap_num > 0:
            result.avg_price = vwap_num / total_filled
        log.error("iceberg_executor_error", error=str(e),
                  elapsed_ms=round(result.time_elapsed_ms), parent_id=parent_id)
        return result
