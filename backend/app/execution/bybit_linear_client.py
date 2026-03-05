"""
LIMIT-only Bybit V5 LINEAR client.

Hard rule: NO Market orders ever. Every order placed through this client
is orderType="Limit" with a mandatory price. This is enforced at the API
boundary with asserts — a missing price is a programming error, not a
runtime condition.

Uses asyncio.to_thread() + wait_for() to wrap pybit's synchronous HTTP,
same pattern as the existing BybitClient.
"""
import asyncio
import structlog
from decimal import Decimal
from pybit.unified_trading import HTTP

from app.utils.async_helpers import thread_with_timeout as _thread_with_timeout

log = structlog.get_logger()


class BybitLinearClient:
    """
    LIMIT-only Bybit V5 LINEAR perpetuals client.

    Every order is orderType="Limit" with a mandatory price.
    No place_market_order method exists — by design.
    """

    def __init__(self, config, *, testnet: bool = False):
        self.testnet = testnet
        self.session = HTTP(
            testnet=testnet,
            api_key=config.bybit_api_key,
            api_secret=config.bybit_api_secret,
            domain="bytick" if not testnet else None,
        )

    # ─── Order Placement (LIMIT ONLY) ─────────────────────────────

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        *,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        order_link_id: str | None = None,
    ) -> dict:
        """Place a LIMIT order. Price is REQUIRED — no Market orders ever.

        Args:
            symbol: e.g. "BTCUSDT"
            side: "Buy" or "Sell"
            qty: order quantity as string (Decimal-safe)
            price: limit price as string (Decimal-safe)
            time_in_force: "GTC" (default) or "PostOnly"
            reduce_only: close-only flag
            order_link_id: optional client-side order ID

        Returns:
            {"order_id": str, "status": "success"}
        """
        # Hard enforcement: price is mandatory
        assert price is not None, "BybitLinearClient: price is REQUIRED (no Market orders)"
        assert price != "", "BybitLinearClient: price must not be empty"
        assert side in ("Buy", "Sell"), f"Invalid side: {side}"

        log.info(
            "linear_placing_limit",
            symbol=symbol, side=side, qty=qty, price=price,
            tif=time_in_force, reduce_only=reduce_only,
        )

        kwargs: dict = dict(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=qty,
            price=price,
            timeInForce=time_in_force,
            reduceOnly=reduce_only,
        )
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id

        try:
            resp = await _thread_with_timeout(self.session.place_order, **kwargs)
            ret_code = resp.get("retCode", -1)
            ret_msg = resp.get("retMsg", "")

            if ret_code != 0:
                log.warning("linear_limit_rejected", retCode=ret_code, retMsg=ret_msg)
                raise Exception(f"Limit order rejected: {ret_msg} (code={ret_code})")

            order_id = resp.get("result", {}).get("orderId", "")
            log.info("linear_limit_placed", order_id=order_id, symbol=symbol)
            return {"order_id": order_id, "status": "success"}

        except asyncio.TimeoutError:
            log.error("linear_limit_timeout", symbol=symbol)
            raise Exception(f"Limit order timed out after {_SDK_TIMEOUT}s")
        except Exception as e:
            log.error("linear_limit_error", symbol=symbol, error=str(e))
            raise

    # ─── Order Management ─────────────────────────────────────────

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel a single open order."""
        try:
            resp = await _thread_with_timeout(
                self.session.cancel_order,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            ret_code = resp.get("retCode", -1)
            if ret_code != 0:
                raise Exception(f"Cancel failed: {resp.get('retMsg', 'unknown')}")
            log.info("linear_order_cancelled", order_id=order_id)
            return {"status": "cancelled", "order_id": order_id}
        except asyncio.TimeoutError:
            log.error("linear_cancel_timeout", order_id=order_id)
            raise Exception(f"Cancel timed out for order {order_id}")
        except Exception as e:
            log.error("linear_cancel_error", order_id=order_id, error=str(e))
            raise

    async def cancel_all_orders(self, symbol: str) -> dict:
        """Cancel all open orders for a symbol."""
        try:
            resp = await _thread_with_timeout(
                self.session.cancel_all_orders,
                category="linear",
                symbol=symbol,
            )
            ret_code = resp.get("retCode", -1)
            if ret_code != 0:
                raise Exception(f"Cancel all failed: {resp.get('retMsg', 'unknown')}")
            cancelled = resp.get("result", {}).get("list", [])
            log.info("linear_all_orders_cancelled", symbol=symbol, count=len(cancelled))
            return {"status": "cancelled", "count": len(cancelled)}
        except asyncio.TimeoutError:
            log.error("linear_cancel_all_timeout", symbol=symbol)
            raise Exception(f"Cancel all timed out for {symbol}")
        except Exception as e:
            log.error("linear_cancel_all_error", symbol=symbol, error=str(e))
            raise

    async def get_order_status(self, symbol: str, order_id: str) -> dict:
        """Poll order status.

        Returns:
            {status, filled_qty, avg_price, remaining_qty}
        """
        try:
            # Try open orders first
            resp = await _thread_with_timeout(
                self.session.get_open_orders,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            orders = resp.get("result", {}).get("list", [])
            if orders:
                o = orders[0]
                filled = Decimal(o.get("cumExecQty", "0"))
                total = Decimal(o.get("qty", "0"))
                avg_p = o.get("avgPrice", "0")
                return {
                    "status": o.get("orderStatus", "Unknown"),
                    "filled_qty": filled,
                    "avg_price": Decimal(avg_p) if avg_p and avg_p != "0" else Decimal("0"),
                    "remaining_qty": total - filled,
                }

            # Not in open orders → check history (filled/cancelled)
            resp = await _thread_with_timeout(
                self.session.get_order_history,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            orders = resp.get("result", {}).get("list", [])
            if orders:
                o = orders[0]
                filled = Decimal(o.get("cumExecQty", "0"))
                total = Decimal(o.get("qty", "0"))
                avg_p = o.get("avgPrice", "0")
                return {
                    "status": o.get("orderStatus", "Unknown"),
                    "filled_qty": filled,
                    "avg_price": Decimal(avg_p) if avg_p and avg_p != "0" else Decimal("0"),
                    "remaining_qty": total - filled,
                }

            return {
                "status": "Unknown",
                "filled_qty": Decimal("0"),
                "avg_price": Decimal("0"),
                "remaining_qty": Decimal("0"),
            }
        except asyncio.TimeoutError:
            log.error("linear_order_status_timeout", order_id=order_id)
            raise Exception(f"Order status timed out for {order_id}")
        except Exception as e:
            log.error("linear_order_status_error", order_id=order_id, error=str(e))
            raise

    # ─── Position & Market Data ───────────────────────────────────

    async def get_position(self, symbol: str) -> dict:
        """Get current position for a symbol.

        Returns:
            {amount, side, entry_price, pnl, leverage}
        """
        _empty = {
            "amount": Decimal("0"),
            "side": "None",
            "entry_price": Decimal("0"),
            "pnl": Decimal("0"),
            "leverage": Decimal("0"),
        }
        try:
            resp = await _thread_with_timeout(
                self.session.get_positions,
                category="linear",
                symbol=symbol,
            )
            positions = resp.get("result", {}).get("list", [])
            if not positions or Decimal(positions[0].get("size", "0")) == 0:
                return _empty

            pos = positions[0]
            return {
                "amount": abs(Decimal(pos.get("size", "0"))),
                "side": pos.get("side", "None"),
                "entry_price": Decimal(pos.get("avgPrice", "0")),
                "pnl": Decimal(pos.get("unrealisedPnl", "0")),
                "leverage": Decimal(pos.get("leverage", "0")),
            }
        except asyncio.TimeoutError:
            log.error("linear_get_position_timeout", symbol=symbol)
            return _empty
        except Exception as e:
            log.error("linear_get_position_error", symbol=symbol, error=str(e))
            return _empty

    async def get_instrument_info(self, symbol: str) -> dict:
        """Fetch instrument constraints: tickSize, qtyStep, min/max qty.

        Returns:
            {tick_size, qty_step, min_qty, max_qty} — all Decimal
        """
        try:
            resp = await _thread_with_timeout(
                self.session.get_instruments_info,
                category="linear",
                symbol=symbol,
            )
            instruments = resp.get("result", {}).get("list", [])
            if not instruments:
                raise Exception(f"No instrument info for {symbol}")

            inst = instruments[0]
            price_filter = inst.get("priceFilter", {})
            lot_filter = inst.get("lotSizeFilter", {})

            return {
                "tick_size": Decimal(price_filter.get("tickSize", "0.01")),
                "qty_step": Decimal(lot_filter.get("qtyStep", "0.001")),
                "min_qty": Decimal(lot_filter.get("minOrderQty", "0.001")),
                "max_qty": Decimal(lot_filter.get("maxOrderQty", "100")),
            }
        except asyncio.TimeoutError:
            log.error("linear_instrument_info_timeout", symbol=symbol)
            raise Exception(f"Instrument info timed out for {symbol}")
        except Exception as e:
            log.error("linear_instrument_info_error", symbol=symbol, error=str(e))
            raise

    async def get_orderbook(self, symbol: str, limit: int = 5) -> dict:
        """Fetch orderbook top N levels.

        Returns:
            {bids: [[price, size], ...], asks: [[price, size], ...]}
        """
        try:
            resp = await _thread_with_timeout(
                self.session.get_orderbook,
                category="linear",
                symbol=symbol,
                limit=limit,
            )
            result = resp.get("result", {})
            return {
                "bids": result.get("b", []),
                "asks": result.get("a", []),
                "ts": result.get("ts", 0),
            }
        except asyncio.TimeoutError:
            log.error("linear_orderbook_timeout", symbol=symbol)
            raise Exception(f"Orderbook timed out for {symbol}")
        except Exception as e:
            log.error("linear_orderbook_error", symbol=symbol, error=str(e))
            raise
