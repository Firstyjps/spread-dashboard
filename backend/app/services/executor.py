import asyncio
import structlog
from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient

log = structlog.get_logger()

class ArbitrageExecutor:
    def __init__(self, config):
        self.lighter = LighterClient(config)
        self.bybit = BybitClient(config)

    async def run_arb(self, symbol: str, strategy_side: str, amount: float):
        log.info("arb_execution_start", side=strategy_side, symbol=symbol, amount=amount)

        if strategy_side == "BUY_LIGHTER_SELL_BYBIT":
            tasks = [
                self.lighter.place_market_order(symbol, amount, is_ask=False),
                self.bybit.place_market_order(symbol, amount, side="Sell")
            ]
        else:
            tasks = [
                self.lighter.place_market_order(symbol, amount, is_ask=True),
                self.bybit.place_market_order(symbol, amount, side="Buy")
            ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        lighter_res = results[0]
        bybit_res = results[1]

        if isinstance(lighter_res, Exception) and not isinstance(bybit_res, Exception):
            log.warning("ARBITRAGE_MISMATCH: Lighter failed, emergency closing Bybit position")
            reverse_side = "Buy" if strategy_side == "SELL_LIGHTER_BUY_BYBIT" else "Sell"
            await self.bybit.place_market_order(symbol, amount, side=reverse_side)
            raise Exception(f"Lighter failed: {str(lighter_res)}. Bybit position was closed for safety.")

        return results
    
    async def emergency_close_both_sides(self, symbol: str, lighter_amount: float, bybit_amount: float, lighter_is_long: bool):
        log.info("emergency_close_triggered", symbol=symbol, lighter_amt=lighter_amount, bybit_amt=bybit_amount)
        
        tasks = []
        try:
            if lighter_amount > 0 and hasattr(self, 'lighter'):
                close_lighter_ask = lighter_is_long
                
                tasks.append(self.lighter.place_market_order(
                    symbol=symbol, 
                    amount=lighter_amount, 
                    is_ask=close_lighter_ask, 
                    reduce_only=True
                ))

            if bybit_amount > 0 and hasattr(self, 'bybit'):
                close_bybit_ask = not lighter_is_long
                bybit_side = "Sell" if close_bybit_ask else "Buy"
                
                tasks.append(self.bybit.place_market_order(
                    symbol=symbol, 
                    amount=bybit_amount, 
                    side=bybit_side,
                    reduce_only=True 
                ))

            if not tasks:
                return {"status": "failed", "error": "No tasks created. Missing Lighter or Bybit instance."}

            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "status": "success", 
                "results": [str(r) for r in results]
            }
            
        except Exception as e:
            for task in tasks:
                if hasattr(task, 'close'):
                    task.close()
            log.error("emergency_close_failed", error=str(e))
            return {"status": "failed", "error": f"Execution setup failed: {e}"}
        

    async def emergency_close_auto(self, symbol: str):
        log.info("emergency_close_auto_started", symbol=symbol)
        
        try:
            lighter_amount = 0.0
            lighter_is_long = True
            
            if hasattr(self, 'lighter') and hasattr(self.lighter, 'get_position'):
                lighter_pos = await self.lighter.get_position(symbol)
                lighter_amount = lighter_pos.get('amount', 0.0)
                lighter_is_long = lighter_pos.get('is_long', True)
            else:
                log.warning("lighter_get_position_missing", message="Please implement get_position in LighterClient")

            bybit_amount = 0.0
            bybit_is_long = False
            
            if hasattr(self, 'bybit') and hasattr(self.bybit, 'get_position'):
                bybit_pos = await self.bybit.get_position(symbol)
                bybit_amount = bybit_pos.get('amount', 0.0)
                bybit_is_long = bybit_pos.get('is_long', False)
            else:
                log.warning("bybit_get_position_missing", message="Please implement get_position in BybitClient")

            if lighter_amount <= 0 and bybit_amount <= 0:
                return {"status": "success", "detail": f"No open positions found for {symbol}."}

            log.info("auto_close_amounts_found", lighter=lighter_amount, bybit=bybit_amount)

            return await self.emergency_close_both_sides(
                symbol=symbol,
                lighter_amount=lighter_amount,
                bybit_amount=bybit_amount,
                lighter_is_long=lighter_is_long
            )

        except Exception as e:
            log.error("emergency_close_auto_failed", error=str(e))
            return {"status": "failed", "error": f"Auto-close failed: {str(e)}"}