"""
MODULE 3 - AI DOCUMENT TYPE IDENTIFICATION API

POST /{certificate_id}/classify  -> runs the classifier, persists + returns result
GET  /{certificate_id}/document-type -> returns the last stored classification
"""
from fastapi import APIRouter, Depends, HTTPException, status
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, Certificate, DocumentType, OCRData
from app.schemas.document_type_schemas import ClassifyResponse, DocumentTypeResponse
from app.services.storage_service import get_storage_backend
from app.services.document_classifier import classify
from app.api.deps import get_current_verified_user

router = APIRouter(prefix="/api/v1/certificates", tags=["Document Type Identification"])


@router.post("/{certificate_id}/classify", response_model=ClassifyResponse)
@router.post("/{certificate_id}/classify-document", response_model=ClassifyResponse, include_in_schema=False)
async def classify_certificate(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    # Check if OCR has already run on this certificate
    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result.scalar_one_or_none()

    try:
        if ocr_row and ocr_row.raw_text:
            from app.services.document_classifier import classify_from_text
            result = await asyncio.to_thread(classify_from_text, ocr_row.raw_text, cert.original_filename)
        else:
            storage = get_storage_backend()
            file_bytes = await storage.read(cert.storage_path)
            result = await asyncio.to_thread(classify, file_bytes, cert.file_type)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not classify this document: {e}",
        )

    # Upsert: a certificate can be re-classified (e.g. after re-upload)
    existing = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
    doc_type_row = existing.scalar_one_or_none()

    if doc_type_row:
        doc_type_row.predicted_type = result.predicted_type
        doc_type_row.confidence_score = result.confidence
        doc_type_row.model_used = result.model_used
    else:
        doc_type_row = DocumentType(
            certificate_id=cert.id,
            predicted_type=result.predicted_type,
            confidence_score=result.confidence,
            model_used=result.model_used,
        )
        db.add(doc_type_row)

    await db.commit()
    await db.refresh(doc_type_row)

    return ClassifyResponse(
        id=doc_type_row.id,
        certificate_id=doc_type_row.certificate_id,
        predicted_type=doc_type_row.predicted_type.value,
        confidence_score=doc_type_row.confidence_score,
        model_used=doc_type_row.model_used,
        created_at=doc_type_row.created_at,
        signals=result.signals,
    )


@router.get("/{certificate_id}/document-type", response_model=DocumentTypeResponse)
async def get_document_type(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
    doc_type_row = result.scalar_one_or_none()
    if not doc_type_row:
        raise HTTPException(status_code=404, detail="This certificate has not been classified yet.")

    return DocumentTypeResponse(
        id=doc_type_row.id,
        certificate_id=doc_type_row.certificate_id,
        predicted_type=doc_type_row.predicted_type.value,
        confidence_score=doc_type_row.confidence_score,
        model_used=doc_type_row.model_used,
        created_at=doc_type_row.created_at,
    )


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id, Certificate.owner_id == user.id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    return cert
