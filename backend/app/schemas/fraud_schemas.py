from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class SignalContribution(BaseModel):
    signal: str
    label: str
    is_active: bool
    nominal_weight: float
    effective_weight: float
    risk: Optional[float] = None
    contribution: float = 0.0
    status: str                                             # CLEAN | WARNING | CRITICAL | NOT_APPLICABLE
    details: str


class FraudAnalysisResponse(BaseModel):
    id: str
    certificate_id: str
    fraud_probability: float

    # Per-factor effective weights (DB-persisted)
    ocr_accuracy_weight: float
    comparison_weight: float
    qr_weight: float
    blockchain_weight: float
    tampering_weight: float
    duplicate_weight: float
    metadata_integrity_weight: float
    image_quality_weight: float

    # Rich analysis fields — computed at request time, explainable for UI
    risk_level: Optional[str] = None                        # LOW | MODERATE | HIGH | VERY_HIGH
    factor_risks: Optional[dict[str, float]] = None         # raw 0-1 risk per factor
    signal_contributions: Optional[list[SignalContribution]] = None
    critical_overrides_applied: Optional[list[str]] = None  # hard floor labels that fired
    image_quality_details: Optional[dict[str, Any]] = None

    created_at: datetime

    class Config:
        from_attributes = True

