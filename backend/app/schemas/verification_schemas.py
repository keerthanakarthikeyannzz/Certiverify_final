from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class VerificationResultResponse(BaseModel):
    id: str
    certificate_id: str

    # QR Check
    qr_present: bool
    qr_decoded_data: Optional[dict] = None
    qr_valid: Optional[bool] = None
    qr_warning: Optional[str] = None
    qr_status: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None

    # Blockchain Verification
    blockchain_hash_submitted: Optional[str] = None
    blockchain_hash_onchain: Optional[str] = None
    blockchain_match: Optional[bool] = None
    blockchain_tx_hash: Optional[str] = None
    blockchain_status: Optional[str] = None

    # Hash Consistency (fresh hash vs stored hash at verify time)
    hash_match_status: Optional[str] = None          # MATCH | MISMATCH | NOT_REGISTERED

    # Tampering Detection
    tampering_score: Optional[float] = None
    tampering_flags: Optional[list] = None
    ela_heatmap_path: Optional[str] = None
    tampering_risk_level: Optional[str] = None       # LOW | MINOR_ANOMALIES | MODERATE_RISK | HIGH_RISK | VERY_HIGH_RISK
    tampering_confidence: Optional[float] = None     # 0-100 overall detection confidence
    tampering_status: Optional[str] = None           # analyzed | not_applicable_for_pdf_text_layer | failed: <reason> | unavailable
    tampering_detail: Optional[dict[str, Any]] = None  # full structured result JSON

    # Duplicate Detection
    is_duplicate: bool = False
    duplicate_of_certificate_id: Optional[str] = None
    duplicate_match_reason: Optional[str] = None
    duplicate_status: Optional[str] = None
    duplicate_detail: Optional[dict] = None   # full structured duplicate result (Priority 7)

    # Cross-Validation (QR data vs OCR fields vs DB record)
    cross_validation_status: Optional[str] = None         # CONSISTENT | MISMATCH | PARTIAL | UNAVAILABLE
    cross_validation_mismatches: Optional[list[dict]] = None  # [{field, qr_value, ocr_value}]

    created_at: datetime

    class Config:
        from_attributes = True
