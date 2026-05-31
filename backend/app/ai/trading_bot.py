import asyncio
import time
import structlog
from app.config.settings import settings
from app.ai.models.xgboost_inference import SpreadPredictor
from app.services.executor import ArbitrageExecutor
from app.alerts.alert_engine import send_system_alert
from app.analytics.spread_engine import compute_spread

log = structlog.get_logger()

class AITradingDaemon:
    def __init__(self):
        # Initialize the AI Model
        import os
        model_dir = os.path.join(os.path.dirname(__file__), 'models')
        self.predictor = SpreadPredictor(model_dir=model_dir)
        
        self.active_trades = 0
        self.last_trade_time = 0
        self.cooldown_s = 60 # Cooldown between AI trades
        
        # Load config
        self.trade_size_usd = settings.ai_trade_size_usd
        self.max_trades = settings.ai_max_open_trades
        self.threshold_bps = settings.ai_profit_threshold_bps
        self.is_dry_run = settings.risk_dry_run_enabled

    async def run_forever(self):
        log.info("ai_trading_daemon_started", 
                 dry_run=self.is_dry_run, 
                 trade_size=self.trade_size_usd,
                 threshold=self.threshold_bps)
                 
        await send_system_alert("ai_daemon_started", "AI Trading Daemon has started. Dry Run: " + str(self.is_dry_run))
        
        while True:
            try:
                await self.tick()
            except Exception as e:
                log.error("ai_daemon_error", error=str(e))
            await asyncio.sleep(1) # Evaluate every second

    async def tick(self):
        # Only support HYPEUSDT for now as the model is trained on it
        symbol = "HYPEUSDT"
        
        if self.active_trades >= self.max_trades:
            return # Reached max capacity
            
        if time.time() - self.last_trade_time < self.cooldown_s:
            return # Cooldown
            
        spread_data = compute_spread(symbol)
        if not spread_data:
            return
            
        # TODO: In a real system, you would calculate real-time features (rolling mean, zscore)
        # For MVP Phase 4, we use dummy features to simulate the pipeline since real-time rolling 
        # features require a windowed cache of the last 7200 ticks.
        # This will be replaced by the actual real-time cache in production.
        dummy_features = {
            'exchange_spread_mid': float(spread_data.exchange_spread_mid),
            'spread': float(spread_data.best_spread_usd), # approximating
            'mean_10': float(spread_data.best_spread_usd),
            'std_10': 0.0002,
            'zscore_10': 1.0,
            'min_10': float(spread_data.best_spread_usd) - 0.0005,
            'max_10': float(spread_data.best_spread_usd) + 0.0005,
            'dist_min_10': 0.0005,
            'dist_max_10': -0.0005,
            'mean_50': float(spread_data.best_spread_usd),
            'std_50': 0.0003,
            'zscore_50': 1.0,
            'min_50': float(spread_data.best_spread_usd) - 0.0010,
            'max_50': float(spread_data.best_spread_usd) + 0.0010,
            'dist_min_50': 0.0010,
            'dist_max_50': -0.0010,
            'mean_300': float(spread_data.best_spread_usd),
            'std_300': 0.0005,
            'zscore_300': 1.0,
            'min_300': float(spread_data.best_spread_usd) - 0.0015,
            'max_300': float(spread_data.best_spread_usd) + 0.0015,
            'dist_min_300': 0.0015,
            'dist_max_300': -0.0015,
            'roc_10': 0.0,
            'roc_50': 0.0
        }
        
        predicted_profit_bps = self.predictor.predict_short(dummy_features)
        
        if predicted_profit_bps >= self.threshold_bps:
            log.info("ai_signal_triggered", symbol=symbol, predicted_bps=predicted_profit_bps)
            await self.execute_trade(symbol, "SELL_BYBIT_BUY_LIGHTER", predicted_profit_bps)

    async def execute_trade(self, symbol: str, side: str, expected_profit: float):
        self.last_trade_time = time.time()
        
        if self.is_dry_run:
            msg = f"🔥 [DRY RUN] AI Signal: {side} on {symbol} | Expected: {expected_profit:.2f} bps | Size: ${self.trade_size_usd}"
            log.info("ai_dry_run_execute", message=msg)
            await send_system_alert("ai_signal_dry_run", msg)
            return

        msg = f"⚡ [LIVE] AI Executing: {side} on {symbol} | Expected: {expected_profit:.2f} bps | Size: ${self.trade_size_usd}"
        log.warning("ai_live_execute", message=msg)
        await send_system_alert("ai_signal_live", msg)
        
        # Determine actual coin amount based on USD size
        # Amount = TradeSizeUSD / CurrentPrice
        # For simplicity, we assume price is ~1.0 for HYPE, but we should fetch real price.
        # Hardcoding a tiny test amount 0.1 for safety if price isn't fetched
        amount_coin = 0.1 
        
        try:
            self.active_trades += 1
            async with ArbitrageExecutor(settings) as executor:
                await executor.run_arb(symbol, side, amount_coin)
            await send_system_alert("ai_trade_success", f"Successfully executed AI trade for {symbol}")
        except Exception as e:
            log.error("ai_execution_failed", error=str(e))
            await send_system_alert("ai_trade_failed", f"Failed to execute AI trade: {str(e)}", severity="critical")
        finally:
            self.active_trades -= 1

if __name__ == "__main__":
    daemon = AITradingDaemon()
    asyncio.run(daemon.run_forever())
