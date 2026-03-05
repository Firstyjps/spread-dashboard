"""
Maker-Only Sliced Execution Engine for Bybit V5 LINEAR perpetuals.

Guarantees maker fills by using PostOnly LIMIT orders exclusively:
  - PostOnly: Bybit rejects the order if it would cross the spread
  - Maker pricing: BUY at best_bid, SELL at best_ask (rests on book)
  - Never chases into taker territory

Why this ensures maker fills:
  1. timeInForce="PostOnly" tells Bybit: "reject this order if it would
     take liquidity." So the order either rests on the book (maker) or
     gets rejected — it NEVER fills as taker.
  2. Maker pricing (BUY<=bid, SELL>=ask) ensures the price is on our
     side of the spread, so the order rests and waits for a counter-party.
  3. If the market moves and our resting order becomes stale, we cancel
     and replace at the new maker price — never chase.

Algorithm:
  1. Fetch instrument info (tickSize, qtyStep, minQty, minNotional)
  2. Loop until filled_usd >= target_usd - tolerance_usd or timeout:
     a. Fetch top-of-book (best_bid, best_ask)
     b. Compute maker price: BUY→best_bid, SELL→best_ask, rounded to tick
     c. Compute slice qty = slice_usd / price, rounded to qtyStep
     d. Place PostOnly LIMIT order
     e. Poll for stale_ms:
        - Filled? Update accumulators, continue to next slice
        - Not filled? Cancel and re-post at updated price
     f. Sleep pace_ms (with jitter)
  3. When target reached: cancel_all_orders, return summary
"""
import asyncio
import random
import time
import structlog
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import List, Optional
from uuid import uuid4

from app.exchanges.bybit_linear.client import BybitLinearMakerClient, PostOnlyRejectError

log = structlog.get_logger()


# ─── Result Types ─────────────────────────────────────────────────

@dataclass
class MakerFill:
    """A single fill record."""
    order_id: str
    price: Decimal
    qty: Decimal
    value_usd: Decimal
    is_maker: Optional[bool]       # None if verification unavailable
    ts: float


@dataclass
class ExecutionSummary:
    """Result of a maker-only sliced execution."""
    status: str = "error"              # done | partial | timeout | error
    symbol: str = ""
    side: str = ""
    target_usd: Decimal = Decimal("0")
    filled_usd: Decimal = Decimal("0")
    filled_qty: Decimal = Decimal("0")
    remaining_usd: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")  # VWAP
    slices_placed: int = 0
    slices_filled: int = 0
    slices_cancelled: int = 0
    postonly_rejects: int = 0          # orders rejected because would take
    reprice_count: int = 0
    elapsed_ms: float = 0.0
    maker_fill_count: int = 0          # verified maker fills
    taker_fill_count: int = 0          # verified taker fills (should be 0)
    estimated_fee_usd: Decimal = Decimal("0")
    fills: List[MakerFill] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "target_usd": str(self.target_usd),
            "filled_usd": str(self.filled_usd),
            "filled_qty": str(self.filled_qty),
            "remaining_usd": str(self.remaining_usd),
            "avg_price": str(self.avg_price),
            "slices_placed": self.slices_placed,
            "slices_filled": self.slices_filled,
            "slices_cancelled": self.slices_cancelled,
            "postonly_rejects": self.postonly_rejects,
            "reprice_count": self.reprice_count,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "maker_fill_count": self.maker_fill_count,
            "taker_fill_count": self.taker_fill_count,
            "estimated_fee_usd": str(self.estimated_fee_usd),
            "detail": self.detail,
        }


# ─── Price / Qty Helpers ─────────────────────────────────────────

def _round_price(price: Decimal, tick: Decimal, side: str) -> Decimal:
    """Round price to tick.  BUY→floor (lower=safer for maker), SELL→ceil."""
    if tick <= 0:
        return price
    if side == "Buy":
        return (price / tick).to_integral_value(rounding=ROUND_DOWN) * tick
    else:
        return (price / tick).to_integral_value(rounding=ROUND_UP) * tick


def _round_qty(qty: Decimal, step: Decimal) -> Decimal:
    """Floor qty to step size."""
    if step <= 0:
        return qty
    return (qty / step).to_integral_value(rounding=ROUND_DOWN) * step


