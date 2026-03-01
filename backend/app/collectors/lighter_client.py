"""
Lighter DEX SDK client for order execution and position management.

Uses dynamic scaling from MARKET_META (populated at startup from /api/v1/orderBooks).
Each market has its own supported_size_decimals and supported_price_decimals.
"""
import time
import aiohttp
import lighter
import structlog
from app.analytics.spread_engine import get_all_current_data
from app.collectors.lighter_collector import SYMBOL_TO_MARKET_ID, MARKET_META

log = structlog.get_logger()


class LighterClient:
    def __init__(self, config):
        self.config = config
        self.base_url = config.lighter_base_url

        # SignerClient is only usable when private key is configured
        if config.lighter_private_key:
            self.client = lighter.SignerClient(
                url=self.base_url,
                account_index=int(config.lighter_account_index),
                api_private_keys={int(config.lighter_api_key_index): config.lighter_private_key},
            )
        else:
            self.client = None

    async def get_position(self, symbol: str) -> dict:
        """Get Lighter position via REST API.

        Uses GET /api/v1/account?by=index&value={account_index}
        Returns: {amount, is_long, entry_price, pnl}
        """
        try:
            lighter_symbol = self.config.lighter_aliases.get(symbol, symbol)
            market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)

            if market_id is None:
                log.warning("lighter_market_id_not_found", symbol=lighter_symbol)
                return {"amount": 0.0, "is_long": True, "entry_price": 0.0, "pnl": 0.0}

            url = f"{self.base_url}/api/v1/account"
            params = {"by": "index", "value": str(self.config.lighter_account_index)}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        log.error("lighter_account_api_error", status=resp.status)
                        return {"amount": 0.0, "is_long": True, "entry_price": 0.0, "pnl": 0.0}
                    data = await resp.json()

            # Parse position from account data
            positions = data.get("positions", {})
            pos = positions.get(str(market_id), {})

            size_str = pos.get("position", "0")
            size = float(size_str) if size_str else 0.0

            entry_str = pos.get("avg_entry_price", "0")
            entry_price = float(entry_str) if entry_str else 0.0

            pnl_str = pos.get("unrealized_pnl", "0")
            pnl = float(pnl_str) if pnl_str else 0.0

            return {
                "amount": abs(size),
                "is_long": size > 0,
                "entry_price": entry_price,
                "pnl": pnl,
            }
        except Exception as e:
            log.error("lighter_get_position_error", symbol=symbol, error=str(e))
            return {"amount": 0.0, "is_long": True, "entry_price": 0.0, "pnl": 0.0}

    async def place_market_order(self, symbol: str, amount: float, is_ask: bool, reduce_only: bool = False):
        """Place a market IOC order on Lighter.

        Args:
            symbol: dashboard symbol (e.g. "BTCUSDT")
            amount: base amount (human-readable, e.g. 0.01)
            is_ask: True = sell, False = buy
            reduce_only: if True, only reduces existing position

        Raises:
            Exception on any failure (so executor can detect via asyncio.gather)
        """
        if not self.client:
            raise Exception("Lighter private key not configured")

        lighter_symbol = self.config.lighter_aliases.get(symbol, symbol)
        market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)

        if market_id is None:
            raise Exception(f"Market ID not found for {lighter_symbol}")

        # Get current price for slippage calculation
        all_data = get_all_current_data()
        current_price = all_data.get(symbol, {}).get("lighter", {}).get("mid", 0)

        if current_price == 0:
            raise Exception(f"Lighter price data missing for {symbol}")

        # Dynamic scaling from MARKET_META (populated at startup from API)
        meta = MARKET_META.get(lighter_symbol, {})
        size_dec = meta.get("size_decimals", 4)
        price_dec = meta.get("price_decimals", 2)
        min_base = meta.get("min_base_amount", 0)

        s_scale = 10 ** size_dec
        p_scale = 10 ** price_dec

        # Validate minimum amount
        if amount < min_base:
            raise Exception(
                f"Amount {amount} below Lighter minimum {min_base} for {symbol}"
            )

        # Slippage protection: ±2%
        worst_price = current_price * 1.02 if not is_ask else current_price * 0.98
        scaled_amount = int(round(float(amount) * s_scale))
        scaled_price = int(round(float(worst_price) * p_scale))

        client_order_index = int(time.time() % 1000000)

        log.info(
            "lighter_sending_order",
            symbol=symbol,
            lighter_symbol=lighter_symbol,
            market_id=market_id,
            amount_raw=amount,
            scaled_amount=scaled_amount,
            price_raw=round(worst_price, 4),
            scaled_price=scaled_price,
            size_dec=size_dec,
            price_dec=price_dec,
            is_ask=is_ask,
            reduce_only=reduce_only,
        )

        try:
            result = await self.client.create_order(
                market_index=int(market_id),
                client_order_index=client_order_index,
                base_amount=scaled_amount,
                price=scaled_price,
                is_ask=bool(is_ask),
                order_type=self.client.ORDER_TYPE_MARKET,
                time_in_force=self.client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL,
                reduce_only=reduce_only,
                order_expiry=self.client.DEFAULT_IOC_EXPIRY,
                api_key_index=int(self.config.lighter_api_key_index),
            )

            # create_order returns:
            #   Success: (CreateOrder, RespSendTx, None)
            #   Error:   (None, None, error_string)
            if isinstance(result, tuple) and len(result) >= 3:
                order_obj, resp_obj, err = result
            else:
                order_obj = result
                resp_obj = None
                err = getattr(result, "error", None)

            if err:
                raise Exception(f"Lighter order rejected: {err}")

            # Extract tx_hash from response object
            tx_hash = "unknown"
            if resp_obj is not None:
                tx_hash = getattr(resp_obj, "tx_hash", None) or str(resp_obj)

            log.info("lighter_order_success", tx_hash=tx_hash, symbol=symbol)
            return {"status": "success", "tx_hash": tx_hash}

        except Exception as e:
            log.error("lighter_execution_error", symbol=symbol, error=str(e))
            raise  # Re-raise so executor can detect failure

    async def close(self):
        """Close the underlying API client session. Call when done with client."""
        if self.client and hasattr(self.client, "api_client"):
            try:
                await self.client.api_client.close()
            except Exception:
                pass
