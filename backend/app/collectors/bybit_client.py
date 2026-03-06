"""
Bybit V5 SDK client for order execution and position management.
Uses asyncio.to_thread() to wrap pybit's synchronous HTTP calls.
All thread calls wrapped with asyncio.wait_for() to prevent hang.
"""
import asyncio
import structlog
from decimal import Decimal
from pybit.unified_trading import HTTP

from app.utils.async_helpers import thread_with_timeout as _thread_with_timeout

log = structlog.get_logger()


class BybitClient:
    def __init__(self, config):
        self.session = HTTP(
            testnet=False,
            api_key=config.bybit_api_key,
            api_secret=config.bybit_api_secret,
            domain="bytick",
            recv_window=5000,
        )
        # Set socket-level timeout on the underlying requests.Session
        # to prevent zombie threads when Bybit API is unresponsive
        if hasattr(self.session, 'client'):
            self.session.client.timeout = 10

    async def get_position(self, symbol: str) -> dict:
        """Get current position for a symbol.

        Returns:
            {amount, is_long, entry_price, pnl, mark_price, liq_price, leverage}
        """
        try:
            resp = await _thread_with_timeout(
                self.session.get_positions,
                category="linear",
                symbol=symbol,
            )

            positions = resp.get("result", {}).get("list", [])
            _empty = {
                "amount": 0.0, "is_long": True, "entry_price": 0.0,
                "pnl": 0.0, "mark_price": 0.0, "liq_price": 0.0,
                "leverage": 0.0, "cum_realized_pnl": 0.0,
            }
            if not positions or float(positions[0].get("size", 0)) == 0:
                return _empty

            pos = positions[0]
            return {
                "amount": abs(float(pos.get("size", 0))),
                "is_long": pos.get("side") == "Buy",
                "entry_price": float(pos.get("avgPrice", 0)),
                "pnl": float(pos.get("unrealisedPnl", 0)),
                "mark_price": float(pos.get("markPrice", 0)),
                "liq_price": float(pos.get("liqPrice", 0) or 0),
                "leverage": float(pos.get("leverage", 0)),
                "cum_realized_pnl": float(pos.get("cumRealisedPnl", 0)),
            }
        except asyncio.TimeoutError:
            log.error("bybit_get_position_timeout", symbol=symbol)
            return {
                "amount": 0.0, "is_long": True, "entry_price": 0.0,
                "pnl": 0.0, "mark_price": 0.0, "liq_price": 0.0,
                "leverage": 0.0, "cum_realized_pnl": 0.0,
            }
        except Exception as e:
            log.error("bybit_get_position_error", symbol=symbol, error=str(e))
            return {
                "amount": 0.0, "is_long": True, "entry_price": 0.0,
                "pnl": 0.0, "mark_price": 0.0, "liq_price": 0.0,
                "leverage": 0.0, "cum_realized_pnl": 0.0,
            }

    async def place_market_order(self, symbol: str, amount: float, side: str, reduce_only: bool = False):
        """Place a market order on Bybit linear perps."""
        log.info("bybit_placing_order", symbol=symbol, amount=amount, side=side, reduce_only=reduce_only)
        try:
            response = await _thread_with_timeout(
                self.session.place_order,
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(amount),
                timeInForce="IOC",
                reduceOnly=reduce_only,
            )
            ret_code = response.get("retCode", -1)
            if ret_code != 0:
                log.error("bybit_order_rejected", response=response)
                raise Exception(f"Bybit order rejected: {response.get('retMsg', 'unknown')}")

            order_id = response.get("result", {}).get("orderId", "")
            log.info("bybit_order_success", order_id=order_id, symbol=symbol)
            return {"status": "success", "order_id": order_id, "response": response}
        except asyncio.TimeoutError:
            log.error("bybit_order_timeout", symbol=symbol, side=side)
            raise Exception("Bybit order timed out after 10s")
        except Exception as e:
            log.error("bybit_order_error", symbol=symbol, error=str(e))
            raise

    # --- Maker Engine Methods ---

    async def get_instrument_info(self, symbol: str, category: str = "linear") -> dict:
        """Fetch instrument constraints: tickSize, qtyStep, min/max qty."""
        try:
            resp = await _thread_with_timeout(
                self.session.get_instruments_info, category=category, symbol=symbol
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
            log.error("bybit_instrument_info_timeout", symbol=symbol)
            raise Exception(f"Instrument info timed out for {symbol}")
        except Exception as e:
            log.error("bybit_instrument_info_error", symbol=symbol, error=str(e))
            raise

    async def get_orderbook(self, symbol: str, category: str = "linear", limit: int = 25) -> dict:
        """Fetch orderbook top N levels."""
        try:
            resp = await _thread_with_timeout(
                self.session.get_orderbook, category=category, symbol=symbol, limit=limit
            )
            result = resp.get("result", {})
            return {
                "bids": result.get("b", []),  # [[price, size], ...]
                "asks": result.get("a", []),
                "ts": result.get("ts", 0),
            }
        except asyncio.TimeoutError:
            log.error("bybit_orderbook_timeout", symbol=symbol)
            raise Exception(f"Orderbook timed out for {symbol}")
        except Exception as e:
            log.error("bybit_orderbook_error", symbol=symbol, error=str(e))
            raise

    async def place_limit_postonly(
        self, symbol: str, side: str, qty: str, price: str, reduce_only: bool = False
    ) -> dict:
        """Place a PostOnly LIMIT order (maker-only)."""
        log.info("bybit_placing_postonly", symbol=symbol, side=side, qty=qty, price=price)
        try:
            resp = await _thread_with_timeout(
                self.session.place_order,
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Limit",
                qty=qty,
                price=price,
                timeInForce="PostOnly",
                reduceOnly=reduce_only,
            )
            ret_code = resp.get("retCode", -1)
            ret_msg = resp.get("retMsg", "")

            if ret_code != 0:
                log.warning("bybit_postonly_rejected", retCode=ret_code, retMsg=ret_msg)
                raise Exception(f"PostOnly rejected: {ret_msg} (code={ret_code})")

            order_id = resp.get("result", {}).get("orderId", "")
            log.info("bybit_postonly_placed", order_id=order_id)
            return {"order_id": order_id, "status": "success"}
        except asyncio.TimeoutError:
            log.error("bybit_postonly_timeout", symbol=symbol)
            raise Exception(f"PostOnly order timed out for {symbol}")
        except Exception as e:
            log.error("bybit_postonly_error", symbol=symbol, error=str(e))
            raise

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel an open order."""
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
            log.info("bybit_order_cancelled", order_id=order_id)
            return {"status": "cancelled", "order_id": order_id}
        except asyncio.TimeoutError:
            log.error("bybit_cancel_timeout", order_id=order_id)
            raise Exception(f"Cancel timed out for order {order_id}")
        except Exception as e:
            log.error("bybit_cancel_error", order_id=order_id, error=str(e))
            raise

    async def place_limit_gtc(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        reduce_only: bool = False,
        order_link_id: str | None = None,
    ) -> dict:
        """Place a GTC LIMIT order (for iceberg children).

        Unlike PostOnly, GTC orders can fill immediately if price crosses.
        This is intentional — iceberg wants fills, just hides total size.
        """
        log.info("bybit_placing_gtc", symbol=symbol, side=side, qty=qty,
                 price=price, order_link_id=order_link_id)
        try:
            kwargs: dict = dict(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Limit",
                qty=qty,
                price=price,
                timeInForce="GTC",
                reduceOnly=reduce_only,
            )
            if order_link_id:
                kwargs["orderLinkId"] = order_link_id

            resp = await _thread_with_timeout(self.session.place_order, **kwargs)
            ret_code = resp.get("retCode", -1)
            ret_msg = resp.get("retMsg", "")

            if ret_code != 0:
                log.warning("bybit_gtc_rejected", retCode=ret_code, retMsg=ret_msg)
                raise Exception(f"GTC rejected: {ret_msg} (code={ret_code})")

            order_id = resp.get("result", {}).get("orderId", "")
            log.info("bybit_gtc_placed", order_id=order_id, order_link_id=order_link_id)
            return {"order_id": order_id, "status": "success"}
        except asyncio.TimeoutError:
            log.error("bybit_gtc_timeout", symbol=symbol)
            raise Exception(f"GTC order timed out for {symbol}")
        except Exception as e:
            log.error("bybit_gtc_error", symbol=symbol, error=str(e))
            raise

    async def amend_order(
        self,
        symbol: str,
        order_id: str,
        price: str | None = None,
        qty: str | None = None,
    ) -> dict:
        """Amend an open order's price and/or qty.

        Uses Bybit V5 amend endpoint — atomic reprice without cancel+replace race.
        """
        log.info("bybit_amending_order", order_id=order_id, price=price, qty=qty)
        try:
            kwargs: dict = dict(
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            if price is not None:
                kwargs["price"] = price
            if qty is not None:
                kwargs["qty"] = qty

            resp = await _thread_with_timeout(self.session.amend_order, **kwargs)
            ret_code = resp.get("retCode", -1)
            if ret_code != 0:
                raise Exception(f"Amend failed: {resp.get('retMsg', 'unknown')} (code={ret_code})")
            log.info("bybit_order_amended", order_id=order_id)
            return {"status": "amended", "order_id": order_id}
        except asyncio.TimeoutError:
            log.error("bybit_amend_timeout", order_id=order_id)
            raise Exception(f"Amend timed out for order {order_id}")
        except Exception as e:
            log.error("bybit_amend_error", order_id=order_id, error=str(e))
            raise

    async def get_order_status(self, symbol: str, order_id: str) -> dict:
        """Poll order status. Returns {status, filled_qty, avg_price, remaining_qty}."""
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

            return {"status": "Unknown", "filled_qty": Decimal("0"),
                    "avg_price": Decimal("0"), "remaining_qty": Decimal("0")}
        except asyncio.TimeoutError:
            log.error("bybit_order_status_timeout", order_id=order_id)
            raise Exception(f"Order status timed out for {order_id}")
        except Exception as e:
            log.error("bybit_order_status_error", order_id=order_id, error=str(e))
            raise
