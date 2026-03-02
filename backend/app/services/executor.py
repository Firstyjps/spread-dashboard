"""
Arbitrage Executor — sends orders to Lighter + Bybit simultaneously.

Bybit side uses Smart Maker Engine (PostOnly LIMIT) to save ~63% on fees.
Lighter side stays MARKET (L2 DEX, different fee model).

Safety: if one side fails, the other is immediately reversed.
Cleanup: client resources are properly closed after each execution.
"""
import asyncio
import structlog
from decimal import Decimal
from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.execution.maker_engine import smart_execute_maker, MakerConfig

log = structlog.get_logger()


def _build_maker_config(config) -> MakerConfig:
    """Build MakerConfig from app settings."""
    return MakerConfig(
        max_time_s=getattr(config, "maker_max_time_s", 15.0),
        reprice_interval_ms=getattr(config, "maker_reprice_interval_ms", 800),
        max_reprices=getattr(config, "maker_max_reprices", 8),
        aggressiveness=getattr(config, "maker_aggressiveness", "BALANCED"),
        allow_market_fallback=getattr(config, "maker_allow_market_fallback", True),
        maker_fee_rate=getattr(config, "maker_fee_rate", 0.0002),
        taker_fee_rate=getattr(config, "taker_fee_rate", 0.00055),
        spread_guard_ticks=getattr(config, "maker_spread_guard_ticks", 1),
        vol_window=getattr(config, "maker_vol_window", 20),
        vol_limit_ticks=getattr(config, "maker_vol_limit_ticks", 10),
        max_deviation_ticks=getattr(config, "maker_max_deviation_ticks", 50),
    )


