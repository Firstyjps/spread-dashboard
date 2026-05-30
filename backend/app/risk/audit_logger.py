from __future__ import annotations

from app.risk.database import insert_audit_record, query_audit_records
from app.risk.models import RiskEvaluation


class RiskAuditLogger:
    async def log(self, evaluation: RiskEvaluation) -> None:
        await insert_audit_record(evaluation.to_dict())

    async def query(
        self,
        *,
        symbol: str | None = None,
        decision_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        return await query_audit_records(
            symbol=symbol,
            decision_type=decision_type,
            page=page,
            page_size=page_size,
        )
