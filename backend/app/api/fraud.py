import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, Certificate, OCRData, DocumentComparison, VerificationResult, FraudAnalysis, DocumentType
from app.schemas.fraud_schemas import FraudAnalysisResponse
from app.services.fraud_analysis import compute_fraud_analysis, FraudFactorInputs
from app.services.image_quality import compute_image_quality_score
from app.services.tampering_detection import check_metadata
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array
from app.api.deps import get_current_verified_user

router = APIRouter(prefix="/api/v1/certificates", tags=["Fraud Analysis"])

# Expected fields per OCR row for field_extraction_completeness
_OCR_TRACKABLE_FIELDS = [
    "student_name", "university_name", "register_number", "roll_number",
    "certificate_number", "department", "course", "cgpa", "percentage", "date_of_issue",
]



def _compute_field_completeness(ocr_row: OCRData | None) -> float | None:
    """Return fraction of tracked OCR fields that are non-None/non-empty."""
    if ocr_row is None:
        return None
    detected = sum(
        1 for f in _OCR_TRACKABLE_FIELDS
        if getattr(ocr_row, f, None) not in (None, "", 0)
    )
    return round(detected / len(_OCR_TRACKABLE_FIELDS), 4)


@router.post("/{certificate_id}/analyze-fraud", response_model=FraudAnalysisResponse)
async def run_fraud_analysis(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result.scalar_one_or_none()

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
    doc_type_row = doc_type_result.scalar_one_or_none()

    comparison_row = None
    if cert.group_id:
        comparison_result = await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id == cert.group_id)
        )
        comparison_row = comparison_result.scalar_one_or_none()

    verification_result = await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id == cert.id)
    )
    verification_row = verification_result.scalar_one_or_none()

    storage = get_storage_backend()
    file_bytes = await storage.read(cert.storage_path)
    image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)

    # ── Read image quality from stored tampering_detail if available ──────────
    # Avoids re-loading the file when tampering analysis has already run.
    stored_detail = (verification_row.tampering_detail or {}) if verification_row else {}
    stored_iq = stored_detail.get("image_quality", {})
    if stored_iq and stored_iq.get("score") is not None:
        image_quality_score = float(stored_iq["score"])
    else:
        image_quality_score = await asyncio.to_thread(compute_image_quality_score, image)

    # ── Derive text_consistency_score from stored font/text analysis ──────────
    # font_consistency.score is 0-100 (high = consistent); normalize to 0-1.
    # Also blend with text_analysis score when available.
    stored_font = stored_detail.get("font_consistency", {})
    stored_text = stored_detail.get("text_analysis", {})
    if stored_font.get("score") is not None:
        font_s = float(stored_font["score"]) / 100.0
        text_s = float(stored_text.get("score", stored_font["score"])) / 100.0
        text_consistency_score = round((font_s + text_s) / 2.0, 4)
    else:
        text_consistency_score = None

    # ── Derive duplicate type + same_owner from stored duplicate_detail ────────
    stored_dup_detail = {}
    if verification_row and getattr(verification_row, "duplicate_detail", None):
        stored_dup_detail = verification_row.duplicate_detail or {}
    dup_type = stored_dup_detail.get("duplicate_type") or None
    dup_status = stored_dup_detail.get("duplicate_status") or None
    dup_same_owner = stored_dup_detail.get("same_owner") if stored_dup_detail else None

    metadata_flags = await asyncio.to_thread(check_metadata, file_bytes, cert.file_type)

    inputs = FraudFactorInputs(
        # Existing signals
        ocr_accuracy=ocr_row.ocr_accuracy if ocr_row else None,
        comparison_consistency_pct=comparison_row.consistency_percentage if comparison_row else None,
        qr_present=verification_row.qr_present if verification_row else None,
        qr_valid=verification_row.qr_valid if verification_row else None,
        blockchain_status=verification_row.blockchain_status if verification_row else None,
        tampering_score=verification_row.tampering_score if verification_row else None,
        tampering_risk_level=verification_row.tampering_risk_level if verification_row else None,
        is_duplicate=verification_row.is_duplicate if verification_row else None,
        metadata_flags_present=len(metadata_flags) > 0,
        image_quality_score=image_quality_score,
        # New signals
        doc_classification_confidence=(
            doc_type_row.confidence_score if doc_type_row else None
        ),
        field_extraction_completeness=_compute_field_completeness(ocr_row),
        text_consistency_score=text_consistency_score,          # from tampering_detail
        signature_present=ocr_row.has_signature if ocr_row else None,
        seal_present=ocr_row.has_seal if ocr_row else None,
        # Priority 7 — duplicate type context
        duplicate_type=dup_type,
        duplicate_status=dup_status,
        duplicate_same_owner=dup_same_owner,
    )

    result = await asyncio.to_thread(compute_fraud_analysis, inputs)

    existing = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id))
    fraud_row = existing.scalar_one_or_none()
    if fraud_row is None:
        fraud_row = FraudAnalysis(certificate_id=cert.id)
        db.add(fraud_row)

    fraud_row.fraud_probability      = result.fraud_probability
    fraud_row.ocr_accuracy_weight    = result.factor_weights.get("ocr_accuracy", 0.0)
    fraud_row.comparison_weight      = result.factor_weights.get("comparison", 0.0)
    fraud_row.qr_weight              = result.factor_weights.get("qr", 0.0)
    fraud_row.blockchain_weight      = result.factor_weights.get("blockchain", 0.0)
    fraud_row.tampering_weight       = result.factor_weights.get("tampering", 0.0)
    fraud_row.duplicate_weight       = result.factor_weights.get("duplicate", 0.0)
    fraud_row.metadata_integrity_weight = result.factor_weights.get("metadata_integrity", 0.0)
    fraud_row.image_quality_weight   = result.factor_weights.get("image_quality", 0.0)

    await db.commit()
    await db.refresh(fraud_row)

    # Derive risk_level label from fraud_probability for UI display
    fp = result.fraud_probability
    if fp >= 0.75:
        risk_level = "VERY_HIGH"
    elif fp >= 0.50:
        risk_level = "HIGH"
    elif fp >= 0.25:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    # Build response and inject computed-only fields (not persisted to DB columns)
    response = FraudAnalysisResponse.model_validate(fraud_row)
    response.risk_level = risk_level
    response.factor_risks = result.factor_risks
    response.critical_overrides_applied = result.critical_overrides_applied
    return response


@router.get("/{certificate_id}/fraud-analysis", response_model=FraudAnalysisResponse)
async def get_fraud_analysis(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id))
    fraud_row = result.scalar_one_or_none()
    if not fraud_row:
        raise HTTPException(status_code=404, detail="No fraud analysis has been run on this certificate yet.")
    return fraud_row


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")

    from app.api.deps import verify_tenant_access
    verify_tenant_access(user, cert.organization_id, cert.owner_id)
    return cert