def _compute_maker_price(
    side: str,
    best_bid: Decimal,
    best_ask: Decimal,
    tick: Decimal,
) -> Decimal:
    """Compute maker-safe price.

    BUY:  price = best_bid  (rests on bid side, never crosses)
    SELL: price = best_ask  (rests on ask side, never crosses)

    Hard enforcement:
      BUY price  <= best_bid  (NEVER >= best_ask)
      SELL price >= best_ask  (NEVER <= best_bid)
    """
    if side == "Buy":
        price = best_bid
        # Ensure we never cross into taker territory
        price = min(price, best_bid)
        return _round_price(price, tick, "Buy")
    else:
        price = best_ask
        price = max(price, best_ask)
        return _round_price(price, tick, "Sell")


def _shift_away(price: Decimal, tick: Decimal, side: str) -> Decimal:
    """Shift price 1 tick away from spread to avoid PostOnly rejection."""
    if side == "Buy":
        return price - tick   # lower buy price = more passive
    else:
        return price + tick   # higher sell price = more passive


# ─── Main Executor ────────────────────────────────────────────────

async def execute_linear_maker_sliced(
    client: BybitLinearMakerClient,
    symbol: str,
    side: str,
    target_usd: float,
    slices: int = 10,
    pace_ms: int = 500,
    stale_ms: int = 2000,
    max_live_orders: int = 2,
    tolerance_usd: float = 2.0,
    max_duration_s: int = 120,
) -> ExecutionSummary:
    """Execute a maker-only sliced order on Bybit V5 LINEAR.

    Places small PostOnly LIMIT slices, reprices stale orders,
    never crosses into taker territory.

    Args:
        client: BybitLinearMakerClient instance
        symbol: e.g. "BTCUSDT", "XAUTUSDT"
        side: "Buy" or "Sell"
        target_usd: total notional to execute in USD
        slices: number of child orders to split into
        pace_ms: minimum delay between slice placements (ms)
        stale_ms: cancel + replace if unfilled after this many ms
        max_live_orders: max concurrent resting orders (default 2)
        tolerance_usd: stop when filled_usd >= target_usd - tolerance
        max_duration_s: hard timeout in seconds
    """
    assert side in ("Buy", "Sell"), f"Invalid side: {side}"
    assert target_usd > 0, "target_usd must be positive"
    assert slices > 0, "slices must be positive"

    # Normalize side for Bybit API (uppercase first letter)
    side = "Buy" if side.upper() in ("BUY", "BUY") else "Sell"

    t_start = time.time()
    target = Decimal(str(target_usd))
    tolerance = Decimal(str(tolerance_usd))
    slice_usd = target / slices
    exec_id = uuid4().hex[:10]

    summary = ExecutionSummary(
        symbol=symbol,
        side=side,
        target_usd=target,
        remaining_usd=target,
    )

    filled_usd = Decimal("0")
    filled_qty = Decimal("0")
    vwap_num = Decimal("0")     # sum(price * qty)
    all_fills: List[MakerFill] = []
    maker_verified = 0
    taker_verified = 0
    slice_idx = 0

    try:
        # ═══ 1. Fetch instrument info ═══
        inst = await client.get_instrument_info(symbol)
        tick = inst.tick_size
        step = inst.qty_step
        min_qty = inst.min_qty
        min_notional = inst.min_notional

        log.info(
            "maker_slicer_start",
            exec_id=exec_id, symbol=symbol, side=side,
            target_usd=str(target), slices=slices,
            slice_usd=str(slice_usd),
            tick=str(tick), step=str(step),
            min_qty=str(min_qty), min_notional=str(min_notional),
        )

        # Adjust slice_usd if below minimum notional
        if slice_usd < min_notional:
            old_slices = slices
            slices = max(1, int(target / min_notional))
            slice_usd = target / slices
            log.warning(
                "maker_slicer_adjusted_slices",
                old_slices=old_slices, new_slices=slices,
                new_slice_usd=str(slice_usd),
                reason=f"slice_usd below min_notional ({min_notional})",
            )

        # ═══ 2. Main execution loop ═══
        while filled_usd < target - tolerance:
            elapsed = time.time() - t_start
            if elapsed >= max_duration_s:
                summary.detail = f"Timeout after {max_duration_s}s"
                log.warning("maker_slicer_timeout", elapsed_s=round(elapsed, 1))
                break

            # Remaining USD to fill
            remaining = target - filled_usd
            this_slice_usd = min(slice_usd, remaining)

            # ── 2a. Fetch orderbook ──
            try:
                ob = await client.get_orderbook(symbol)
            except Exception as e:
                log.warning("maker_slicer_ob_error", error=str(e))
                await asyncio.sleep(pace_ms / 1000.0)
                continue

            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if not bids or not asks:
                log.warning("maker_slicer_empty_book")
                await asyncio.sleep(pace_ms / 1000.0)
                continue

            best_bid = Decimal(bids[0][0])
            best_ask = Decimal(asks[0][0])

            # ── 2b. Compute maker price ──
            maker_price = _compute_maker_price(side, best_bid, best_ask, tick)

            # Sanity: BUY must be <= best_bid, SELL must be >= best_ask
            if side == "Buy" and maker_price > best_bid:
                maker_price = _round_price(best_bid, tick, "Buy")
            if side == "Sell" and maker_price < best_ask:
                maker_price = _round_price(best_ask, tick, "Sell")

            # ── 2c. Compute qty ──
            if maker_price <= 0:
                log.warning("maker_slicer_zero_price")
                await asyncio.sleep(pace_ms / 1000.0)
                continue

            qty = _round_qty(this_slice_usd / maker_price, step)

            # Check min constraints
            if qty < min_qty:
                qty = min_qty
            notional = qty * maker_price
            if notional < min_notional:
                qty = _round_qty(min_notional / maker_price + step, step)
                log.info("maker_slicer_qty_adjusted", qty=str(qty), reason="below min_notional")

            # ── 2d. Place PostOnly LIMIT ──
            order_link_id = f"mks_{exec_id}_{slice_idx}"
            order_id: Optional[str] = None
            postonly_retries = 0

            while postonly_retries < 3:
                try:
                    resp = await client.place_postonly_limit(
                        symbol=symbol,
                        side=side,
                        qty=str(qty),
                        price=str(maker_price),
                        order_link_id=order_link_id,
                    )
                    order_id = resp["order_id"]
                    summary.slices_placed += 1
                    slice_idx += 1
                    log.info(
                        "maker_slicer_placed",
                        idx=slice_idx, order_id=order_id,
                        qty=str(qty), price=str(maker_price),
                    )
                    break
                except PostOnlyRejectError:
                    summary.postonly_rejects += 1
                    postonly_retries += 1
                    maker_price = _shift_away(maker_price, tick, side)
                    log.info(
                        "maker_slicer_postonly_shift",
                        new_price=str(maker_price), retry=postonly_retries,
                    )
                except Exception as e:
                    log.error("maker_slicer_place_error", error=str(e))
                    break

            if order_id is None:
                # Failed to place after retries — skip this cycle
                await asyncio.sleep(pace_ms / 1000.0)
                continue

            # ── 2e. Poll for fill (up to stale_ms) ──
            poll_start = time.time()
            order_filled = False

            while (time.time() - poll_start) * 1000 < stale_ms:
                # Check global timeout
                if (time.time() - t_start) >= max_duration_s:
                    break

                await asyncio.sleep(min(0.3, stale_ms / 1000.0 / 4))

                try:
                    status = await client.get_order_status(symbol, order_id)
                except Exception:
                    continue

                if status["filled_qty"] > 0:
                    fill_qty = status["filled_qty"]
                    fill_price = status["avg_price"] if status["avg_price"] > 0 else maker_price
                    fill_value = status["cum_exec_value"] if status["cum_exec_value"] > 0 else fill_qty * fill_price

                    vwap_num += fill_price * fill_qty
                    filled_qty += fill_qty
                    filled_usd += fill_value

                    all_fills.append(MakerFill(
                        order_id=order_id,
                        price=fill_price,
                        qty=fill_qty,
                        value_usd=fill_value,
                        is_maker=None,  # verified later
                        ts=time.time(),
                    ))
                    summary.slices_filled += 1
                    order_filled = True

                    log.info(
                        "maker_slicer_fill",
                        order_id=order_id, qty=str(fill_qty),
                        price=str(fill_price), value=str(fill_value),
                        total_filled_usd=str(filled_usd),
                    )
                    break

                if status["status"] in ("Cancelled", "Rejected", "Deactivated"):
                    break

            # ── 2e'. Cancel stale order if not filled ──
            if not order_filled:
                try:
                    await client.cancel_order(symbol, order_id)
                    summary.slices_cancelled += 1
                    summary.reprice_count += 1
                    log.info("maker_slicer_stale_cancelled", order_id=order_id)
                except Exception as e:
                    # Could already be filled between check and cancel
                    err = str(e).lower()
                    if "filled" in err or "not found" in err:
                        # Double-check: was it actually filled?
                        try:
                            final = await client.get_order_status(symbol, order_id)
                            if final["filled_qty"] > 0:
                                fill_qty = final["filled_qty"]
                                fill_price = final["avg_price"] if final["avg_price"] > 0 else maker_price
                                fill_value = final["cum_exec_value"] if final["cum_exec_value"] > 0 else fill_qty * fill_price
                                vwap_num += fill_price * fill_qty
                                filled_qty += fill_qty
                                filled_usd += fill_value
                                all_fills.append(MakerFill(
                                    order_id=order_id, price=fill_price,
                                    qty=fill_qty, value_usd=fill_value,
                                    is_maker=None, ts=time.time(),
                                ))
                                summary.slices_filled += 1
                                order_filled = True
                        except Exception:
                            pass
                    else:
                        log.warning("maker_slicer_cancel_error", order_id=order_id, error=str(e))

            # Check if target reached after this slice
            if filled_usd >= target - tolerance:
                log.info("maker_slicer_target_reached", filled_usd=str(filled_usd))
                break

            # ── 2f. Pace delay with small jitter ──
            jitter = random.uniform(0, pace_ms * 0.2) / 1000.0
            await asyncio.sleep(pace_ms / 1000.0 + jitter)

        # ═══ 3. Cleanup: cancel all remaining open orders ═══
        try:
            cancel_resp = await client.cancel_all_orders(symbol)
            cleanup_count = cancel_resp.get("count", 0)
            if cleanup_count > 0:
                log.info("maker_slicer_cleanup", cancelled=cleanup_count)
        except Exception as e:
            log.warning("maker_slicer_cleanup_error", error=str(e))

        # ═══ 4. Verify maker/taker via execution records ═══
        for fill in all_fills:
            try:
                records = await client.get_execution_records(symbol, fill.order_id)
                for rec in records:
                    if rec["is_maker"]:
                        maker_verified += 1
                        fill.is_maker = True
                    else:
                        taker_verified += 1
                        fill.is_maker = False
                        log.error(
                            "maker_slicer_TAKER_DETECTED",
                            order_id=fill.order_id,
                            exec_id=rec["exec_id"],
                            price=str(rec["price"]),
                            qty=str(rec["qty"]),
                        )
            except Exception as e:
                log.warning("maker_verify_error", order_id=fill.order_id, error=str(e))

        # ═══ 5. Build summary ═══
        summary.filled_usd = filled_usd
        summary.filled_qty = filled_qty
        summary.remaining_usd = target - filled_usd
        summary.fills = all_fills
        summary.elapsed_ms = (time.time() - t_start) * 1000
        summary.maker_fill_count = maker_verified
        summary.taker_fill_count = taker_verified

        # VWAP
        if filled_qty > 0 and vwap_num > 0:
            summary.avg_price = vwap_num / filled_qty

        # Estimated fee (maker rate = 0.02%)
        maker_fee_rate = Decimal("0.0002")
        summary.estimated_fee_usd = filled_usd * maker_fee_rate

        # Status
        if filled_usd >= target - tolerance:
            summary.status = "done"
        elif (time.time() - t_start) >= max_duration_s:
            summary.status = "timeout" if filled_usd == 0 else "partial"
        elif filled_usd > 0:
            summary.status = "partial"
        else:
            summary.status = "error"
            summary.detail = summary.detail or "No fills received"

        log.info(
            "maker_slicer_result",
            exec_id=exec_id,
            status=summary.status,
            filled_usd=str(filled_usd),
            filled_qty=str(filled_qty),
            avg_price=str(summary.avg_price),
            slices_placed=summary.slices_placed,
            slices_filled=summary.slices_filled,
            cancelled=summary.slices_cancelled,
            rejects=summary.postonly_rejects,
            maker_fills=maker_verified,
            taker_fills=taker_verified,
            elapsed_ms=round(summary.elapsed_ms),
        )

        return summary

    except Exception as e:
        summary.status = "error"
        summary.detail = str(e)
        summary.elapsed_ms = (time.time() - t_start) * 1000
        summary.filled_usd = filled_usd
        summary.filled_qty = filled_qty
        summary.fills = all_fills

        # Emergency cleanup
        try:
            await client.cancel_all_orders(symbol)
        except Exception:
            pass

        log.error("maker_slicer_error", exec_id=exec_id, error=str(e))
        return summary
