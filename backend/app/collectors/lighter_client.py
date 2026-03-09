"""
Lighter DEX SDK client for order execution and position management.

Uses dynamic scaling from MARKET_META (populated at startup from /api/v1/orderBooks).
Each market has its own supported_size_decimals and supported_price_decimals.
"""
import time
import aiohttp
import lighter
import structlog
from typing import Optional
from app.analytics.spread_engine import get_all_current_data
from app.collectors.lighter_collector import SYMBOL_TO_MARKET_ID, MARKET_META, get_market_stats

log = structlog.get_logger()

_TIMEOUT = aiohttp.ClientTimeout(total=10)


class LighterClient:
    def __init__(self, config):
        self.config = config
        self.base_url = config.lighter_base_url
        self._session: Optional[aiohttp.ClientSession] = None

        # SignerClient is only usable when private key is configured
        if config.lighter_private_key:
            self.client = lighter.SignerClient(
                url=self.base_url,
                account_index=int(config.lighter_account_index),
                api_private_keys={int(config.lighter_api_key_index): config.lighter_private_key},
            )
        else:
            self.client = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Reuse persistent HTTP session instead of creating per call."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=_TIMEOUT,
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
            )
        return self._session

    async def get_position(self, symbol: str) -> dict:
        try:
            lighter_symbol = self.config.lighter_aliases.get(symbol, symbol)
            expected_market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)

            url = f"{self.base_url}/api/v1/account"
            params = {"by": "index", "value": str(self.config.lighter_account_index)}

            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return {"amount": 0.0, "is_long": True, "entry_price": 0.0, "pnl": 0.0}
                data = await resp.json()

            accounts = data.get("accounts", [])
            if not accounts:
                return {"amount": 0.0, "is_long": True, "entry_price": 0.0, "pnl": 0.0}
                
            positions = accounts[0].get("positions", [])

            pos = {}
            for p in positions:
                p_market_id = int(p.get("market_id", -1))
                p_symbol = p.get("symbol", "")

                if (expected_market_id is not None and p_market_id == int(expected_market_id)) or \
                    (p_symbol and p_symbol.upper() in lighter_symbol.upper()):
                    pos = p
                    break

            _empty = {
                "amount": 0.0, "is_long": True, "entry_price": 0.0,
                "pnl": 0.0, "realized_pnl": 0.0, "funding_paid": 0.0,
            }
            if not pos:
                return _empty

            raw_size = float(pos.get("position", "0"))

            if raw_size == 0:
                return _empty

            sign = pos.get("sign", 1)
            is_long = (sign == 1)

            if raw_size < 0:
                is_long = False
                raw_size = abs(raw_size)

            entry_price = float(pos.get("avg_entry_price", "0"))
            pnl = float(pos.get("unrealized_pnl", "0"))
            realized_pnl = float(pos.get("realized_pnl", "0"))
            funding_paid = float(pos.get("total_funding_paid_out", "0"))
            liq_price = float(pos.get("liquidation_price", "0"))

            # Look up mark price from WebSocket cache
            mark_price = None
            if expected_market_id is not None:
                stats = get_market_stats(expected_market_id)
                if stats:
                    try:
                        mark_price = float(stats.get("mark_price", 0)) or None
                    except (ValueError, TypeError):
                        pass

            return {
                "amount": raw_size,
                "is_long": is_long,
                "entry_price": entry_price,
                "pnl": pnl,
                "realized_pnl": realized_pnl,
                "funding_paid": funding_paid,
                "mark_price": mark_price,
                "liq_price": liq_price or None,
            }

        except Exception as e:
            log.error("lighter_get_position_crash", symbol=symbol, error=str(e))
            return {
                "amount": 0.0, "is_long": True, "entry_price": 0.0,
                "pnl": 0.0, "realized_pnl": 0.0, "funding_paid": 0.0,
            }

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

        # Slippage protection: ±1% (tighter guard = better fill prices)
        worst_price = current_price * 1.01 if not is_ask else current_price * 0.99
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
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        if self.client and hasattr(self.client, "api_client"):
            try:
                await self.client.api_client.close()
            except Exception:
                pass
