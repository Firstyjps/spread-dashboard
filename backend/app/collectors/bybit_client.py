from pybit.unified_trading import HTTP

class BybitClient:
    def __init__(self, config):
        self.session = HTTP(
            testnet=False,
            api_key=config.bybit_api_key,
            api_secret=config.bybit_api_secret,
            domain="bytick"
        )

    async def place_market_order(self, symbol, amount, side: str, reduce_only: bool = False):
        response = self.session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(amount),
            timeInForce="IOC",
            reduceOnly=reduce_only
        )
        return response