class ArbitrageExecutor:
    def __init__(self, config):
        self.lighter = LighterClient(config)
        self.bybit = BybitClient(config)
        self.maker_config = _build_maker_config(config)

    async def run_arb(self, symbol: str, strategy_side: str, amount: float):
        """Execute arb: Lighter MARKET + Bybit Smart Maker (PostOnly LIMIT).

        Bybit uses maker engine for lower fees (0.02% vs 0.055% taker).
        If Lighter fails but Bybit succeeds, Bybit is reversed for safety.
        """
        log.info("arb_execution_start", side=strategy_side, symbol=symbol, amount=amount)

        try:
            if strategy_side == "BUY_LIGHTER_SELL_BYBIT":
                lighter_task = self.lighter.place_market_order(symbol, amount, is_ask=False)
                bybit_side = "Sell"
            else:
                lighter_task = self.lighter.place_market_order(symbol, amount, is_ask=True)
                bybit_side = "Buy"

            # Execute Lighter MARKET + Bybit Maker concurrently
            bybit_task = smart_execute_maker(
                client=self.bybit,
                symbol=symbol,
                side=bybit_side,
                target_qty=Decimal(str(amount)),
                config=self.maker_config,
            )

            results = await asyncio.gather(lighter_task, bybit_task, return_exceptions=True)

            lighter_res = results[0]
            bybit_res = results[1]

            # Check for failures
            lighter_failed = isinstance(lighter_res, Exception)
            bybit_failed = isinstance(bybit_res, Exception)

            # Maker engine returns MakerResult (not exception) even on abort
            if not bybit_failed and hasattr(bybit_res, "status") and bybit_res.status == "aborted":
                bybit_failed = True
                bybit_res = Exception(f"Maker engine aborted: {bybit_res.detail}")

            if lighter_failed and not bybit_failed:
                log.warning("arb_mismatch_lighter_failed", error=str(lighter_res))
                reverse_side = "Buy" if strategy_side == "SELL_LIGHTER_BUY_BYBIT" else "Sell"
                try:
                    await self.bybit.place_market_order(symbol, amount, side=reverse_side)
                except Exception as rev_err:
                    log.error("arb_reversal_failed", error=str(rev_err))
                raise Exception(
                    f"Lighter failed: {lighter_res}. Bybit position was reversed for safety."
                )

            if bybit_failed and not lighter_failed:
                log.warning("arb_mismatch_bybit_failed", error=str(bybit_res))
                # Reverse Lighter
                try:
                    await self.lighter.place_market_order(
                        symbol, amount, is_ask=(strategy_side == "BUY_LIGHTER_SELL_BYBIT"),
                        reduce_only=True,
                    )
                except Exception as rev_err:
                    log.error("arb_reversal_lighter_failed", error=str(rev_err))
                raise Exception(
                    f"Bybit failed: {bybit_res}. Lighter position was reversed for safety."
                )

            if lighter_failed and bybit_failed:
                raise Exception(
                    f"Both exchanges failed! Lighter: {lighter_res} | Bybit: {bybit_res}"
                )

            # Log maker engine telemetry
            if hasattr(bybit_res, "to_dict"):
                log.info("arb_bybit_maker_result", **bybit_res.to_dict())

            log.info("arb_execution_success", lighter=str(lighter_res), bybit=str(bybit_res))
            return results

        finally:
            await self._cleanup()

    async def emergency_close_both_sides(
        self, symbol: str, lighter_amount: float, bybit_amount: float, lighter_is_long: bool
    ):
        """Close positions on both exchanges."""
        log.info(
            "emergency_close_triggered",
            symbol=symbol,
            lighter_amt=lighter_amount,
            bybit_amt=bybit_amount,
        )

        tasks = []
        try:
            if lighter_amount > 0:
                # Close lighter: if long, sell (is_ask=True); if short, buy (is_ask=False)
                tasks.append(
                    self.lighter.place_market_order(
                        symbol=symbol,
                        amount=lighter_amount,
                        is_ask=lighter_is_long,
                        reduce_only=True,
                    )
                )

            if bybit_amount > 0:
                # Close bybit: opposite side of lighter
                bybit_side = "Sell" if not lighter_is_long else "Buy"
                tasks.append(
                    self.bybit.place_market_order(
                        symbol=symbol,
                        amount=bybit_amount,
                        side=bybit_side,
                        reduce_only=True,
                    )
                )

            if not tasks:
                return {"status": "success", "detail": "No positions to close."}

            results = await asyncio.gather(*tasks, return_exceptions=True)

            errors = [str(r) for r in results if isinstance(r, Exception)]
            if errors:
                return {
                    "status": "partial",
                    "detail": f"Some closes failed: {'; '.join(errors)}",
                    "results": [str(r) for r in results],
                }

            return {
                "status": "success",
                "detail": "All positions closed.",
                "results": [str(r) for r in results],
            }

        except Exception as e:
            log.error("emergency_close_failed", error=str(e))
            return {"status": "failed", "error": f"Close failed: {e}"}

        finally:
            await self._cleanup()

    async def emergency_close_auto(self, symbol: str):
        """Auto-detect positions and close them all."""
        log.info("emergency_close_auto_started", symbol=symbol)

        try:
            lighter_pos = await self.lighter.get_position(symbol)
            lighter_amount = lighter_pos.get("amount", 0.0)
            lighter_is_long = lighter_pos.get("is_long", True)

            bybit_pos = await self.bybit.get_position(symbol)
            bybit_amount = bybit_pos.get("amount", 0.0)

            if lighter_amount <= 0 and bybit_amount <= 0:
                return {"status": "success", "detail": f"No open positions found for {symbol}."}

            log.info(
                "auto_close_amounts_found",
                lighter=lighter_amount,
                lighter_is_long=lighter_is_long,
                bybit=bybit_amount,
            )

            return await self.emergency_close_both_sides(
                symbol=symbol,
                lighter_amount=lighter_amount,
                bybit_amount=bybit_amount,
                lighter_is_long=lighter_is_long,
            )

        except Exception as e:
            log.error("emergency_close_auto_failed", error=str(e))
            return {"status": "failed", "error": f"Auto-close failed: {str(e)}"}

    async def _cleanup(self):
        """Clean up client resources."""
        try:
            await self.lighter.close()
        except Exception:
            pass
