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

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["portfolio"])


@router.get("/portfolio")
async def get_portfolio(exchange: Optional[str] = Query(None, description="Filter by exchange name")):
    """Fetch unified portfolio snapshot across all exchanges."""
    try:
        exchanges = [exchange] if exchange else None
        snapshot = await fetch_portfolio_snapshot(exchanges=exchanges)
        return snapshot.to_dict()
    except Exception as e:
        log.error("portfolio_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
