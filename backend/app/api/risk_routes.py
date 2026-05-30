from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.api.rate_limit import limiter
from app.risk import get_risk_engine
from app.risk.models import RISK_CONFIG_RANGES

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


class RiskConfigPatch(BaseModel):
    dry_run_enabled: bool | None = None
    max_position_per_symbol: float | None = None
    position_limits_override: dict[str, float] | None = None
    max_notional_exposure_usd: float | None = None
    max_order_rate_per_minute: int | None = None
    rate_limit_queue_timeout_s: float | None = None
    price_sanity_band_pct: float | None = None
    price_data_max_age_s: float | None = None
    kill_switch_loss_threshold_usd: float | None = None
    kill_switch_consecutive_failures: int | None = None
    kill_switch_feed_stale_s: float | None = None
    kill_switch_spread_inversion_pct: float | None = None
    kill_switch_spread_inversion_duration_s: float | None = None
    cooldown_minutes: float | None = None
    audit_retention_days: int | None = None
    confirm_live: bool = False


class KillSwitchRequest(BaseModel):
    reason: str = "manual kill switch"


class LossRecordRequest(BaseModel):
    pnl_usd: float
    reason: str = "manual loss record"


@router.get("/status")
async def risk_status() -> dict[str, Any]:
    return get_risk_engine().snapshot().to_dict()


@router.get("/config")
async def risk_config() -> dict[str, Any]:
    return {
        "config": get_risk_engine().config.to_dict(),
        "ranges": RISK_CONFIG_RANGES,
    }


@router.patch("/config", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def update_risk_config(request: Request, patch: RiskConfigPatch) -> dict[str, Any]:
    values = patch.model_dump(exclude_none=True)
    confirm_live = bool(values.pop("confirm_live", False))
    if values.get("dry_run_enabled") is False and not confirm_live:
        raise HTTPException(status_code=400, detail="confirm_live=true is required to disable dry-run mode")

    try:
        config = get_risk_engine().update_config(values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log.info("risk_config_updated", keys=list(values.keys()), dry_run=config.dry_run_enabled)
    return {"status": "ok", "config": config.to_dict()}


@router.post("/kill-switch/activate", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def activate_kill_switch(request: Request, body: KillSwitchRequest) -> dict[str, Any]:
    await get_risk_engine().activate_kill_switch(body.reason.strip() or "manual kill switch")
    return get_risk_engine().kill_switch.status()


@router.post("/kill-switch/reset", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def reset_kill_switch(request: Request) -> dict[str, Any]:
    await get_risk_engine().reset_kill_switch()
    return get_risk_engine().kill_switch.status()


@router.post("/loss", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def record_loss(request: Request, body: LossRecordRequest) -> dict[str, Any]:
    await get_risk_engine().record_loss(body.pnl_usd, body.reason)
    return get_risk_engine().snapshot().to_dict()


@router.get("/audit", dependencies=[Depends(require_api_key)])
async def risk_audit(
    symbol: str | None = Query(default=None),
    decision_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return await get_risk_engine().audit.query(
        symbol=symbol.upper() if symbol else None,
        decision_type=decision_type,
        page=page,
        page_size=page_size,
    )
