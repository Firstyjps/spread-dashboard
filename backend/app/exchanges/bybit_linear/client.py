"""
Bybit V5 LINEAR client — PostOnly LIMIT orders only.

Hard rules:
  - category="linear" on every call
  - orderType="Limit" always
  - timeInForce="PostOnly" on every order placement
  - No Market order method exists

PostOnly guarantees maker fills: if the order would cross the spread
and take liquidity, Bybit rejects it instead of filling as taker.

Uses asyncio.to_thread() + wait_for() to wrap pybit's synchronous HTTP.
"""
import asyncio
import structlog
from decimal import Decimal
from pybit.unified_trading import HTTP

from app.exchanges.bybit_linear.instruments import InstrumentInfo, fetch_instrument_info
from app.utils.async_helpers import thread_with_timeout as _t

log = structlog.get_logger()


class BybitLinearMakerClient:
    """
    PostOnly LIMIT-only Bybit V5 LINEAR perpetuals client.

    Every order is:
      category="linear"
      orderType="Limit"
      timeInForce="PostOnly"

    No place_market_order. No GTC. No IOC. Maker fills only.
    """

    def __init__(self, config, *, testnet: bool = False):
        self.testnet = testnet
        self.session = HTTP(
            testnet=testnet,
            api_key=config.bybit_api_key,
            api_secret=config.bybit_api_secret,
            domain="bytick" if not testnet else None,
        )
        self._instrument_cache: dict[str, InstrumentInfo] = {}

    # ─── Instrument Info (cached) ─────────────────────────────────

    async def get_instrument_info(self, symbol: str) -> InstrumentInfo:
        """Fetch instrument info, cached per symbol for the session."""
        if symbol not in self._instrument_cache:
            info = await fetch_instrument_info(self.session, symbol)
            self._instrument_cache[symbol] = info
            log.info(
                "maker_instrument_loaded",
                symbol=symbol,
                tick=str(info.tick_size),
                step=str(info.qty_step),
                min_qty=str(info.min_qty),
                min_notional=str(info.min_notional),
            )
        return self._instrument_cache[symbol]

    # ─── Order Placement (PostOnly LIMIT ONLY) ────────────────────

    async def place_postonly_limit(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        *,
        reduce_only: bool = False,
        order_link_id: str | None = None,
    ) -> dict:
        """Place a PostOnly LIMIT order. Maker fills only.

        If this order would cross the spread (take liquidity),
        Bybit rejects it with retCode=140024 instead of filling
        as taker. This is the desired behavior.

        Args:
            symbol: e.g. "BTCUSDT"
            side: "Buy" or "Sell"
            qty: order quantity as string
            price: limit price as string — REQUIRED
            reduce_only: close-only flag
            order_link_id: client-side idempotency ID

        Returns:
            {"order_id": str, "status": "placed"}

        Raises:
            PostOnlyRejectError: if PostOnly would take liquidity
            Exception: on API error or timeout
        """
        assert price is not None, "price is REQUIRED (PostOnly LIMIT)"
        assert price != "", "price must not be empty"
        assert side in ("Buy", "Sell"), f"Invalid side: {side}"

        log.info(
            "maker_placing_postonly",
            symbol=symbol, side=side, qty=qty, price=price,
        )

        kwargs: dict = dict(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=qty,
            price=price,
            timeInForce="PostOnly",
            reduceOnly=reduce_only,
        )
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id

        try:
            resp = await _t(self.session.place_order, **kwargs)
        except asyncio.TimeoutError:
            raise Exception(f"PostOnly order timed out for {symbol}")

        ret_code = resp.get("retCode", -1)
        ret_msg = resp.get("retMsg", "")

        if ret_code != 0:
            # PostOnly rejection: order would take liquidity
            msg_lower = ret_msg.lower()
            if "post only" in msg_lower or "would take" in msg_lower or str(ret_code) == "140024":
                raise PostOnlyRejectError(
                    f"PostOnly rejected (would take liquidity): {ret_msg} (code={ret_code})"
                )
            raise Exception(f"Order rejected: {ret_msg} (code={ret_code})")

        order_id = resp.get("result", {}).get("orderId", "")
        log.info("maker_postonly_placed", order_id=order_id)
        return {"order_id": order_id, "status": "placed"}

    # ─── Order Management ─────────────────────────────────────────

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Cancel a single open order."""
        try:
            resp = await _t(
                self.session.cancel_order,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            ret_code = resp.get("retCode", -1)
            if ret_code != 0:
                raise Exception(f"Cancel failed: {resp.get('retMsg', 'unknown')}")
            log.info("maker_order_cancelled", order_id=order_id)
            return {"status": "cancelled", "order_id": order_id}
        except asyncio.TimeoutError:
            raise Exception(f"Cancel timed out for {order_id}")
        except Exception as e:
            log.error("maker_cancel_error", order_id=order_id, error=str(e))
            raise

    async def cancel_all_orders(self, symbol: str) -> dict:
        """Cancel all open orders for a symbol."""
        try:
            resp = await _t(
                self.session.cancel_all_orders,
                category="linear",
                symbol=symbol,
            )
            ret_code = resp.get("retCode", -1)
            if ret_code != 0:
                raise Exception(f"Cancel all failed: {resp.get('retMsg', 'unknown')}")
            cancelled = resp.get("result", {}).get("list", [])
            log.info("maker_all_cancelled", symbol=symbol, count=len(cancelled))
            return {"status": "cancelled", "count": len(cancelled)}
        except asyncio.TimeoutError:
            raise Exception(f"Cancel all timed out for {symbol}")
        except Exception as e:
            log.error("maker_cancel_all_error", symbol=symbol, error=str(e))
            raise

    async def get_order_status(self, symbol: str, order_id: str) -> dict:
        """Poll order status.

        Returns:
            {status, filled_qty, avg_price, remaining_qty, cum_exec_value}
        """
        try:
            # Try open orders first
            resp = await _t(
                self.session.get_open_orders,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            orders = resp.get("result", {}).get("list", [])
            if orders:
                return self._parse_order(orders[0])

            # Not in open orders → check history
            resp = await _t(
                self.session.get_order_history,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            orders = resp.get("result", {}).get("list", [])
            if orders:
                return self._parse_order(orders[0])

            return {
                "status": "Unknown",
                "filled_qty": Decimal("0"),
                "avg_price": Decimal("0"),
                "remaining_qty": Decimal("0"),
                "cum_exec_value": Decimal("0"),
            }
        except asyncio.TimeoutError:
            raise Exception(f"Order status timed out for {order_id}")
        except Exception as e:
            log.error("maker_order_status_error", order_id=order_id, error=str(e))
            raise

    @staticmethod
    def _parse_order(o: dict) -> dict:
        filled = Decimal(o.get("cumExecQty", "0"))
        total = Decimal(o.get("qty", "0"))
        avg_p = o.get("avgPrice", "0")
        cum_val = o.get("cumExecValue", "0")
        return {
            "status": o.get("orderStatus", "Unknown"),
            "filled_qty": filled,
            "avg_price": Decimal(avg_p) if avg_p and avg_p != "0" else Decimal("0"),
            "remaining_qty": total - filled,
            "cum_exec_value": Decimal(cum_val) if cum_val else Decimal("0"),
        }

    # ─── Execution Verification ───────────────────────────────────

    async def get_execution_records(self, symbol: str, order_id: str) -> list[dict]:
        """Fetch execution (trade) records for an order.

        Returns list of fills with isMaker flag from Bybit V5.
        This is the definitive way to verify maker vs taker fills.
        """
        try:
            resp = await _t(
                self.session.get_executions,
                category="linear",
                symbol=symbol,
                orderId=order_id,
            )
            records = resp.get("result", {}).get("list", [])
            return [
                {
                    "exec_id": r.get("execId", ""),
                    "order_id": r.get("orderId", ""),
                    "price": Decimal(r.get("execPrice", "0")),
                    "qty": Decimal(r.get("execQty", "0")),
                    "value": Decimal(r.get("execValue", "0")),
                    "fee": Decimal(r.get("execFee", "0")),
                    "fee_rate": r.get("feeRate", ""),
                    "is_maker": r.get("isMaker", "") == "true",
                    "exec_type": r.get("execType", ""),
                    "exec_time": r.get("execTime", ""),
                }
                for r in records
            ]
        except asyncio.TimeoutError:
            log.warning("maker_exec_records_timeout", order_id=order_id)
            return []
        except Exception as e:
            log.warning("maker_exec_records_error", order_id=order_id, error=str(e))
            return []

    # ─── Market Data ──────────────────────────────────────────────

    async def get_orderbook(self, symbol: str, limit: int = 5) -> dict:
        """Fetch top-of-book.

        Returns:
            {bids: [[price, size], ...], asks: [[price, size], ...]}
        """
        try:
            resp = await _t(
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
            raise Exception(f"Orderbook timed out for {symbol}")
        except Exception as e:
            log.error("maker_orderbook_error", symbol=symbol, error=str(e))
            raise

    async def get_position(self, symbol: str) -> dict:
        """Get current position.

        Returns:
            {amount, side, entry_price, unrealised_pnl}
        """
        _empty = {
            "amount": Decimal("0"),
            "side": "None",
            "entry_price": Decimal("0"),
            "unrealised_pnl": Decimal("0"),
        }
        try:
            resp = await _t(
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
                "unrealised_pnl": Decimal(pos.get("unrealisedPnl", "0")),
            }
        except asyncio.TimeoutError:
            log.error("maker_position_timeout", symbol=symbol)
            return _empty
        except Exception as e:
            log.error("maker_position_error", symbol=symbol, error=str(e))
            return _empty


class PostOnlyRejectError(Exception):
    """Raised when a PostOnly order would take liquidity (expected behavior)."""
    pass
