from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class VerificationSummary(BaseModel):
    document_type_identified: bool
    ocr_extracted: bool
    document_comparison_run: bool
    qr_checked: bool
    blockchain_checked: bool
    tampering_checked: bool
    duplicate_checked: bool
    fraud_analyzed: bool
    trust_score_computed: bool


class FinalPredictionResponse(BaseModel):
    id: str
    certificate_id: str
    label: str
    confidence_score: float
    explanation: str
    recommended_action: str
    # Enhanced fields (Optional for backward compatibility with stored rows
    # that pre-date this enhancement and don't yet have these columns)
    fraud_probability: Optional[float] = None
    evidence: Optional[dict[str, Any]] = None      # per-factor status breakdown
    reasons: Optional[list[str]] = None            # human-readable bullet list
    verification_summary: Optional[VerificationSummary] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CertificateReviewRequest(BaseModel):
    verdict: str  # "genuine" | "suspicious" | "fake"
    review_note: Optional[str] = None


class CertificateReviewResponse(BaseModel):
    certificate_id: str
    verdict: str
    review_note: Optional[str] = None
    confidence_score: float
    explanation: str
    updated_at: datetime

    class Config:
        from_attributes = True

