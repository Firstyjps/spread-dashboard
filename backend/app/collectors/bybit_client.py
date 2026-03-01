"""
Bybit V5 SDK client for order execution and position management.
Uses asyncio.to_thread() to wrap pybit's synchronous HTTP calls.
"""
import asyncio
import structlog
from pybit.unified_trading import HTTP

log = structlog.get_logger()


class BybitClient:
    def __init__(self, config):
        self.session = HTTP(
            testnet=False,
            api_key=config.bybit_api_key,
            api_secret=config.bybit_api_secret,
            domain="bytick"
        )

    async def get_position(self, symbol: str) -> dict:
        """Get current position for a symbol.

        Returns:
            {amount, is_long, entry_price, pnl, mark_price, liq_price, leverage}
        """
        try:
            resp = await asyncio.to_thread(
                self.session.get_positions,
                category="linear",
                symbol=symbol,
            )

            positions = resp.get("result", {}).get("list", [])
            if not positions or float(positions[0].get("size", 0)) == 0:
                return {
                    "amount": 0.0,
                    "is_long": True,
                    "entry_price": 0.0,
                    "pnl": 0.0,
                    "mark_price": 0.0,
                    "liq_price": 0.0,
                    "leverage": 0.0,
                }

            pos = positions[0]
            return {
                "amount": abs(float(pos.get("size", 0))),
                "is_long": pos.get("side") == "Buy",
                "entry_price": float(pos.get("avgPrice", 0)),
                "pnl": float(pos.get("unrealisedPnl", 0)),
                "mark_price": float(pos.get("markPrice", 0)),
                "liq_price": float(pos.get("liqPrice", 0) or 0),
                "leverage": float(pos.get("leverage", 0)),
            }
        except Exception as e:
            log.error("bybit_get_position_error", symbol=symbol, error=str(e))
            return {
                "amount": 0.0, "is_long": True, "entry_price": 0.0,
                "pnl": 0.0, "mark_price": 0.0, "liq_price": 0.0, "leverage": 0.0,
            }

    async def place_market_order(self, symbol: str, amount: float, side: str, reduce_only: bool = False):
        """Place a market order on Bybit linear perps.

        Args:
            symbol: e.g. "BTCUSDT"
            amount: quantity
            side: "Buy" or "Sell"
            reduce_only: if True, only reduces existing position
        """
        log.info("bybit_placing_order", symbol=symbol, amount=amount, side=side, reduce_only=reduce_only)
        try:
            response = await asyncio.to_thread(
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
        except Exception as e:
            log.error("bybit_order_error", symbol=symbol, error=str(e))
            raise
