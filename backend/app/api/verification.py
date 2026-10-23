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
from datetime import datetime

from app.db.database import get_db
from app.models.models import User, Certificate, OCRData, VerificationResult, VerificationJob
from app.schemas.verification_schemas import VerificationResultResponse
from app.services.qr_verification import verify_qr
from app.services.blockchain_service import verify_hash_onchain, get_blockchain_provider
from app.services.tampering_detection import analyze_tampering
from app.services.duplicate_detection import detect_duplicates
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array, preprocess_pipeline, _pdf_pages_to_arrays
from app.services.ocr_field_extractor import detect_qr_code
from app.services.audit_service import log_audit_event
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

    qr_raw_data: str | None = None
    qr_confidence: int = 0
    detection_source = "none"

    # 1. Reuse existing OCR QR data first — don't re-decode needlessly
    if ocr_row and ocr_row.qr_code_data:
        qr_raw_data = ocr_row.qr_code_data
        detection_source = "ocr_stored"
        if ocr_row.field_confidences and isinstance(ocr_row.field_confidences, dict):
            qr_confidence = int(ocr_row.field_confidences.get("_qr_confidence", 85))
        else:
            qr_confidence = 85
        logger.info(
            "QR detection reused from OCR data | cert_id=%s | confidence=%d",
            certificate_id, qr_confidence,
        )
    else:
        # 2. Multi-pass decoding across document pages (PDF or image)
        try:
            storage = get_storage_backend()
            file_bytes = await storage.read(cert.storage_path)

            if cert.file_type.lower() == "pdf":
                pages = await asyncio.to_thread(_pdf_pages_to_arrays, file_bytes)
                for page in pages:
                    text, conf = await asyncio.to_thread(detect_qr_code, page["image"])
                    if text:
                        qr_raw_data = text
                        qr_confidence = conf
                        detection_source = f"direct_pdf_page_{page['index'] + 1}"
                        logger.info(
                            "QR detected on PDF page %d | cert_id=%s | conf=%d | len=%d",
                            page["index"] + 1, certificate_id, conf, len(text),
                        )
                        break
            else:
                image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)
                text, conf = await asyncio.to_thread(detect_qr_code, image)
                if text:
                    qr_raw_data = text
                    qr_confidence = conf
                    detection_source = "direct_image"
                    logger.info(
                        "QR detected on image | cert_id=%s | conf=%d | len=%d",
                        certificate_id, conf, len(text),
                    )
        except Exception as exc:
            logger.warning("Document QR detection pass failed (non-fatal): %s", exc)

    # Build OCR fields dict for cross-validation and live matching
    ocr_fields: dict | None = None
    if ocr_row:
        ocr_fields = {
            "student_name":       ocr_row.student_name,
            "certificate_number": ocr_row.certificate_number,
            "university_name":    ocr_row.university_name,
            "register_number":    ocr_row.register_number,
        }

    logger.info(
        "QR verify run | cert_id=%s | source=%s | qr_present=%s",
        certificate_id, detection_source, bool(qr_raw_data),
    )

    result = await verify_qr(
        qr_raw_data,
        expected_certificate_number=expected_cert_number,
        qr_confidence=qr_confidence,
        ocr_fields=ocr_fields,
        detection_source=detection_source,
    )

    decoded_with_meta = dict(result.decoded) if result.decoded else None
    if decoded_with_meta:
        decoded_with_meta["_qr_type"] = result.qr_type
        decoded_with_meta["_detection_source"] = detection_source
        decoded_with_meta["_status"] = result.status
        decoded_with_meta["_qr_confidence"] = qr_confidence
        if result.reason:
            decoded_with_meta["_reason"] = result.reason

    verification_row = await _get_or_create_verification_row(cert.id, db)
    verification_row.qr_present = result.present
    verification_row.qr_decoded_data = decoded_with_meta
    verification_row.qr_valid = result.valid
    verification_row.qr_warning = result.reason or result.warning
    verification_row.cross_validation_status = result.cross_validation_status
    verification_row.cross_validation_mismatches = result.cross_validation_mismatches or []

    # Update any existing verification job's stage_states
    job_res = await db.execute(
        select(VerificationJob).where(VerificationJob.certificate_id == cert.id).order_by(VerificationJob.id.desc())
    )
    job = job_res.scalars().first()
    if job:
        states = dict(job.stage_states or {})
        now_iso = datetime.utcnow().isoformat()
        if not result.present:
            states["qr_verification"] = {
                "status": "NOT_APPLICABLE",
                "label": "QR Code Verification",
                "completed_at": now_iso,
                "details": result.reason or "No QR code detected on document",
            }
        elif result.valid:
            states["qr_verification"] = {
                "status": "COMPLETED",
                "label": "QR Code Verification",
                "completed_at": now_iso,
                "details": f"QR payload verified ({result.qr_type})",
            }
        else:
            states["qr_verification"] = {
                "status": "FAILED",
                "label": "QR Code Verification",
                "completed_at": now_iso,
                "details": result.reason or "QR verification failed",
            }
        job.stage_states = states

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        "QR check done | cert_id=%s | present=%s valid=%s cross_val=%s mismatches=%d | %dms",
        certificate_id, result.present, result.valid,
        result.cross_validation_status,
        len(result.cross_validation_mismatches), elapsed_ms,
    )

    await log_audit_event(
        db,
        action="verification:qr_completed",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=cert.organization_id,
        entity_id=cert.id,
        metadata_json={
            "qr_present": result.present,
            "qr_valid": result.valid,
            "qr_type": result.qr_type,
            "status": result.status,
            "elapsed_ms": elapsed_ms,
        },
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

    # 1. Document hash from certificates.sha256_hash (don't recompute unless missing)
    if not cert.sha256_hash:
        try:
            storage = get_storage_backend()
            file_bytes = await storage.read(cert.storage_path)
            cert.sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            logger.info("Computed missing certificate SHA-256 hash | cert_id=%s", cert.id)
            await db.commit()
        except Exception as exc:
            logger.warning("Failed computing SHA-256 hash: %s", exc)

    logger.info(
        "Blockchain verification | cert_id=%s | hash=%s...",
        certificate_id, cert.sha256_hash[:16] if cert.sha256_hash else "None",
    )

    # 2. Query blockchain via swappable BlockchainProvider
    result = verify_hash_onchain(cert.sha256_hash)
    logger.info(
        "Blockchain result | status=%s | match=%s | provider=%s",
        result.status, result.match, result.provider_name,
    )

    verification_row = await _get_or_create_verification_row(cert.id, db)
    verification_row.blockchain_hash_submitted = cert.sha256_hash
    verification_row.blockchain_hash_onchain = result.onchain_hash
    verification_row.blockchain_match = result.match
    verification_row.blockchain_tx_hash = result.tx_hash
    verification_row.blockchain_status = result.status
    verification_row.hash_match_status = "MATCH" if cert.sha256_hash else "NOT_REGISTERED"

    # 3. Update VerificationJob stage_states
    job_res = await db.execute(
        select(VerificationJob).where(VerificationJob.certificate_id == cert.id).order_by(VerificationJob.id.desc())
    )
    job = job_res.scalars().first()
    if job:
        states = dict(job.stage_states or {})
        now_iso = datetime.utcnow().isoformat()
        if result.status == "NOT_APPLICABLE":
            states["blockchain_verification"] = {
                "status": "NOT_APPLICABLE",
                "label": "Blockchain Verification",
                "completed_at": now_iso,
                "details": "Blockchain not configured",
            }
        elif result.status in ("MATCH", "verified", "MATCH (local_ledger)"):
            states["blockchain_verification"] = {
                "status": "COMPLETED",
                "label": "Blockchain Verification",
                "completed_at": now_iso,
                "details": f"Verified ({result.status})",
            }
        elif result.status == "NOT_REGISTERED":
            states["blockchain_verification"] = {
                "status": "COMPLETED",
                "label": "Blockchain Verification",
                "completed_at": now_iso,
                "details": "Certificate hash not registered on blockchain (neutral)",
            }
        elif result.status == "UNREACHABLE":
            states["blockchain_verification"] = {
                "status": "FAILED",
                "label": "Blockchain Verification",
                "completed_at": now_iso,
                "details": result.reason or "Blockchain RPC unreachable",
            }
        elif result.status == "MISMATCH":
            states["blockchain_verification"] = {
                "status": "FAILED",
                "label": "Blockchain Verification",
                "completed_at": now_iso,
                "details": result.reason or "Blockchain on-chain hash mismatch",
            }
        else:
            states["blockchain_verification"] = {
                "status": "COMPLETED",
                "label": "Blockchain Verification",
                "completed_at": now_iso,
                "details": result.reason or str(result.status),
            }
        job.stage_states = states

    await log_audit_event(
        db,
        action="verification:blockchain_completed",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=cert.organization_id,
        entity_id=cert.id,
        metadata_json={
            "blockchain_status": result.status,
            "blockchain_match": result.match,
            "provider": result.provider_name,
        },
    )

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
    import dataclasses

    findings_data = []
    for f in (result.findings or []):
        if dataclasses.is_dataclass(f):
            findings_data.append(dataclasses.asdict(f))
        elif hasattr(f, "to_dict"):
            findings_data.append(f.to_dict())
        elif isinstance(f, dict):
            findings_data.append(f)
        else:
            findings_data.append(str(f))

    verification_row.tampering_detail = {
        "status":             result.status,
        "tampering_status":   result.status,
        "composite_score":    result.score,
        "risk_level":         result.risk_level,
        "confidence":         result.confidence,
        "checks":             result.tampering_detail.get("checks", {}),
        "active_weights":     result.tampering_detail.get("active_weights", {}),
        "image_quality":      result.image_quality,
        "ela":                result.ela,
        "copy_paste":         result.copy_paste,
        "font_consistency":   result.font_consistency,
        "text_analysis":      result.text_analysis,
        "signature":          result.signature,
        "seal":               result.seal,
        "metadata":           result.metadata_detail,
        "document_structure": result.document_structure,
        "findings":           findings_data,
    }

    # Persist ELA heatmap alongside the certificate for reviewer inspection
    if result.ela_heatmap_png:
        heatmap_name = f"ela_{cert.id}.png"
        heatmap_path = await storage.save_bytes(result.ela_heatmap_png, heatmap_name, subdir="ela_heatmaps")
        verification_row.ela_heatmap_path = heatmap_path

    # Update verification job stage states if job exists
    job_res = await db.execute(
        select(VerificationJob).where(VerificationJob.certificate_id == cert.id).order_by(VerificationJob.id.desc())
    )
    job = job_res.scalars().first()
    if job:
        states = dict(job.stage_states or {})
        now_iso = datetime.utcnow().isoformat()
        if result.status == "not_applicable_for_pdf_text_layer":
            stage_info = {
                "status": "NOT_APPLICABLE",
                "label": "Tampering & Forgery Detection",
                "completed_at": now_iso,
                "details": "Digital vector PDF text layer (image forensics not applicable)",
            }
        elif result.risk_level in ("HIGH", "VERY_HIGH_RISK") or (result.score and result.score >= 60.0):
            stage_info = {
                "status": "FAILED",
                "label": "Tampering & Forgery Detection",
                "completed_at": now_iso,
                "details": f"Tampering risk detected (Score: {result.score:.1f}/100 - {result.risk_level})",
            }
        else:
            stage_info = {
                "status": "COMPLETED",
                "label": "Tampering & Forgery Detection",
                "completed_at": now_iso,
                "details": f"Analysis complete (Score: {result.score:.1f}/100 - {result.risk_level})",
            }
        states["tamper_analysis"] = stage_info
        states["tampering"] = stage_info
        job.stage_states = states

    await log_audit_event(
        db,
        action="verification:tampering_completed",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=cert.organization_id,
        entity_id=cert.id,
        metadata_json={
            "tampering_score": result.score,
            "tampering_risk_level": result.risk_level,
            "tampering_confidence": result.confidence,
            "status": result.status,
            "flags_count": len(result.flags),
        },
    )

    await db.commit()
    await db.refresh(verification_row)
    return verification_row


@router.post("/{certificate_id}/verify-duplicate", response_model=VerificationResultResponse)
@router.post("/{certificate_id}/check/duplicate", response_model=VerificationResultResponse, include_in_schema=False)
@router.post("/{certificate_id}/analyze/duplicate", response_model=VerificationResultResponse, include_in_schema=False)
async def run_duplicate_detection(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result.scalar_one_or_none()

    # Load file bytes for visual similarity — best-effort, non-blocking
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

    # ── Rich structured result (Module 4) ───────────────────────────────────
    verification_row.duplicate_detail = result.to_detail_dict()

    # Update verification job stage states if job exists
    job_res = await db.execute(
        select(VerificationJob).where(VerificationJob.certificate_id == cert.id).order_by(VerificationJob.id.desc())
    )
    job = job_res.scalars().first()
    if job:
        states = dict(job.stage_states or {})
        now_iso = datetime.utcnow().isoformat()
        if result.is_duplicate:
            stage_status = "WARNING" if result.same_owner else "FAILED"
            details = f"Duplicate detected ({result.owner_distinction} - {result.match_layer})"
        else:
            stage_status = "COMPLETED"
            details = "No duplicate records found in registry"

        stage_info = {
            "status": stage_status,
            "label": "Duplicate Detection",
            "completed_at": now_iso,
            "details": details,
        }
        states["duplicate"] = stage_info
        states["duplicate_detection"] = stage_info
        states["DUPLICATE_DETECTION"] = stage_info
        job.stage_states = states

    from app.services.audit_service import log_audit_event
    await log_audit_event(
        db,
        action="verification:duplicate_completed",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=cert.organization_id,
        entity_id=cert.id,
        metadata_json={
            "is_duplicate": result.is_duplicate,
            "match_layer": result.match_layer,
            "same_owner": result.same_owner,
            "owner_distinction": result.owner_distinction,
            "duplicate_type": result.duplicate_type,
            "matched_certificate_id": result.duplicate_of_certificate_id,
            "confidence": result.confidence,
        },
    )

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
        verification_row = await _get_or_create_verification_row(cert.id, db)
        await db.commit()
        await db.refresh(verification_row)
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
    from app.api.deps import normalize_cert_id
    norm_id = normalize_cert_id(certificate_id)
    result = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == norm_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = VerificationResult(certificate_id=norm_id)
        db.add(row)
    return row


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    from app.api.deps import get_owned_certificate
    return await get_owned_certificate(certificate_id, user, db)



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
    raw_bc_status = (vr.blockchain_status or "").strip().lower()
    bc_status_map = {
        "verified":             "VERIFIED",
        "match":                "VERIFIED",
        "match (local_ledger)": "VERIFIED",
        "not_found":            "NOT_REGISTERED",
        "not_registered":       "NOT_REGISTERED",
        "mismatch":             "HASH_MISMATCH",
        "unavailable":          "UNAVAILABLE",
        "unreachable":          "UNREACHABLE",
        "not_applicable":       "NOT_APPLICABLE",
    }
    blockchain_sub = {
        "status": bc_status_map.get(raw_bc_status, vr.blockchain_status or "NOT_CHECKED"),
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
    norm_bc_status = (vr.blockchain_status or "").strip().lower()
    if norm_bc_status in ("mismatch",):
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
    blockchain_verified = norm_bc_status in ("verified", "match", "match (local_ledger)")

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
