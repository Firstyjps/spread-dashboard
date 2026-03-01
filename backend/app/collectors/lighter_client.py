import time
import aiohttp
import lighter
import asyncio
import structlog
from app.analytics.spread_engine import get_all_current_data
from app.collectors.lighter_collector import SYMBOL_TO_MARKET_ID

log = structlog.get_logger()

class LighterClient:
    def __init__(self, config):
        self.config = config
        self.base_url = config.lighter_base_url
        
        self.client = lighter.SignerClient(
            url=self.base_url,
            account_index=int(config.lighter_account_index),
            api_private_keys={int(config.lighter_api_key_index): config.lighter_private_key}
        )

    async def place_market_order(self, symbol: str, amount: float, is_ask: bool, reduce_only: bool = False):
        lighter_symbol = self.config.lighter_aliases.get(symbol, symbol)
        market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)
        
        all_data = get_all_current_data()
        current_price = all_data.get(symbol, {}).get('lighter', {}).get('mid', 0)
        
        if current_price == 0:
            log.error("lighter_price_missing", symbol=symbol)
            return {"status": "failed", "error": "Price data missing"}

        s_scale = 10**5 if "BTC" in symbol else 10**4 
        p_scale = 10**1 if "BTC" in symbol else 10**2
        worst_price = current_price * 1.02 if not is_ask else current_price * 0.98
        scaled_amount = int(float(amount) * s_scale)
        scaled_price = int(float(worst_price) * p_scale)
        
        client_order_index = int(time.time() % 1000000)

        log.info("lighter_sending_order", symbol=symbol, amount=scaled_amount, price=scaled_price, reduce_only=reduce_only)

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
                api_key_index=int(self.config.lighter_api_key_index) 
            )

            if isinstance(result, tuple) and len(result) >= 3:
                _, tx_hash, err = result
            else:
                tx_hash = getattr(result, 'tx_hash', 'success')
                err = getattr(result, 'error', None)

            if err:
                log.error("lighter_sdk_error", error=str(err))
                return {"status": "failed", "error": str(err)}

            log.info("lighter_order_success", tx_hash=tx_hash, symbol=symbol)
            return {"status": "success", "tx_hash": tx_hash}

        except Exception as e:
            log.error("lighter_execution_crash", error=str(e))
            return {"status": "failed", "error": str(e)}
            
        finally:
            await self.close()

    async def close(self):
        if hasattr(self, 'client') and hasattr(self.client, 'api_client'):
            await self.client.api_client.close()