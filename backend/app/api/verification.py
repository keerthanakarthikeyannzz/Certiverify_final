"""
MODULE 6 - AI VERIFICATION MODULE (all four sub-engines)

POST /{certificate_id}/verify-qr         -> QR Check  (detects from file bytes, OCR fallback)
POST /{certificate_id}/verify-blockchain -> Blockchain Verification (SHA-256 hash lookup)
POST /{certificate_id}/verify-tampering  -> Tampering Detection (ELA + OpenCV heuristics)
POST /{certificate_id}/verify-duplicate  -> Duplicate Detection (hash / cert no. / reg no. / QR)
POST /{certificate_id}/verify-all        -> runs all four in sequence, one convenience call
GET  /{certificate_id}/verification      -> returns the full VerificationResult row
GET  /{certificate_id}/verify-enhanced   -> structured Part L composite response
"""
import asyncio
import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional

from app.db.database import get_db
from app.models.models import User, Certificate, OCRData, VerificationResult
from app.schemas.verification_schemas import VerificationResultResponse
from app.services.qr_verification import verify_qr
from app.services.blockchain_service import verify_hash_onchain
from app.services.tampering_detection import analyze_tampering
from app.services.duplicate_detection import detect_duplicates
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array, preprocess_pipeline
from app.services.ocr_field_extractor import detect_qr_code
from app.api.deps import get_current_verified_user, get_current_verified_user_flexible

logger = logging.getLogger("certiverify.verification")

router = APIRouter(prefix="/api/v1/certificates", tags=["AI Verification"])


@router.post("/{certificate_id}/verify-qr", response_model=VerificationResultResponse)
@router.post("/{certificate_id}/verify/qr", response_model=VerificationResultResponse, include_in_schema=False)
async def run_qr_check(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    t0 = time.monotonic()
    cert = await _get_owned_certificate(certificate_id, user, db)

    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result.scalar_one_or_none()
    expected_cert_number = ocr_row.certificate_number if ocr_row else None

    # ── Primary: detect QR directly from file bytes (independent of OCR) ────
    # Ensures QR detection works even when OCR hasn't run yet, or when OCR
    # missed the QR due to low resolution / preprocessing issues.
    qr_raw_data: str | None = None
    qr_confidence: int = 0
    detection_source = "none"

    try:
        storage = get_storage_backend()
        file_bytes = await storage.read(cert.storage_path)
        image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)
        direct_text, direct_confidence = await asyncio.to_thread(detect_qr_code, image)
        if direct_text:
            qr_raw_data = direct_text
            qr_confidence = direct_confidence
            detection_source = "direct_file"
            logger.info(
                "QR detection (direct) | cert_id=%s | confidence=%d | len=%d",
                certificate_id, direct_confidence, len(direct_text),
            )
    except Exception as exc:
        logger.warning("Direct QR detection failed (non-fatal, trying OCR fallback): %s", exc)

    # ── Fallback: use QR data stored by OCR pipeline ─────────────────────────
    if not qr_raw_data and ocr_row and ocr_row.qr_code_data:
        qr_raw_data = ocr_row.qr_code_data
        detection_source = "ocr_stored"
        if ocr_row.field_confidences:
            qr_confidence = int(ocr_row.field_confidences.get("_qr_confidence", 70))
        else:
            qr_confidence = 70
        logger.info(
            "QR detection (OCR fallback) | cert_id=%s | confidence=%d",
            certificate_id, qr_confidence,
        )

    # Build OCR fields dict for cross-validation
    ocr_fields: dict | None = None
    if ocr_row:
        ocr_fields = {
            "student_name":       ocr_row.student_name,
            "certificate_number": ocr_row.certificate_number,
            "university_name":    ocr_row.university_name,
            "register_number":    ocr_row.register_number,
        }

    logger.info(
        "QR check | cert_id=%s | source=%s | qr_present=%s | cert_number=%s",
        certificate_id, detection_source, bool(qr_raw_data), expected_cert_number,
    )

    result = verify_qr(
        qr_raw_data,
        expected_cert_number,
        qr_confidence=qr_confidence,
        ocr_fields=ocr_fields,
    )

    # Store qr_type and detection_source in decoded metadata for transparency
    decoded_with_meta = dict(result.decoded) if result.decoded else {}
    decoded_with_meta["_qr_type"] = result.qr_type
    decoded_with_meta["_detection_source"] = detection_source
    decoded_with_meta["_status"] = result.status
    if result.reason:
        decoded_with_meta["_reason"] = result.reason

    verification_row = await _get_or_create_verification_row(cert.id, db)
    verification_row.qr_present = result.present
    verification_row.qr_decoded_data = decoded_with_meta if result.present else result.decoded
    verification_row.qr_valid = result.valid
    verification_row.qr_warning = result.reason or result.warning
    verification_row.cross_validation_status = result.cross_validation_status
    verification_row.cross_validation_mismatches = result.cross_validation_mismatches or []

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        "QR check done | cert_id=%s | present=%s valid=%s cross_val=%s mismatches=%d | %dms",
        certificate_id, result.present, result.valid,
        result.cross_validation_status,
        len(result.cross_validation_mismatches), elapsed_ms,
    )
    await db.commit()
    await db.refresh(verification_row)
    return verification_row


