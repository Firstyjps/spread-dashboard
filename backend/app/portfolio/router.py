"""
Portfolio API routes.

GET /api/v1/portfolio          — full snapshot (all exchanges)
GET /api/v1/portfolio?exchange=bybit — single exchange
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.portfolio.service import fetch_portfolio_snapshot
from app.storage.database import get_portfolio_history

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["portfolio"])


@router.get("/portfolio")
async def get_portfolio(
    exchange: Optional[str] = Query(None, description="Filter by exchange name"),
    account: str = Query("manual", description="Account type: 'manual' or 'ai'")
):
    """Fetch unified portfolio snapshot across all exchanges."""
    try:
        exchanges = [exchange] if exchange else None
        snapshot = await fetch_portfolio_snapshot(exchanges=exchanges, account=account)
        return snapshot.to_dict()
    except Exception as e:
        log.error("portfolio_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/history")
async def get_history(
    account: str = Query("manual", description="Account type: 'manual' or 'ai'"),
    days: int = Query(30, description="Number of days to fetch")
):
    """Fetch portfolio historical snapshot data."""
    try:
        limit = days * 24 # 24 hours per day, 1 snapshot per hour
        history = await get_portfolio_history(account=account, limit=limit)
        return history
    except Exception as e:
        log.error("portfolio_history_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
