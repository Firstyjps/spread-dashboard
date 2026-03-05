"""
Smart Maker Execution Engine for Bybit.

Always attempts PostOnly LIMIT (maker-only) with adaptive repricing.
Falls back to MARKET only when explicitly allowed and timed out.
Uses Decimal for all price/qty math — never float for money.
"""
import asyncio
import time
import structlog
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import List, Optional

log = structlog.get_logger()


# ─── Configuration ───────────────────────────────────────────────

@dataclass
class MakerConfig:
    max_time_s: float = 15.0
    reprice_interval_ms: int = 800
    max_reprices: int = 8
    aggressiveness: str = "BALANCED"         # CONSERVATIVE / BALANCED / AGGRESSIVE
    allow_market_fallback: bool = True
    maker_fee_rate: float = 0.0002           # 0.02%
    taker_fee_rate: float = 0.00055          # 0.055%
    spread_guard_ticks: int = 1              # pause if spread < N ticks
    vol_window: int = 20                     # mid samples for vol guard
    vol_limit_ticks: int = 10                # max short-term move
    max_deviation_ticks: int = 50            # max drift from mid → abort
    stall_intervals: int = 3                 # reprices with no fills → more aggressive


# ─── Result ──────────────────────────────────────────────────────

@dataclass
class FillRecord:
    price: Decimal
    qty: Decimal
    ts: float


@dataclass
class MakerResult:
    status: str                              # filled | partial | market_fallback | aborted
    filled_qty: Decimal = Decimal("0")
    remaining_qty: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")        # VWAP
    order_count: int = 0
    cancel_count: int = 0
    reprice_count: int = 0
    maker_reject_count: int = 0
    time_to_fill_ms: float = 0.0
    estimated_fee: Decimal = Decimal("0")
    price_improvement_bps: float = 0.0       # vs initial mid
    initial_mid: Decimal = Decimal("0")
    fills: List[FillRecord] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "filled_qty": str(self.filled_qty),
            "remaining_qty": str(self.remaining_qty),
            "avg_price": str(self.avg_price),
            "order_count": self.order_count,
            "cancel_count": self.cancel_count,
            "reprice_count": self.reprice_count,
            "maker_reject_count": self.maker_reject_count,
            "time_to_fill_ms": round(self.time_to_fill_ms, 1),
            "estimated_fee": str(self.estimated_fee),
            "price_improvement_bps": round(self.price_improvement_bps, 2),
            "detail": self.detail,
        }


# ─── Decimal Rounding Helpers ────────────────────────────────────

def round_price_to_tick(price: Decimal, tick: Decimal, side: str) -> Decimal:
    """Round price to tick.  BUY→floor, SELL→ceil."""
    if tick <= 0:
        return price
    if side == "Buy":
        return (price / tick).to_integral_value(rounding=ROUND_DOWN) * tick
    else:
        return (price / tick).to_integral_value(rounding=ROUND_UP) * tick


def round_qty_to_step(qty: Decimal, step: Decimal) -> Decimal:
    """Floor qty to step size."""
    if step <= 0:
        return qty
    return (qty / step).to_integral_value(rounding=ROUND_DOWN) * step


def validate_qty(qty: Decimal, min_qty: Decimal, max_qty: Decimal) -> Decimal:
    """Clamp qty within exchange limits."""
    if qty < min_qty:
        raise ValueError(f"Qty {qty} below minimum {min_qty}")
    if max_qty > 0 and qty > max_qty:
        qty = max_qty
    return qty


# ─── Orderbook Analysis ─────────────────────────────────────────

@dataclass
class BookMetrics:
    best_bid: Decimal
    best_ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    spread: Decimal
    mid: Decimal
    microprice: Decimal


