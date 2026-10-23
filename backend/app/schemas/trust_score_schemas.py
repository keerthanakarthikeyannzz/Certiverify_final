from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class TrustComponentBreakdown(BaseModel):
    component: str
    label: str
    value: Optional[float] = None
    weight: float
    contribution: float
    status: str                                             # PASS | WARN | FAIL | not evaluated
    reason: str


class TrustScoreResponse(BaseModel):
    id: str
    certificate_id: str
    score: float
    band: Optional[str] = "HIGH"                            # HIGH | MEDIUM | LOW
    band_label: Optional[str] = "High Trust"
    coverage: Optional[float] = 1.0                         # 0.0 - 1.0 (e.g. 0.75)
    coverage_percentage: Optional[float] = 100.0            # 0.0 - 100.0 (e.g. 75.0)
    checks_evaluated: Optional[int] = 8
    checks_total: Optional[int] = 8
    components: Optional[list[TrustComponentBreakdown]] = None
    breakdown: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
