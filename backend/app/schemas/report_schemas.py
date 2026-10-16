"""
MODULE 10 - VERIFICATION REPORT SCHEMAS
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class VerificationReportResponse(BaseModel):
    id: str
    certificate_id: str
    verification_id: str
    pdf_path: Optional[str] = None
    digital_signature: Optional[str] = None
    generated_at: datetime

    class Config:
        from_attributes = True


# ---- Dashboard Stats ----

class PredictionDistribution(BaseModel):
    genuine: int = 0
    suspicious: int = 0
    fake: int = 0
    inconclusive: int = 0
    not_run: int = 0


class RecentCertificate(BaseModel):
    id: str
    original_filename: str
    file_type: str
    uploaded_at: datetime
    trust_score: Optional[float] = None
    ocr_accuracy: Optional[float] = None
    prediction_label: Optional[str] = None
    fraud_probability: Optional[float] = None
    has_report: bool = False
    verification_id: Optional[str] = None


class TimelineEvent(BaseModel):
    certificate_id: str
    filename: str
    event: str          # "uploaded" | "ocr" | "verified" | "predicted" | "report"
    timestamp: datetime
    label: Optional[str] = None


class DashboardStatsResponse(BaseModel):
    total_certificates: int
    avg_trust_score: Optional[float] = None
    prediction_distribution: PredictionDistribution
    recent_certificates: list[RecentCertificate]
    timeline: list[TimelineEvent]
    total_reports_generated: int
    avg_ocr_accuracy: Optional[float] = None
    avg_fraud_probability: Optional[float] = None
    # Priority 8 — new additive fields
    duplicate_count: int = 0
    tampered_count: int = 0
    qr_verified_count: int = 0
    blockchain_verified_count: int = 0
    doc_type_distribution: dict = {}           # {"aadhaar": 3, "degree": 7, ...}
