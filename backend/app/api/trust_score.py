import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    User, Certificate, OCRData, DocumentComparison, VerificationResult,
    FraudAnalysis, TrustScore, DocumentType,
)
from app.schemas.trust_score_schemas import TrustScoreResponse
from app.services.trust_score import compute_trust_score, TrustScoreInputs
from app.services.image_quality import compute_image_quality_score
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array
from app.api.deps import get_current_verified_user

router = APIRouter(prefix="/api/v1/certificates", tags=["Trust Score"])

_OCR_TRACKABLE_FIELDS = [
    "student_name", "university_name", "register_number", "roll_number",
    "certificate_number", "department", "course", "cgpa", "percentage", "date_of_issue",
]


def _compute_field_completeness(ocr_row: OCRData | None) -> float | None:
    if ocr_row is None:
        return None
    detected = sum(
        1 for f in _OCR_TRACKABLE_FIELDS
        if getattr(ocr_row, f, None) not in (None, "", 0)
    )
    return round(detected / len(_OCR_TRACKABLE_FIELDS), 4)


@router.post("/{certificate_id}/compute-trust-score", response_model=TrustScoreResponse)
async def run_trust_score(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id).order_by(OCRData.id.desc()))
    ocr_row = ocr_result.scalars().first()

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id).order_by(DocumentType.id.desc()))
    doc_type_row = doc_type_result.scalars().first()

    comparison_row = None
    if cert.group_id:
        comparison_result = await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id == cert.group_id).order_by(DocumentComparison.id.desc())
        )
        comparison_row = comparison_result.scalars().first()

    verification_result = await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc())
    )
    verification_row = verification_result.scalars().first()

    fraud_result = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id).order_by(FraudAnalysis.id.desc()))
    fraud_row = fraud_result.scalars().first()

    storage = get_storage_backend()
    file_bytes = await storage.read(cert.storage_path)
    image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)
    image_quality_score = await asyncio.to_thread(compute_image_quality_score, image)

    dup_detail = (verification_row.duplicate_detail or {}) if verification_row else {}
    dup_status = dup_detail.get("duplicate_status")
    dup_same_owner = dup_detail.get("same_owner")
    dup_type = dup_detail.get("duplicate_type")

    inputs = TrustScoreInputs(
        ocr_accuracy=ocr_row.ocr_accuracy if ocr_row else None,
        image_quality_score=image_quality_score,
        document_consistency_pct=comparison_row.consistency_percentage if comparison_row else None,
        blockchain_status=verification_row.blockchain_status if verification_row else None,
        qr_present=verification_row.qr_present if verification_row else None,
        qr_valid=verification_row.qr_valid if verification_row else None,
        tampering_score=verification_row.tampering_score if verification_row else None,
        tampering_status=verification_row.tampering_status if verification_row else None,
        is_duplicate=verification_row.is_duplicate if verification_row else None,
        duplicate_status=dup_status,
        duplicate_same_owner=dup_same_owner,
        duplicate_type=dup_type,
        fraud_probability=fraud_row.fraud_probability if fraud_row else None,
        # New signals
        doc_classification_confidence=(
            doc_type_row.confidence_score if doc_type_row else None
        ),
        field_extraction_completeness=_compute_field_completeness(ocr_row),
    )

    result = compute_trust_score(inputs)

    existing = await db.execute(select(TrustScore).where(TrustScore.certificate_id == cert.id).order_by(TrustScore.id.desc()))
    trust_row = existing.scalars().first()
    if trust_row is None:
        trust_row = TrustScore(certificate_id=cert.id)
        db.add(trust_row)

    trust_row.score = result.score
    trust_row.breakdown = {
        "weights": result.breakdown,
        "factor_trust_values": result.factor_trust_values,
        "evidence_breakdown": result.evidence_breakdown,
    }

    await db.commit()
    await db.refresh(trust_row)
    return trust_row


@router.get("/{certificate_id}/trust-score", response_model=TrustScoreResponse)
async def get_trust_score(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(TrustScore).where(TrustScore.certificate_id == cert.id).order_by(TrustScore.id.desc()))
    trust_row = result.scalars().first()
    if not trust_row:
        raise HTTPException(status_code=404, detail="No trust score has been computed for this certificate yet.")
    return trust_row


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id, Certificate.owner_id == user.id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    return cert
