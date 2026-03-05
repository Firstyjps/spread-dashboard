"""
Bybit V5 LINEAR instrument info fetcher.

Fetches tick size, qty step, and min constraints for a symbol.
Uses asyncio.to_thread() to wrap pybit's synchronous HTTP call.
"""
import asyncio
import structlog
from dataclasses import dataclass
from decimal import Decimal

from app.utils.async_helpers import thread_with_timeout

log = structlog.get_logger()


@dataclass(frozen=True)
class InstrumentInfo:
    """Instrument constraints for a Bybit LINEAR perpetual."""
    symbol: str
    tick_size: Decimal        # price increment
    qty_step: Decimal         # quantity increment
    min_qty: Decimal          # minimum order quantity
    max_qty: Decimal          # maximum order quantity
    min_notional: Decimal     # minimum order value in USD (minNotionalValue)


async def fetch_instrument_info(session, symbol: str) -> InstrumentInfo:
    """Fetch instrument info from Bybit V5 API.

    Args:
        session: pybit HTTP session (unified_trading)
        symbol: e.g. "BTCUSDT"

    Returns:
        InstrumentInfo with tick/step/min constraints
    """
    try:
        resp = await thread_with_timeout(
            session.get_instruments_info,
            category="linear",
            symbol=symbol,
        )
    except asyncio.TimeoutError:
        raise Exception(f"Instrument info timed out for {symbol}")

    instruments = resp.get("result", {}).get("list", [])
    if not instruments:
        raise Exception(f"No instrument info for {symbol}")

    inst = instruments[0]
    price_filter = inst.get("priceFilter", {})
    lot_filter = inst.get("lotSizeFilter", {})

    return InstrumentInfo(
        symbol=symbol,
        tick_size=Decimal(price_filter.get("tickSize", "0.01")),
        qty_step=Decimal(lot_filter.get("qtyStep", "0.001")),
        min_qty=Decimal(lot_filter.get("minOrderQty", "0.001")),
        max_qty=Decimal(lot_filter.get("maxOrderQty", "100")),
        min_notional=Decimal(lot_filter.get("minNotionalValue", "5")),
    )