def compute_book_metrics(orderbook: dict) -> BookMetrics:
    """Compute orderbook metrics from raw Bybit book data."""
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    if not bids or not asks:
        raise ValueError("Empty orderbook — cannot compute metrics")

    best_bid = Decimal(bids[0][0])
    bid_size = Decimal(bids[0][1])
    best_ask = Decimal(asks[0][0])
    ask_size = Decimal(asks[0][1])

    spread = best_ask - best_bid
    mid = (best_bid + best_ask) / 2

    total_size = bid_size + ask_size
    if total_size > 0:
        microprice = (best_bid * ask_size + best_ask * bid_size) / total_size
    else:
        microprice = mid

    return BookMetrics(
        best_bid=best_bid, best_ask=best_ask,
        bid_size=bid_size, ask_size=ask_size,
        spread=spread, mid=mid, microprice=microprice,
    )


# ─── Volatility Tracker ─────────────────────────────────────────

class VolTracker:
    """Ring buffer of mid prices for short-term volatility estimation."""

    def __init__(self, window: int = 20):
        self.mids: deque = deque(maxlen=window)

    def push(self, mid: Decimal):
        self.mids.append(mid)

    def get_move_ticks(self, tick: Decimal) -> Decimal:
        """Max absolute move within the window, in ticks."""
        if len(self.mids) < 2 or tick <= 0:
            return Decimal("0")
        hi = max(self.mids)
        lo = min(self.mids)
        return (hi - lo) / tick


# ─── Maker Price Strategy ───────────────────────────────────────

def compute_maker_price(
    side: str,
    best_bid: Decimal,
    best_ask: Decimal,
    tick: Decimal,
    mode: str,
    microprice: Decimal,
    mid: Decimal,
) -> Decimal:
    """
    Compute maker-safe price.

    Modes:
      QUEUE_TOP:  join the best price without crossing.
      STEP_AHEAD: step 1 tick ahead of best (still maker, never crosses).

    Hard rules:
      BUY price  < best_ask
      SELL price > best_bid
    """
    if side == "Buy":
        if mode == "STEP_AHEAD":
            price = min(best_bid + tick, best_ask - tick)
        else:
            price = best_bid
        # Hard ceiling: must be strictly below best ask
        price = min(price, best_ask - tick)
        return round_price_to_tick(price, tick, "Buy")
    else:
        if mode == "STEP_AHEAD":
            price = max(best_ask - tick, best_bid + tick)
        else:
            price = best_ask
        # Hard floor: must be strictly above best bid
        price = max(price, best_bid + tick)
        return round_price_to_tick(price, tick, "Sell")


def select_mode(aggressiveness: str, microprice: Decimal, mid: Decimal, side: str) -> str:
    """Auto-select placement mode based on config + microprice pressure."""
    if aggressiveness == "CONSERVATIVE":
        return "QUEUE_TOP"
    if aggressiveness == "AGGRESSIVE":
        return "STEP_AHEAD"

    # BALANCED: use microprice signal
    if side == "Buy":
        # Buy pressure (microprice > mid) → be more aggressive
        return "STEP_AHEAD" if microprice > mid else "QUEUE_TOP"
    else:
        # Sell pressure (microprice < mid) → be more aggressive
        return "STEP_AHEAD" if microprice < mid else "QUEUE_TOP"


# ─── Smart Execute Main Loop ────────────────────────────────────

