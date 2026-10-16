from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


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

    # Rich analysis fields — computed at request time, not stored in DB columns
    # (populated by the POST /analyze-fraud endpoint via model_validate override)
    risk_level: Optional[str] = None                        # LOW | MODERATE | HIGH | VERY_HIGH
    factor_risks: Optional[dict[str, float]] = None         # raw 0-1 risk per factor
    critical_overrides_applied: Optional[list[str]] = None  # hard floor labels that fired

    created_at: datetime

    class Config:
        from_attributes = True
