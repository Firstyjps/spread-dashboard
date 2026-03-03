from fastapi import APIRouter, HTTPException
from app.config.settings import settings
from app.services.executor import ArbitrageExecutor
from pydantic import BaseModel

# Iceberg + Rate Limiter exports
from app.execution.iceberg_executor import (  # noqa: F401
    execute_iceberg, IcebergConfig, IcebergResult, PricePolicy, Urgency,
)
from app.execution.rate_limiter import (  # noqa: F401
    TokenBucketRateLimiter, RateLimiterConfig,
)

router = APIRouter()

class TradeRequest(BaseModel):
    symbol: str
    side: str
    amount: float

@router.post("/execute")
async def execute_trade(req: TradeRequest):
    executor = ArbitrageExecutor(settings)
    
    try:
        results = await executor.run_arb(req.symbol, req.side, req.amount)
        
        for res in results:
            if isinstance(res, Exception):
                raise HTTPException(status_code=500, detail=f"Execution Failed: {str(res)}")
                
        return {
            "status": "success", 
            "detail": f"Atomic Arb triggered for {req.symbol}",
            "results": str(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))