@router.post("/{certificate_id}/verify-blockchain", response_model=VerificationResultResponse)
@router.post("/{certificate_id}/verify/blockchain", response_model=VerificationResultResponse, include_in_schema=False)
async def run_blockchain_verification(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    # ── Hash Consistency Check ────────────────────────────────────────────────
    # Re-compute SHA-256 from the stored file bytes and compare against the
    # hash we recorded at upload time. A mismatch means the file was modified
    # after upload (tampering evidence). This is separate from blockchain lookup.
    hash_match_status = "NOT_REGISTERED"
    try:
        storage = get_storage_backend()
        file_bytes = await storage.read(cert.storage_path)
        fresh_hash = hashlib.sha256(file_bytes).hexdigest()
        if fresh_hash == cert.sha256_hash:
            hash_match_status = "MATCH"
            logger.info("Hash consistency: MATCH | cert_id=%s", certificate_id)
        else:
            hash_match_status = "MISMATCH"
            logger.warning(
                "Hash consistency: MISMATCH | cert_id=%s | stored=%s | fresh=%s",
                certificate_id, cert.sha256_hash[:16], fresh_hash[:16],
            )
    except Exception as exc:
        logger.warning("Hash consistency check failed (non-fatal): %s", exc)
        hash_match_status = "NOT_REGISTERED"

    # ── Blockchain Lookup ─────────────────────────────────────────────────────
    logger.info(
        "Blockchain lookup | cert_id=%s | hash=%s...",
        certificate_id, cert.sha256_hash[:16] if cert.sha256_hash else "None",
    )
    result = verify_hash_onchain(cert.sha256_hash)
    logger.info(
        "Blockchain result | status=%s | match=%s",
        result.status, result.match,
    )

    verification_row = await _get_or_create_verification_row(cert.id, db)
    verification_row.blockchain_hash_submitted = cert.sha256_hash
    verification_row.blockchain_hash_onchain = result.onchain_hash
    verification_row.blockchain_match = result.match
    verification_row.blockchain_tx_hash = result.tx_hash
    verification_row.blockchain_status = result.status
    verification_row.hash_match_status = hash_match_status

    await db.commit()
    await db.refresh(verification_row)
    return verification_row


@router.post("/{certificate_id}/verify-tampering", response_model=VerificationResultResponse)
@router.post("/{certificate_id}/analyze/tampering", response_model=VerificationResultResponse, include_in_schema=False)
async def run_tampering_detection(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    storage = get_storage_backend()
    file_bytes = await storage.read(cert.storage_path)
    image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)
    processed = await asyncio.to_thread(preprocess_pipeline, image)

    # Fetch OCR context for document-aware tampering analysis (doc_type, fields, bboxes)
    ocr_result_q = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result_q.scalar_one_or_none()

    doc_type: str | None = None
    ocr_fields: dict | None = None
    bbox_results: list | None = None
    if ocr_row:
        # Extract doc_type from field_confidences metadata (stored by OCR pipeline)
        fc = ocr_row.field_confidences or {}
        doc_type = fc.get("_doc_type") or None
        ocr_fields = {
            "student_name":       ocr_row.student_name,
            "university_name":    ocr_row.university_name,
            "register_number":    ocr_row.register_number,
            "certificate_number": ocr_row.certificate_number,
            "course":             ocr_row.course,
        }
        # bbox_results is stored in field_confidences as _bbox_results or not stored (None is safe)
        bbox_results = fc.get("_bbox_results") or None

    logger.info(
        "Tampering check | cert_id=%s | doc_type=%s | has_ocr=%s",
        certificate_id, doc_type, bool(ocr_row),
    )

    try:
        result = await asyncio.to_thread(
            analyze_tampering,
            file_bytes, cert.file_type, processed,
            doc_type=doc_type,
            ocr_fields=ocr_fields,
            bbox_results=bbox_results,
        )
    except Exception as e:
        logger.error("Tampering analysis failed: %s", e, exc_info=True)
        from app.services.tampering_detection import TamperingResult
        result = TamperingResult(
            score=0.0,
            flags=[f"Tampering analysis failed: {str(e)}"],
            ela_heatmap_png=None,
            risk_level="FAILED",
            confidence=0.0,
            status=f"failed: {str(e)}",
        )

    logger.info(
        "Tampering done | cert_id=%s | score=%.1f | risk=%s | status=%s | flags=%d",
        certificate_id, result.score, result.risk_level, result.status, len(result.flags),
    )

    verification_row = await _get_or_create_verification_row(cert.id, db)
    # If not applicable for text layer or failed, score is None or 0.0
    verification_row.tampering_score = result.score if result.status == "analyzed" else None
    verification_row.tampering_flags = result.flags
    verification_row.tampering_risk_level = result.risk_level
    verification_row.tampering_confidence = result.confidence
    verification_row.tampering_detail = {
        "status":             result.status,
        "tampering_status":   result.status,
        "image_quality":      result.image_quality,
        "ela":                result.ela,
        "copy_paste":         result.copy_paste,
        "font_consistency":   result.font_consistency,
        "text_analysis":      result.text_analysis,   # PART E — text layout / alignment
        "signature":          result.signature,
        "seal":               result.seal,
        "metadata":           result.metadata_detail,
        "document_structure": result.document_structure,
        "findings":           result.findings,
    }

    # Persist ELA heatmap alongside the certificate for reviewer inspection
    if result.ela_heatmap_png:
        heatmap_name = f"ela_{cert.id}.png"
        heatmap_path = await storage.save_bytes(result.ela_heatmap_png, heatmap_name, subdir="ela_heatmaps")
        verification_row.ela_heatmap_path = heatmap_path

    await db.commit()
    await db.refresh(verification_row)
    return verification_row


@router.post("/{certificate_id}/verify-duplicate", response_model=VerificationResultResponse)
@router.post("/{certificate_id}/check/duplicate", response_model=VerificationResultResponse, include_in_schema=False)
async def run_duplicate_detection(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result.scalar_one_or_none()

    # Load file bytes for visual similarity (PART I) — best-effort, non-blocking
    file_bytes_for_visual: bytes | None = None
    try:
        from app.services.storage_service import get_storage_backend
        storage = get_storage_backend()
        file_bytes_for_visual = await storage.read(cert.storage_path)
    except Exception:
        pass

    result = await detect_duplicates(cert, ocr_row, db, file_bytes=file_bytes_for_visual)
    verification_row = await _get_or_create_verification_row(cert.id, db)

    # ── Legacy fields (backward-compatible) ──────────────────────────────────
    verification_row.is_duplicate = result.is_duplicate
    verification_row.duplicate_of_certificate_id = result.duplicate_of_certificate_id
    verification_row.duplicate_match_reason = (result.match_reason or "")[:255]

    # ── Rich structured result (Priority 7) ──────────────────────────────────
    verification_row.duplicate_detail = result.to_detail_dict()

    await db.commit()
    await db.refresh(verification_row)
    return verification_row


@router.post("/{certificate_id}/verify-all", response_model=VerificationResultResponse)
async def run_full_verification(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Convenience endpoint: runs QR, Blockchain, Tampering, and Duplicate checks
    in one call — mirrors the workflow diagram's single 'AI Verification Module' step."""
    try:
        await run_qr_check(certificate_id, user, db)
    except Exception as exc:
        logger.error("QR check failed for cert %s: %s", certificate_id, exc, exc_info=True)

    try:
        await run_blockchain_verification(certificate_id, user, db)
    except Exception as exc:
        logger.error("Blockchain check failed for cert %s: %s", certificate_id, exc, exc_info=True)

    try:
        await run_tampering_detection(certificate_id, user, db)
    except Exception as exc:
        logger.error("Tampering check failed for cert %s: %s", certificate_id, exc, exc_info=True)

    try:
        await run_duplicate_detection(certificate_id, user, db)
    except Exception as exc:
        logger.error("Duplicate check failed for cert %s: %s", certificate_id, exc, exc_info=True)

    from app.services.audit_service import log_audit_event
    await log_audit_event(
        db,
        action="certificate:verify",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_id=certificate_id,
    )

    return await get_verification(certificate_id, user, db)



@router.get("/{certificate_id}/verification", response_model=VerificationResultResponse)
async def get_verification(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
    verification_row = result.scalar_one_or_none()
    if not verification_row:
        raise HTTPException(status_code=404, detail="No verification has been run on this certificate yet.")
    return verification_row


@router.get("/{certificate_id}/ela-heatmap")
async def get_ela_heatmap(
    certificate_id: str,
    user: User = Depends(get_current_verified_user_flexible),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
    verification_row = result.scalar_one_or_none()
    if not verification_row or not verification_row.ela_heatmap_path:
        raise HTTPException(status_code=404, detail="No ELA heatmap available. Run tampering detection first.")

    storage = get_storage_backend()
    contents = await storage.read(verification_row.ela_heatmap_path)
    return StreamingResponse(iter([contents]), media_type="image/png")


async def _get_or_create_verification_row(certificate_id: str, db: AsyncSession) -> VerificationResult:
    result = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == certificate_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = VerificationResult(certificate_id=certificate_id)
        db.add(row)
    return row


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



# ── Part L — Enhanced Composite Verification Result ──────────────────────────

class EnhancedVerificationResponse(BaseModel):
    certificate_id: str

    qr_verification: dict[str, Any]
    hash_verification: dict[str, Any]
    blockchain_verification: dict[str, Any]
    cross_validation: dict[str, Any]

    composite_status: str          # STRONGLY_VERIFIED | VERIFIED | SUSPICIOUS | HIGH_RISK | INSUFFICIENT_EVIDENCE
    composite_detail: str          # Human-readable explanation
    checks_completed: int          # 0-4
    checks_total: int              # always 4
    verified_at: Optional[str]


@router.get("/{certificate_id}/verify-enhanced", response_model=EnhancedVerificationResponse)
async def get_enhanced_verification(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the structured Part L composite verification response combining:
      - QR verification sub-object
      - SHA-256 hash verification sub-object
      - Blockchain verification sub-object
      - Cross-validation sub-object
      - Composite status (STRONGLY_VERIFIED / VERIFIED / SUSPICIOUS / HIGH_RISK / INSUFFICIENT_EVIDENCE)

    All data is READ from existing stored rows — no computation is triggered.
    Run /verify-all (or individual endpoints) first to populate results.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    vr_result = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
    vr = vr_result.scalar_one_or_none()

    if not vr:
        raise HTTPException(
            status_code=404,
            detail="No verification results found. Run /verify-all or individual verification checks first.",
        )

    # ── QR sub-object ─────────────────────────────────────────────────────────
    decoded_data = vr.qr_decoded_data or {}
    qr_type = decoded_data.get("_qr_type", "unknown") if isinstance(decoded_data, dict) else "unknown"
    detection_source = decoded_data.get("_detection_source", "unknown") if isinstance(decoded_data, dict) else "unknown"

    if vr.qr_valid is True:
        qr_status = "VERIFIED"
    elif not vr.qr_present:
        qr_status = "no_qr_found"
    elif vr.qr_warning and "domain" in vr.qr_warning.lower():
        qr_status = "domain_not_allowed"
    elif vr.qr_warning and "expired" in vr.qr_warning.lower():
        qr_status = "token_expired"
    elif vr.qr_warning and ("match" in vr.qr_warning.lower() or "mismatch" in vr.qr_warning.lower()):
        qr_status = "ocr_mismatch"
    elif vr.qr_valid is False:
        qr_status = "INVALID"
    else:
        qr_status = "PRESENT_UNVERIFIED"

    qr_sub = {
        "status": qr_status,
        "reason": vr.qr_warning,
        "warning": vr.qr_warning,
        "qr_present": vr.qr_present,
        "qr_decoded": vr.qr_present and bool(decoded_data),
        "qr_type": qr_type,
        "detection_source": detection_source,
        "qr_confidence": decoded_data.get("_qr_confidence") if isinstance(decoded_data, dict) else None,
        "certificate_id_from_qr": (
            decoded_data.get("certificate_id") or decoded_data.get("certificateId")
            if isinstance(decoded_data, dict) else None
        ),
    }

    # ── Hash verification sub-object ──────────────────────────────────────────
    hash_sub = {
        "algorithm": "SHA-256",
        "uploaded_hash": cert.sha256_hash,
        "stored_hash": cert.sha256_hash,  # same — stored at upload time
        "status": vr.hash_match_status or "NOT_CHECKED",
    }

    # ── Blockchain sub-object ─────────────────────────────────────────────────
    bc_status_map = {
        "verified":     "VERIFIED",
        "not_found":    "NOT_REGISTERED",
        "mismatch":     "HASH_MISMATCH",
        "unavailable":  "UNAVAILABLE",
    }
    blockchain_sub = {
        "status": bc_status_map.get(vr.blockchain_status or "", "NOT_CHECKED"),
        "algorithm": "SHA-256",
        "submitted_hash": vr.blockchain_hash_submitted,
        "onchain_hash": vr.blockchain_hash_onchain,
        "hash_match": vr.blockchain_match,
        "transaction_id": vr.blockchain_tx_hash,
        "timestamp": None,  # not stored per-record; see block timestamp if needed
    }

    # ── Cross-validation sub-object ───────────────────────────────────────────
    cross_sub = {
        "status": vr.cross_validation_status or "UNAVAILABLE",
        "mismatches": vr.cross_validation_mismatches or [],
        "fields_checked": len(vr.cross_validation_mismatches or []),
    }

    # ── Composite status logic (Part J) ───────────────────────────────────────
    checks_completed, composite_status, composite_detail = _derive_composite(vr)

    logger.info(
        "Enhanced verification | cert_id=%s | composite=%s | checks=%d/4",
        certificate_id, composite_status, checks_completed,
    )

    return EnhancedVerificationResponse(
        certificate_id=certificate_id,
        qr_verification=qr_sub,
        hash_verification=hash_sub,
        blockchain_verification=blockchain_sub,
        cross_validation=cross_sub,
        composite_status=composite_status,
        composite_detail=composite_detail,
        checks_completed=checks_completed,
        checks_total=4,
        verified_at=vr.created_at.isoformat() if vr.created_at else None,
    )


def _derive_composite(vr: VerificationResult) -> tuple[int, str, str]:
    """
    Derive the composite Part J status from all stored verification signals.
    Returns (checks_completed, status_label, human_detail).

    Decision table (in priority order):
    1. BLOCKCHAIN MISMATCH or QR INVALID          → HIGH_RISK
    2. HASH MISMATCH (file changed after upload)  → HIGH_RISK
    3. Cross-validation MISMATCH                  → SUSPICIOUS
    4. QR VERIFIED + BLOCKCHAIN VERIFIED          → STRONGLY_VERIFIED
    5. BLOCKCHAIN VERIFIED (no QR or QR neutral)  → VERIFIED
    6. QR VERIFIED (blockchain unavailable)       → VERIFIED
    7. No strong positive evidence                → INSUFFICIENT_EVIDENCE
    """
    checks = 0
    if vr.qr_present is not None:
        checks += 1
    if vr.blockchain_status is not None:
        checks += 1
    if vr.hash_match_status is not None:
        checks += 1
    if vr.cross_validation_status is not None and vr.cross_validation_status != "UNAVAILABLE":
        checks += 1

    # Negative critical signals (hard overrides)
    if vr.blockchain_status == "mismatch":
        return checks, "HIGH_RISK", (
            "Blockchain hash MISMATCH — the uploaded certificate hash does not match the "
            "on-chain record. The document may have been altered after original registration."
        )
    if vr.qr_present and vr.qr_valid is False:
        return checks, "HIGH_RISK", (
            "QR code validation FAILED — the QR payload is invalid, expired, or its "
            "certificate ID does not match the extracted certificate number."
        )
    if vr.hash_match_status == "MISMATCH":
        return checks, "HIGH_RISK", (
            "SHA-256 hash MISMATCH — the current file hash differs from the hash recorded "
            "at upload time, indicating the file may have been modified."
        )
    if vr.cross_validation_status == "MISMATCH":
        mismatches = vr.cross_validation_mismatches or []
        mismatch_summary = "; ".join(
            f"{m.get('field')}: QR='{m.get('qr_value')}' vs OCR='{m.get('ocr_value')}'"
            for m in mismatches[:3]
        )
        return checks, "SUSPICIOUS", (
            f"Cross-validation found inconsistencies between QR and OCR data: {mismatch_summary}."
        )

    # Positive signals
    qr_verified = vr.qr_present and vr.qr_valid is True
    blockchain_verified = vr.blockchain_status == "verified"

    if qr_verified and blockchain_verified:
        return checks, "STRONGLY_VERIFIED", (
            "Both QR code and blockchain verification passed. The certificate ID matches "
            "the on-chain record and OCR data is consistent."
        )
    if blockchain_verified:
        qr_note = " (no QR code was present on the document)" if not vr.qr_present else " (QR was present but not fully verified)"
        return checks, "VERIFIED", (
            f"Blockchain hash verified — the certificate hash matches the registered on-chain record{qr_note}."
        )
    if qr_verified:
        return checks, "VERIFIED", (
            "QR code verified successfully. Blockchain was unavailable or hash not yet registered, "
            "so blockchain evidence could not be obtained."
        )

    # No strong positive evidence
    return checks, "INSUFFICIENT_EVIDENCE", (
        "Verification checks completed but no strong positive evidence was found. "
        "The certificate may not have been registered, or verification checks may not have been run yet."
    )
