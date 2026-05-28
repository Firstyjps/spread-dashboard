"""Shared trade journal write path."""
import structlog

from app.metrics import TRADES_TOTAL
from app.models import TradeRecord
from app.storage.database import insert_trade, commit as db_commit

log = structlog.get_logger()


async def record_trade(trade: TradeRecord, *, commit: bool = True) -> None:
    """Insert a trade row and update execution metrics."""
    try:
        await insert_trade(trade)
        if commit:
            await db_commit()
        TRADES_TOTAL.labels(symbol=trade.symbol, status=trade.status).inc()
    except Exception as e:
        log.error("trade_record_insert_failed", error=str(e), symbol=trade.symbol, status=trade.status)