async def smart_execute_maker(
    client,
    symbol: str,
    side: str,
    target_qty: Decimal,
    config: MakerConfig,
) -> MakerResult:
    """
    Smart maker execution engine.

    1) Fetches instrument info for correct rounding.
    2) Fetches orderbook for microprice-based placement.
    3) Places PostOnly LIMIT, adaptively reprices.
    4) Falls back to MARKET if allowed and timed out.
    """
    t_start = time.time()
    result = MakerResult(status="aborted", remaining_qty=target_qty)
    vol_tracker = VolTracker(window=config.vol_window)
    fills: list = []
    total_filled = Decimal("0")
    vwap_num = Decimal("0")       # sum(price * qty) for VWAP
    current_order_id: Optional[str] = None
    stall_count = 0               # reprices with no new fills
    prev_filled = Decimal("0")

    try:
        # ── 1. Fetch instrument info ──
        inst = await client.get_instrument_info(symbol)
        tick = inst["tick_size"]
        qty_step = inst["qty_step"]
        min_qty = inst["min_qty"]
        max_qty = inst["max_qty"]

        log.info("maker_instrument",
                 symbol=symbol, tick=str(tick), step=str(qty_step),
                 min_qty=str(min_qty), max_qty=str(max_qty))

        # ── 2. Validate & round qty ──
        remaining = round_qty_to_step(target_qty, qty_step)
        remaining = validate_qty(remaining, min_qty, max_qty)
        result.remaining_qty = remaining

        # ── 3. Initial orderbook ──
        ob = await client.get_orderbook(symbol)
        book = compute_book_metrics(ob)
        vol_tracker.push(book.mid)
        result.initial_mid = book.mid

        log.info("maker_book",
                 bid=str(book.best_bid), ask=str(book.best_ask),
                 spread=str(book.spread), mid=str(book.mid),
                 microprice=str(book.microprice))

        # ── 4. Spread guard ──
        spread_ticks = book.spread / tick if tick > 0 else Decimal("0")
        if spread_ticks < config.spread_guard_ticks:
            log.warning("maker_spread_too_tight",
                        spread_ticks=str(spread_ticks), guard=config.spread_guard_ticks)

        # ── 5. Compute initial maker price ──
        mode = select_mode(config.aggressiveness, book.microprice, book.mid, side)
        price = compute_maker_price(side, book.best_bid, book.best_ask, tick, mode,
                                    book.microprice, book.mid)

        log.info("maker_initial_price", price=str(price), mode=mode, side=side)

        # ── 6. Place initial PostOnly LIMIT ──
        qty_str = str(remaining)
        price_str = str(price)

        try:
            resp = await client.place_limit_postonly(symbol, side, qty_str, price_str)
            current_order_id = resp["order_id"]
            result.order_count += 1
        except Exception as e:
            err_msg = str(e).lower()
            if "post only" in err_msg or "would take" in err_msg or "140024" in err_msg:
                result.maker_reject_count += 1
                # Shift 1 tick away and retry
                price = _shift_away(price, tick, side)
                price_str = str(price)
                log.info("maker_postonly_retry", new_price=price_str)
                resp = await client.place_limit_postonly(symbol, side, qty_str, price_str)
                current_order_id = resp["order_id"]
                result.order_count += 1
            else:
                raise

        # ── 7. Reprice loop ──
        for reprice_i in range(config.max_reprices):
            elapsed = time.time() - t_start
            if elapsed >= config.max_time_s:
                break

            await asyncio.sleep(config.reprice_interval_ms / 1000.0)

            # Poll order status
            if current_order_id:
                status = await client.get_order_status(symbol, current_order_id)
                new_filled = status["filled_qty"]

                if new_filled > prev_filled:
                    # New fill(s)
                    delta_qty = new_filled - prev_filled
                    fill_price = status["avg_price"] if status["avg_price"] > 0 else price
                    fills.append(FillRecord(price=fill_price, qty=delta_qty, ts=time.time()))
                    vwap_num += fill_price * delta_qty
                    total_filled = new_filled
                    stall_count = 0
                    prev_filled = new_filled
                else:
                    stall_count += 1

                remaining = round_qty_to_step(target_qty - total_filled, qty_step)

                if status["status"] == "Filled" or remaining < min_qty:
                    # Fully filled
                    result.status = "filled"
                    result.filled_qty = total_filled
                    result.remaining_qty = Decimal("0")
                    break

            # Fetch fresh orderbook
            try:
                ob = await client.get_orderbook(symbol)
                book = compute_book_metrics(ob)
                vol_tracker.push(book.mid)
            except Exception:
                continue

            # ── Volatility guard ──
            vol_move = vol_tracker.get_move_ticks(tick)
            if vol_move > config.vol_limit_ticks:
                log.warning("maker_vol_guard", move_ticks=str(vol_move), limit=config.vol_limit_ticks)
                continue  # skip repricing this cycle

            # ── Deviation guard ──
            if result.initial_mid > 0:
                deviation = abs(book.mid - result.initial_mid) / tick
                if deviation > config.max_deviation_ticks:
                    log.error("maker_deviation_abort",
                              deviation_ticks=str(deviation), limit=config.max_deviation_ticks)
                    result.status = "aborted"
                    result.detail = f"Price drifted {deviation} ticks from initial mid"
                    break

            # ── Decide whether to reprice ──
            new_mode = select_mode(config.aggressiveness, book.microprice, book.mid, side)
            # Escalate if stalled
            if stall_count >= config.stall_intervals:
                new_mode = "STEP_AHEAD"

            new_price = compute_maker_price(side, book.best_bid, book.best_ask, tick,
                                            new_mode, book.microprice, book.mid)

            price_moved = abs(new_price - price) >= 2 * tick
            should_reprice = price_moved or stall_count >= config.stall_intervals

            if not should_reprice:
                continue

            # ── Atomic Reprice via amend_order ──
            remaining = round_qty_to_step(target_qty - total_filled, qty_step)
            if remaining < min_qty:
                result.status = "filled"
                result.filled_qty = total_filled
                result.remaining_qty = remaining
                break

            price = new_price

            if current_order_id:
                amend_retries = 0
                amend_success = False
                while amend_retries < 3:
                    try:
                        await client.amend_order(
                            symbol, current_order_id,
                            price=str(price), qty=str(remaining),
                        )
                        result.reprice_count += 1
                        stall_count = 0
                        amend_success = True
                        log.info("maker_amended", price=str(price), remaining=str(remaining),
                                 reprice=reprice_i + 1, mode=new_mode)
                        break
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "post only" in err_msg or "would take" in err_msg or "140024" in err_msg:
                            # Amend rejected because new price would cross — shift away
                            result.maker_reject_count += 1
                            price = _shift_away(price, tick, side)
                            amend_retries += 1
                            log.info("maker_amend_shift", new_price=str(price), retry=amend_retries)
                        elif "order not exist" in err_msg or "110001" in err_msg:
                            # Order already filled or cancelled — check status
                            status = await client.get_order_status(symbol, current_order_id)
                            if status["status"] == "Filled":
                                total_filled = status["filled_qty"]
                                if status["avg_price"] > 0:
                                    vwap_num = status["avg_price"] * total_filled
                                result.status = "filled"
                                result.filled_qty = total_filled
                                result.remaining_qty = Decimal("0")
                            amend_success = True  # exit retry loop
                            break
                        else:
                            # Unknown error — fall back to cancel+replace
                            log.warning("maker_amend_fallback", error=str(e))
                            try:
                                await client.cancel_order(symbol, current_order_id)
                                result.cancel_count += 1
                            except Exception:
                                pass
                            try:
                                resp = await client.place_limit_postonly(symbol, side, str(remaining), str(price))
                                current_order_id = resp["order_id"]
                                result.order_count += 1
                                result.reprice_count += 1
                                stall_count = 0
                                amend_success = True
                                log.info("maker_repriced_fallback", price=str(price), remaining=str(remaining))
                            except Exception:
                                pass
                            break

                if result.status == "filled":
                    break
                if not amend_success:
                    log.warning("maker_amend_exhausted", retries=3)
                    continue

        # ── 8. Timeout / market fallback ──
        elapsed_ms = (time.time() - t_start) * 1000
        remaining = round_qty_to_step(target_qty - total_filled, qty_step)

        if result.status not in ("filled",) and remaining >= min_qty:
            # Cancel resting order
            if current_order_id:
                try:
                    await client.cancel_order(symbol, current_order_id)
                    result.cancel_count += 1
                except Exception:
                    pass
                # Final poll
                status = await client.get_order_status(symbol, current_order_id)
                if status["filled_qty"] > total_filled:
                    delta = status["filled_qty"] - total_filled
                    fill_price = status["avg_price"] if status["avg_price"] > 0 else price
                    fills.append(FillRecord(price=fill_price, qty=delta, ts=time.time()))
                    vwap_num += fill_price * delta
                    total_filled = status["filled_qty"]
                    remaining = round_qty_to_step(target_qty - total_filled, qty_step)

            if remaining >= min_qty and config.allow_market_fallback:
                log.warning("maker_market_fallback",
                            remaining=str(remaining), elapsed_ms=round(elapsed_ms))
                try:
                    mkt_resp = await client.place_market_order(symbol, float(remaining), side)
                    fills.append(FillRecord(price=Decimal("0"), qty=remaining, ts=time.time()))
                    total_filled += remaining
                    remaining = Decimal("0")
                    result.order_count += 1
                    result.status = "market_fallback"
                    result.detail = "Timed out, remaining filled via MARKET (taker fees apply)"
                except Exception as e:
                    result.status = "partial" if total_filled > 0 else "aborted"
                    result.detail = f"Market fallback failed: {e}"
            elif remaining >= min_qty:
                result.status = "partial" if total_filled > 0 else "aborted"
                result.detail = f"Timed out, {remaining} unfilled (market fallback disabled)"

        # ── 9. Compute telemetry ──
        elapsed_ms = (time.time() - t_start) * 1000
        result.filled_qty = total_filled
        result.remaining_qty = round_qty_to_step(target_qty - total_filled, qty_step)
        result.time_to_fill_ms = elapsed_ms
        result.fills = fills

        if result.status not in ("filled", "market_fallback", "partial", "aborted"):
            result.status = "filled" if result.remaining_qty < min_qty else "partial"

        # VWAP
        if total_filled > 0 and vwap_num > 0:
            result.avg_price = vwap_num / total_filled

        # Estimated fee
        maker_filled = total_filled
        taker_filled = Decimal("0")
        if result.status == "market_fallback" and fills:
            # Last fill was market (taker)
            taker_filled = fills[-1].qty
            maker_filled = total_filled - taker_filled

        if result.avg_price > 0:
            maker_fee = maker_filled * result.avg_price * Decimal(str(config.maker_fee_rate))
            taker_fee = taker_filled * result.avg_price * Decimal(str(config.taker_fee_rate))
            result.estimated_fee = maker_fee + taker_fee

        # Price improvement vs initial mid
        if result.initial_mid > 0 and result.avg_price > 0:
            if side == "Buy":
                improvement = (result.initial_mid - result.avg_price) / result.initial_mid
            else:
                improvement = (result.avg_price - result.initial_mid) / result.initial_mid
            result.price_improvement_bps = float(improvement * 10000)

        log.info("maker_result",
                 status=result.status,
                 filled=str(result.filled_qty),
                 avg_price=str(result.avg_price),
                 time_ms=round(elapsed_ms),
                 orders=result.order_count,
                 cancels=result.cancel_count,
                 reprices=result.reprice_count,
                 rejects=result.maker_reject_count,
                 fee=str(result.estimated_fee),
                 improvement_bps=round(result.price_improvement_bps, 2))

        return result

    except Exception as e:
        elapsed_ms = (time.time() - t_start) * 1000
        # Cancel any resting order on error
        if current_order_id:
            try:
                await client.cancel_order(symbol, current_order_id)
            except Exception:
                pass
        result.status = "aborted"
        result.time_to_fill_ms = elapsed_ms
        result.detail = str(e)
        log.error("maker_engine_error", error=str(e), elapsed_ms=round(elapsed_ms))
        return result


# ─── Helpers ─────────────────────────────────────────────────────

def _shift_away(price: Decimal, tick: Decimal, side: str) -> Decimal:
    """Shift price 1 tick away from crossing to avoid PostOnly rejection."""
    if side == "Buy":
        return price - tick
    else:
        return price + tick
