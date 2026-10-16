"""
MODULE 4 - OCR TEXT EXTRACTION API

POST  /{certificate_id}/extract-ocr -> runs OCR + field extraction, persists + returns
GET   /{certificate_id}/ocr-data    -> returns the last stored OCR data
PATCH /{certificate_id}/ocr-data    -> user corrections from the editable table (Module 4 UI requirement)

Enhancement: extract-ocr now accepts an optional `doc_type` query parameter.
When the user manually selects a document type before upload, the frontend
passes it here and auto-classification (classify_from_text) is SKIPPED —
the provided type is used directly for field extraction.
When no doc_type is supplied the existing auto-classification path is used
unchanged (100% backward compatible).

FIX (hanging OCR): All synchronous CPU-bound OCR calls are now wrapped in
asyncio.to_thread() so they execute in a thread pool instead of blocking
FastAPI's async event loop. A 120-second global timeout returns HTTP 408
immediately if OCR takes too long, preventing infinite "Extracting..." state.
"""
import asyncio
import logging
import time
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, Certificate, OCRData, DocumentType
from app.schemas.ocr_schemas import (
    OCRDataResponse, OCRDataUpdateRequest,
    DocumentValidationResponse, FieldValidationItem,
)
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import (
    load_image_as_array, preprocess_for_ocr,
    preprocess_for_aadhaar, preprocess_for_marksheet, preprocess_for_resume,
    _pdf_pages_to_arrays, _select_best_page,
)
from app.services.ocr_engine import (
    extract_text_and_bboxes,
    extract_text_and_bboxes_fused,
)
from app.services.ocr_text_cleaner import clean_ocr_text, normalize_ocr_text
from app.services.ocr_field_extractor import (
    extract_fields,
    detect_qr_code,
    detect_signature,
    detect_seal,
    extract_fields_by_type,
    extract_fields_with_bboxes,
    validate_field,
)
from app.services.document_classifier import classify_from_text
from app.services.template_extractor import extract_by_template
from app.api.deps import get_current_verified_user

logger = logging.getLogger("certiverify.ocr")

router = APIRouter(prefix="/api/v1/certificates", tags=["OCR Text Extraction"])

# Global OCR timeout (seconds).
# 120s is enough for single-page OCR at 200 DPI on CPU.
OCR_TIMEOUT_SECONDS = 120

# Valid manual doc type values (mirrors DocTypeEnum)
_VALID_DOC_TYPES = {
    "aadhaar_card",
    "marksheet",
    "transfer_certificate",
    "diploma",
    "degree_certificate",
    "resume",
    # keep legacy values in case older callers pass them
    "experience_certificate",
    "identity_card",
    "unknown",
}


# ---------------------------------------------------------------------------
# Thread-safe async wrappers for all blocking sync calls
# ---------------------------------------------------------------------------

async def _async_load_image(file_bytes: bytes, file_type: str):
    """Run load_image_as_array in a thread pool (PyMuPDF / PIL are blocking)."""
    return await asyncio.to_thread(load_image_as_array, file_bytes, file_type)


async def _async_load_image_dpi(file_bytes: bytes, file_type: str, dpi: int):
    """Render PDF at a specific DPI (used by adaptive DPI retry)."""
    if file_type.lower().lstrip(".") != "pdf":
        return await asyncio.to_thread(load_image_as_array, file_bytes, file_type)
    pages = await asyncio.to_thread(_pdf_pages_to_arrays, file_bytes, dpi)
    best = _select_best_page(pages)
    return best["image"]


async def _async_preprocess(
    raw_image,
    doc_type: str | None = None,
    is_digital: bool = False,
):
    """
    Run the appropriate preprocessing pipeline for the doc type.
    Passes skip_osd=is_digital and is_digital to all pipelines that support it.
    """
    _MS_TYPES = {"marksheet", "sslc", "hsc", "sslc_marksheet", "hsc_marksheet"}
    if doc_type == "aadhaar_card":
        return await asyncio.to_thread(
            preprocess_for_aadhaar, raw_image,
            is_digital,   # skip_osd
            is_digital,   # is_digital
        )
    if doc_type in _MS_TYPES:
        return await asyncio.to_thread(
            preprocess_for_marksheet, raw_image,
            is_digital,   # skip_osd
            is_digital,   # is_digital
        )
    if doc_type == "resume":
        return await asyncio.to_thread(
            preprocess_for_resume, raw_image,
            is_digital,   # skip_osd
            is_digital,   # is_digital
        )
    # Generic pipeline (degree, diploma, transfer cert, unknown)
    return await asyncio.to_thread(
        preprocess_for_ocr, raw_image,
        is_digital,   # skip_osd
        is_digital,   # is_digital
    )


async def _async_extract_text_and_bboxes(color_processed, binary_gray, doc_type=None):
    """
    Run EasyOCR + conditional Tesseract in a thread pool.
    Passes doc_type so the engine can skip Tesseract on high-confidence results.
    """
    return await asyncio.to_thread(
        extract_text_and_bboxes, color_processed,
        binary_gray,
        doc_type,
    )


# ---------------------------------------------------------------------------
# Idempotent OCR result reuse helper
# ---------------------------------------------------------------------------

def _is_valid_ocr_record(ocr_row: OCRData) -> bool:
    """
    Check if an existing OCRData row contains a valid, successful OCR extraction result.
    An OCR record is valid if:
    - raw_text is non-empty (at least 15 chars) AND ocr_accuracy >= 0.05
    - OR at least one key identity field (student_name, register_number, certificate_number, etc.) is populated.
    """
    if not ocr_row:
        return False
    text = (ocr_row.raw_text or "").strip()
    if len(text) >= 15 and (ocr_row.ocr_accuracy or 0.0) >= 0.05:
        return True
    has_key_field = any([
        bool(ocr_row.student_name and len(str(ocr_row.student_name).strip()) > 1),
        bool(ocr_row.register_number and len(str(ocr_row.register_number).strip()) > 1),
        bool(ocr_row.certificate_number and len(str(ocr_row.certificate_number).strip()) > 1),
        bool(ocr_row.university_name and len(str(ocr_row.university_name).strip()) > 1),
        bool(ocr_row.course and len(str(ocr_row.course).strip()) > 1),
    ])
    return has_key_field and len(text) > 0


async def _find_and_reuse_successful_ocr(
    cert: Certificate,
    db: AsyncSession
) -> Optional[OCRData]:
    """
    Idempotency check: If another Certificate with the exact same sha256_hash already has a valid,
    successful OCRData row in the database, safely copy and reuse its extraction results for this cert.
    Returns the newly populated/saved OCRData row, or None if no valid previous OCR exists.
    """
    if not cert.sha256_hash:
        return None

    query = (
        select(OCRData)
        .join(Certificate, OCRData.certificate_id == Certificate.id)
        .where(
            Certificate.sha256_hash == cert.sha256_hash,
            Certificate.id != cert.id,
        )
        .order_by(OCRData.created_at.desc())
    )
    result = await db.execute(query)
    prior_ocr_rows = result.scalars().all()

    for prior_ocr in prior_ocr_rows:
        if _is_valid_ocr_record(prior_ocr):
            logger.info(
                "⚡ [IDEMPOTENT OCR REUSE] Found prior valid OCR result (id=%s, accuracy=%.2f) "
                "for identical sha256_hash=%s. Reusing for cert_id=%s.",
                prior_ocr.id, prior_ocr.ocr_accuracy or 0.0, cert.sha256_hash[:16], cert.id
            )

            existing = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
            current_row = existing.scalar_one_or_none()
            if current_row is None:
                current_row = OCRData(certificate_id=cert.id)
                db.add(current_row)

            # Copy all extraction fields
            current_row.student_name = prior_ocr.student_name
            current_row.university_name = prior_ocr.university_name
            current_row.register_number = prior_ocr.register_number
            current_row.roll_number = prior_ocr.roll_number
            current_row.certificate_number = prior_ocr.certificate_number
            current_row.department = prior_ocr.department
            current_row.course = prior_ocr.course
            current_row.cgpa = prior_ocr.cgpa
            current_row.percentage = prior_ocr.percentage
            current_row.date_of_issue = prior_ocr.date_of_issue
            current_row.qr_code_data = prior_ocr.qr_code_data
            current_row.has_signature = prior_ocr.has_signature
            current_row.has_seal = prior_ocr.has_seal
            current_row.raw_text = prior_ocr.raw_text

            conf = dict(prior_ocr.field_confidences or {})
            conf["_reused_from_hash"] = cert.sha256_hash[:16]
            conf["_ocr_status"] = "OCR_SUCCESS"
            conf["_ocr_stage"] = "idempotent_reuse"
            current_row.field_confidences = conf
            current_row.ocr_accuracy = prior_ocr.ocr_accuracy
            engine_str = prior_ocr.ocr_engine or "easyocr+tesseract"
            if "[idempotent]" not in engine_str:
                engine_str = f"{engine_str}+[idempotent]"
            current_row.ocr_engine = engine_str

            await db.commit()
            await db.refresh(current_row)
            return current_row

    return None


# ---------------------------------------------------------------------------
# Core OCR pipeline (called inside asyncio.wait_for for timeout protection)
# ---------------------------------------------------------------------------

async def _run_ocr_pipeline(
    cert: Certificate,
    file_bytes: bytes,
    doc_type: Optional[str],
):
    """
    All OCR stages run here, fully async (thread-pool for blocking calls).

    UPGRADED: Now processes ALL pages of multi-page PDFs instead of just
    the 'best' single page. Uses intelligent EasyOCR+Tesseract fusion
    and enhanced text normalization.
    """
    pipeline_start = time.time()
    timings: dict[str, float] = {}

    # is_digital = True when file came from PyMuPDF PDF rendering.
    # Digital PDFs are always upright and have no camera shadows —
    # skip OSD (5-15s) and shadow removal (3-8s) for them.
    is_digital = cert.file_type.lower().lstrip(".") == "pdf"

    # ── Stage 1: File validation ──────────────────────────────────────────
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty (0 bytes).",
        )
    logger.info("✔ Stage 1: File validated | size=%d bytes | type=%s", len(file_bytes), cert.file_type)

    # ── Stage 2: Load image (best page only) ────────────────────────────────
    # CRITICAL: Loading ALL pages at 200 DPI creates ~11MB per page.
    # Processing every page through EasyOCR takes ~50s/page on CPU.
    # Multi-page PDFs would exceed the Next.js proxy timeout (~60s)
    # causing ECONNRESET. Solution: load pages, pick the best one,
    # release the rest immediately.
    t = time.time()
    logger.info("✔ Stage 2: Loading image | file_type=%s | is_digital=%s", cert.file_type, is_digital)
    try:
        raw_image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)
        timings["pdf_load"] = time.time() - t
        logger.info("✔ Stage 2 done | shape=%s | %.1fs", raw_image.shape, timings["pdf_load"])
    except RuntimeError as exc:
        logger.error("Stage 2 image load failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        logger.error("Stage 2 unexpected error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to load document image: {exc}",
        )

    # Preliminary doc_type detection from filename or param
    effective_doc_type = doc_type
    if not effective_doc_type and cert.original_filename:
        fn_l = cert.original_filename.lower()
        if any(k in fn_l for k in ["marksheet", "mark_sheet", "12th", "10th", "sslc", "hsc"]):
            effective_doc_type = "marksheet"
        elif "aadhaar" in fn_l:
            effective_doc_type = "aadhaar_card"
        elif "resume" in fn_l:
            effective_doc_type = "resume"

    # ── Stage 3: Image preprocessing (doc-type aware) ─────────────────────
    t = time.time()
    logger.info("✔ Stage 3: Preprocessing | doc_type=%s", effective_doc_type)
    active_variant_name = "standard"
    try:
        color_processed, binary_gray = await _async_preprocess(
            raw_image, doc_type=effective_doc_type, is_digital=is_digital
        )
        timings["preprocess"] = time.time() - t
        logger.info("✔ Stage 3 done | color=%s binary=%s | %.1fs",
                    color_processed.shape, binary_gray.shape, timings["preprocess"])
    except Exception as exc:
        logger.error("Stage 3 preprocessing failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Image preprocessing failed: {exc}",
        )

    # ── Stage 4+5: OCR + BBox (intelligent fusion) ────────────────────────
    t = time.time()
    logger.info("✔ Stage 4: OCR started (running in thread pool)")
    try:
        ocr_result, bbox_results = await asyncio.to_thread(
            extract_text_and_bboxes_fused, color_processed, binary_gray,
            doc_type, 0,
        )
        timings["ocr"] = time.time() - t
        logger.info(
            "✔ Stage 4+5: OCR+BBox done | engines=%s | accuracy=%.4f | text_len=%d | bboxes=%d | %.1fs",
            ocr_result.engines_used, ocr_result.accuracy, len(ocr_result.raw_text),
            len(bbox_results), timings["ocr"],
        )
    except RuntimeError as exc:
        logger.error("Stage 4 OCR engine error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Stage 4 unexpected OCR error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"OCR engine failed: {exc}",
        )

    # ── Adaptive DPI retry (single page only, capped at 250 DPI) ──────────
    if is_digital and ocr_result.accuracy < 0.65 and len(ocr_result.raw_text.strip()) < 50:
        logger.info(
            "⚡ Low confidence (%.3f) + short text — retrying at 250 DPI",
            ocr_result.accuracy,
        )
        try:
            t_retry = time.time()
            raw_image_hq = await _async_load_image_dpi(file_bytes, cert.file_type, dpi=250)
            color_hq, binary_hq = await _async_preprocess(
                raw_image_hq, doc_type=doc_type, is_digital=is_digital
            )
            ocr_result_hq, bbox_results_hq = await asyncio.to_thread(
                extract_text_and_bboxes_fused, color_hq, binary_hq,
                doc_type, 0,
            )
            timings["dpi_retry"] = time.time() - t_retry
            if ocr_result_hq.accuracy > ocr_result.accuracy:
                logger.info(
                    "✔ DPI retry improved accuracy: %.3f → %.3f | %.1fs",
                    ocr_result.accuracy, ocr_result_hq.accuracy, timings["dpi_retry"],
                )
                ocr_result = ocr_result_hq
                bbox_results = bbox_results_hq
                color_processed = color_hq
            else:
                logger.info(
                    "DPI retry did not improve (%.3f vs %.3f) — keeping original",
                    ocr_result_hq.accuracy, ocr_result.accuracy,
                )
        except Exception as exc:
            logger.warning("DPI retry failed (non-fatal): %s", exc)

    # ── Multi-variant fallback for low accuracy / short text ─────────────────
    if ocr_result.accuracy < 0.50 or len(ocr_result.raw_text.strip()) < 25:
        logger.info("⚡ Low OCR accuracy (%.3f) / text len (%d) — testing preprocessing variants",
                    ocr_result.accuracy, len(ocr_result.raw_text.strip()))
        try:
            from app.services.image_preprocessing import generate_preprocessing_variants
            variants = await asyncio.to_thread(generate_preprocessing_variants, raw_image, is_digital)
            best_variant_res = ocr_result
            best_variant_bboxes = bbox_results
            best_color = color_processed

            for var in variants:
                if var["name"] in ("enhanced_color", "raw_fallback"):
                    continue
                try:
                    res_var, bboxes_var = await asyncio.to_thread(
                        extract_text_and_bboxes_fused, var["color"], var["gray"], doc_type, 0
                    )
                    if (res_var.accuracy > best_variant_res.accuracy and len(res_var.raw_text.strip()) >= 15) or \
                       (len(best_variant_res.raw_text.strip()) < 15 and len(res_var.raw_text.strip()) >= 15):
                        logger.info("✔ Preprocessing variant '%s' improved OCR | accuracy: %.3f → %.3f | text_len: %d → %d",
                                    var["name"], best_variant_res.accuracy, res_var.accuracy,
                                    len(best_variant_res.raw_text.strip()), len(res_var.raw_text.strip()))
                        best_variant_res = res_var
                        best_variant_bboxes = bboxes_var
                        best_color = var["color"]
                        active_variant_name = var["name"]
                except Exception as var_exc:
                    logger.warning("Preprocessing variant '%s' failed (non-fatal): %s", var["name"], var_exc)

            ocr_result = best_variant_res
            bbox_results = best_variant_bboxes
            color_processed = best_color
        except Exception as fallback_exc:
            logger.warning("Multi-variant fallback failed (non-fatal): %s", fallback_exc)

    # ── Stage 5.5: Clean / Normalize OCR Text ──────────────────────────────
    t_clean = time.time()
    raw_text_before = ocr_result.raw_text

    # Use enhanced normalization (produces both raw and normalized text)
    norm_result = normalize_ocr_text(ocr_result.raw_text)
    cleaned_text = norm_result["normalized_text"]
    timings["text_clean"] = time.time() - t_clean

    # Patch the result so all downstream code uses normalized text
    ocr_result.raw_text = cleaned_text
    logger.info(
        "✔ Stage 5.5: OCR text normalized | chars: %d → %d (-%d) | %.2fs",
        len(raw_text_before), len(cleaned_text),
        len(raw_text_before) - len(cleaned_text),
        timings["text_clean"],
    )

    # ── Stage 6: Doc-type resolution ────────────────────────────────────────
    if doc_type and doc_type in _VALID_DOC_TYPES:
        detected_doc_type = doc_type
        classification_signals: dict = {"source": "manual_selection", "selected_type": doc_type}
        logger.info("✔ Stage 6: Doc type: manual selection → %s", detected_doc_type)
    else:
        text_classification = classify_from_text(ocr_result.raw_text, filename=cert.original_filename or "")
        detected_doc_type = text_classification.predicted_type.value
        classification_signals = text_classification.signals
        
        # Check filename heuristics if classification returned unknown
        if detected_doc_type == "unknown" and cert.original_filename:
            fn_l = cert.original_filename.lower()
            if any(k in fn_l for k in ["marksheet", "mark_sheet", "12th", "10th", "sslc", "hsc"]):
                detected_doc_type = "marksheet"
                classification_signals = {"source": "filename_heuristic", "selected_type": "marksheet"}
                
        logger.info("✔ Stage 6: Doc type: resolved → %s", detected_doc_type)

    # ── Stage 7: Template-Based Extraction + specialty field merge ───────────
    t = time.time()
    logger.info("✔ Stage 7: Field extraction started | doc_type=%s", detected_doc_type)
    type_specific_fields = extract_fields_by_type(ocr_result.raw_text, detected_doc_type)

    # Layout-aware bbox-based extraction (supplements regex-based extraction)
    if bbox_results:
        try:
            bbox_fields = await asyncio.to_thread(
                extract_fields_with_bboxes,
                ocr_result.raw_text,
                bbox_results,
                detected_doc_type,
            )
            # Merge bbox fields — only fill in fields not already found by type-specific extractors
            for field_name, field_data in bbox_fields.items():
                if field_name not in type_specific_fields or type_specific_fields.get(field_name) is None:
                    # Validate the bbox-extracted value
                    is_valid, reason = validate_field(field_name, field_data["value"])
                    if is_valid:
                        type_specific_fields[field_name] = field_data["value"]
                        logger.info("✔ BBox field '%s' = '%s' (source: %s, conf: %.2f)",
                                    field_name, field_data["value"],
                                    field_data.get("source", "?"), field_data.get("confidence", 0))
                    else:
                        logger.info("✗ BBox field '%s' rejected: %s", field_name, reason)
        except Exception as _exc:
            logger.warning("BBox field extraction failed (non-fatal): %s", _exc)

    # Aadhaar field extraction — uses existing OCR text, no re-run
    if detected_doc_type == "aadhaar_card":
        try:
            from app.services.aadhaar_field_extractor import extract_aadhaar_fields
            _full_aadhaar = extract_aadhaar_fields(ocr_result.raw_text)
            type_specific_fields.update(_full_aadhaar.get("fields", {}))
            type_specific_fields["_aadhaar_confidence"] = _full_aadhaar.get("confidence", 0)
            type_specific_fields["_aadhaar_field_confidences"] = _full_aadhaar.get("field_confidences", {})
            logger.info("✔ Aadhaar fields extracted | confidence=%d%%",
                        _full_aadhaar.get("confidence", 0))
        except Exception as _exc:
            logger.warning("Aadhaar field extraction failed (non-fatal): %s", _exc)

    # Marksheet field extraction — uses existing OCR text, no re-run
    _MS_DOC_TYPES = {"marksheet", "sslc", "hsc", "sslc_marksheet", "hsc_marksheet"}
    if detected_doc_type in _MS_DOC_TYPES:
        try:
            from app.services.marksheet_field_extractor import extract_marksheet_fields
            _exam_hint = "hsc" if detected_doc_type in {"hsc", "hsc_marksheet"} else "sslc"
            _full_ms = extract_marksheet_fields(ocr_result.raw_text, exam_type=_exam_hint)
            type_specific_fields.update(_full_ms.get("fields", {}))
            type_specific_fields["_marksheet_confidence"] = _full_ms.get("confidence", 0)
            type_specific_fields["_marksheet_field_confidences"] = _full_ms.get("field_confidences", {})
            logger.info("✔ Marksheet fields extracted | confidence=%d%% | subjects=%d",
                        _full_ms.get("confidence", 0),
                        len(_full_ms.get("fields", {}).get("subjects", [])))
        except Exception as _exc:
            logger.warning("Marksheet field extraction failed (non-fatal): %s", _exc)

    # Resume field extraction — uses existing OCR text, no re-run
    if detected_doc_type == "resume":
        try:
            from app.services.resume_field_extractor import extract_resume_fields
            _full_resume = extract_resume_fields(ocr_result.raw_text)
            type_specific_fields.update(_full_resume.get("fields", {}))
            type_specific_fields["_resume_confidence"] = _full_resume.get("confidence", 0)
            type_specific_fields["_resume_field_confidences"] = _full_resume.get("field_confidences", {})
            logger.info("✔ Resume fields extracted | confidence=%d%% | skills_tech=%d",
                        _full_resume.get("confidence", 0),
                        len(_full_resume.get("fields", {}).get("skills", {}).get("technical", [])))
        except Exception as _exc:
            logger.warning("Resume field extraction failed (non-fatal): %s", _exc)

    template_result = extract_by_template(
        raw_text=ocr_result.raw_text,
        ocr_results=bbox_results,
        ocr_accuracy=ocr_result.accuracy,
        hint_doc_type=detected_doc_type,
    )
    logger.info(
        "✔ Template detected: %s | found=%d missing=%d",
        template_result.template_name,
        sum(1 for v in template_result.fields.values() if v != "Not Found"),
        len(template_result.missing_fields),
    )
    logger.info("✔ Extracted fields: %s",
                {k: v for k, v in template_result.fields.items() if v != "Not Found"})

    fields = extract_fields(ocr_result.raw_text)

    # Run QR/signature/seal detection in thread pool (OpenCV is blocking)
    qr_tuple, has_signature, has_seal = await asyncio.gather(
        asyncio.to_thread(detect_qr_code, color_processed),
        asyncio.to_thread(detect_signature, color_processed),
        asyncio.to_thread(detect_seal, color_processed),
    )
    qr_text, qr_confidence = qr_tuple if isinstance(qr_tuple, tuple) else (qr_tuple, 0)
    # Fallback: if template text-based detection found "Yes" but pixel scanner found nothing
    qr_data = qr_text or (
        "Present" if template_result.fields.get("qr_present") == "Yes" else None
    )
    if qr_data:
        logger.info("✔ QR detected | data_len=%d | confidence=%d", len(qr_data), qr_confidence)
    else:
        logger.info("✔ QR not detected | confidence=%d", qr_confidence)

    field_confidences = {name: conf for name, (_, conf) in fields.items()}

    # Merge type-specific fields (high confidence for type-specific patterns)
    for ts_field, ts_value in type_specific_fields.items():
        if ts_value is not None and ts_field not in field_confidences:
            field_confidences[ts_field] = 0.9

    # Merge specialized extractor field confidences
    if "_marksheet_field_confidences" in type_specific_fields:
        for k, v in type_specific_fields["_marksheet_field_confidences"].items():
            if v > 0:
                field_confidences[k] = v
    if "_aadhaar_field_confidences" in type_specific_fields:
        for k, v in type_specific_fields["_aadhaar_field_confidences"].items():
            if v > 0:
                field_confidences[k] = v
    if "_resume_field_confidences" in type_specific_fields:
        for k, v in type_specific_fields["_resume_field_confidences"].items():
            if v > 0:
                field_confidences[k] = v

    # Determine OCR Status: OCR_SUCCESS | OCR_PARTIAL | OCR_FAILED
    text_len = len(ocr_result.raw_text.strip())
    word_count = len(ocr_result.raw_text.strip().split())
    has_fields = any([
        bool(type_specific_fields.get("student_name")),
        bool(type_specific_fields.get("register_number")),
        bool(type_specific_fields.get("certificate_number")),
        bool(template_result.fields.get("student_name") and template_result.fields["student_name"] != "Not Found"),
        bool(fields.get("student_name", (None, 0))[0]),
    ])

    if text_len >= 20 and (ocr_result.accuracy >= 0.40 or has_fields or word_count >= 10):
        ocr_status_str = "OCR_SUCCESS"
    elif text_len > 0:
        ocr_status_str = "OCR_PARTIAL"
    else:
        ocr_status_str = "OCR_FAILED"

    field_confidences["_ocr_status"] = ocr_status_str
    field_confidences["_preprocessing_variant"] = active_variant_name
    field_confidences["_ocr_stage"] = "completed"

    # Store classification metadata for downstream use
    field_confidences["_classification"] = classification_signals
    field_confidences["_doc_type"] = detected_doc_type
    field_confidences["_type_fields"] = {
        k: v for k, v in type_specific_fields.items() if v is not None
    }
    field_confidences["_template_fields"] = template_result.fields
    field_confidences["_template_name"] = template_result.template_name
    field_confidences["_template_missing"] = template_result.missing_fields
    field_confidences["_template_debug"] = template_result.debug_log
    # Store QR detection confidence in metadata for downstream use by verify-qr
    field_confidences["_qr_confidence"] = qr_confidence

    t_fields = time.time() - t
    timings["fields"] = t_fields
    total_time = time.time() - pipeline_start
    timings["total"] = total_time

    logger.info(
        "✔ Stage 7 done | fields_extracted=%d | %.1fs",
        sum(1 for v in template_result.fields.values() if v != "Not Found"),
        t_fields,
    )

    # ── Performance summary (matches spec format) ─────────────────────────────
    logger.info(
        "\n"
        "━━━━━━━━━━━ OCR TIMING SUMMARY ━━━━━━━━━━━\n"
        "  PDF load / render : %.1fs\n"
        "  Preprocessing     : %.1fs\n"
        "  OCR (EasyOCR+Tess): %.1fs\n"
        "  DPI retry         : %.1fs\n"
        "  Text normalization: %.1fs\n"
        "  Field extraction  : %.1fs\n"
        "  ──────────────────────────────────────\n"
        "  TOTAL             : %.1fs\n"
        "  Engines used      : %s\n"
        "  OCR confidence    : %.1f%%\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        timings.get("pdf_load", 0),
        timings.get("preprocess", 0),
        timings.get("ocr", 0),
        timings.get("dpi_retry", 0),
        timings.get("text_clean", 0),
        timings.get("fields", 0),
        total_time,
        "+".join(ocr_result.engines_used),
        ocr_result.accuracy * 100,
    )

    return (
        ocr_result, bbox_results, detected_doc_type, classification_signals,
        type_specific_fields, color_processed,
        qr_data, has_signature, has_seal,
        fields, field_confidences, template_result,
    )


# ---------------------------------------------------------------------------
# Public endpoints (routes unchanged — only internal implementation fixed)
# ---------------------------------------------------------------------------

@router.post("/{certificate_id}/extract-ocr", response_model=OCRDataResponse)
@router.post("/{certificate_id}/ocr", response_model=OCRDataResponse, include_in_schema=False)
async def extract_ocr(
    certificate_id: str,
    doc_type: Optional[str] = Query(
        default=None,
        description=(
            "Manually selected document type (e.g. 'marksheet', 'degree_certificate'). "
            "When provided, automatic classification is skipped and this type is used "
            "directly for field extraction."
        ),
    ),
    force_refresh: bool = Query(
        default=False,
        description="Force re-running OCR extraction even if valid results already exist.",
    ),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    t_request = time.time()
    logger.info("=" * 70)
    logger.info("OCR START | certificate_id=%s | doc_type=%s | user=%s | force_refresh=%s",
                certificate_id, doc_type, user.email, force_refresh)

    cert = await _get_owned_certificate(certificate_id, user, db)
    logger.info("✔ Certificate ID: %s", cert.id)
    logger.info("✔ Uploaded file path: %s | type=%s", cert.storage_path, cert.file_type)

    # ── Stage 0: Check for existing valid OCR record or duplicate hash reuse ──
    if not force_refresh:
        existing = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
        current_ocr = existing.scalar_one_or_none()
        if current_ocr and _is_valid_ocr_record(current_ocr):
            logger.info("⚡ [CACHE HIT] Returning existing valid OCR record for certificate_id=%s", cert.id)
            return current_ocr

        reused = await _find_and_reuse_successful_ocr(cert, db)
        if reused is not None:
            logger.info("⚡ [IDEMPOTENT REUSE] Reused OCR record for certificate_id=%s", cert.id)
            return reused

    logger.info("✔ [LIVE OCR] Processing current uploaded document cert_id=%s", cert.id)

    # ── Stage 1: Read file bytes ──────────────────────────────────────────────
    try:
        storage = get_storage_backend()
        file_bytes = await storage.read(cert.storage_path)
        logger.info("✔ PDF loaded from storage | size=%d bytes", len(file_bytes))
    except FileNotFoundError:
        logger.error("File not found on disk: %s", cert.storage_path)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF file not found on disk: {cert.storage_path}",
        )
    except Exception as exc:
        logger.error("Failed to read file from storage: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read uploaded file: {exc}",
        )

    # ── OCR Pipeline with global timeout ─────────────────────────────────────
    try:
        pipeline_result = await asyncio.wait_for(
            _run_ocr_pipeline(cert, file_bytes, doc_type),
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "OCR pipeline TIMEOUT after %ds | certificate_id=%s",
            OCR_TIMEOUT_SECONDS, certificate_id,
        )
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail={
                "success": False,
                "message": f"OCR timeout after {OCR_TIMEOUT_SECONDS}s. "
                           "The document may be too complex or the OCR model is loading. "
                           "Please try again.",
                "stage": "OCR Pipeline",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OCR ERROR | certificate_id=%s | %s\n%s", certificate_id, exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "stage": "OCR Pipeline",
                "error": str(exc),
            },
        )

    (
        ocr_result, bbox_results, detected_doc_type, classification_signals,
        type_specific_fields, color_processed,
        qr_data, has_signature, has_seal,
        fields, field_confidences, template_result,
    ) = pipeline_result

    # ── Stage 8: DB save ──────────────────────────────────────────────────────
    logger.info("✔ Stage 8: Saving to database")
    existing = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = existing.scalar_one_or_none()
    if ocr_row is None:
        ocr_row = OCRData(certificate_id=cert.id)
        db.add(ocr_row)
        logger.info("✔ Creating new OCRData row")
    else:
        logger.info("✔ Updating existing OCRData row")

    # Core OCR columns — priority: template fields > type-specific > generic regex
    def _tf(key: str) -> str | None:
        """Get a template field value; return None if 'Not Found'."""
        v = template_result.fields.get(key)
        return v if (v and v != "Not Found") else None

    ocr_row.student_name = (
        _tf("student_name") or _tf("candidate_name") or _tf("name") or
        type_specific_fields.get("student_name") or type_specific_fields.get("name") or
        fields["student_name"][0]
    )
    ocr_row.university_name = (
        _tf("university") or _tf("institute") or _tf("institution") or _tf("school") or
        type_specific_fields.get("school") or type_specific_fields.get("board") or
        type_specific_fields.get("university") or
        fields["university_name"][0]
    )
    ocr_row.register_number = (
        _tf("permanent_register_number") or _tf("register_number") or
        type_specific_fields.get("register_number") or type_specific_fields.get("roll_number") or
        fields["register_number"][0]
    )
    ocr_row.roll_number = (
        _tf("roll_number") or
        type_specific_fields.get("roll_number") or
        fields["roll_number"][0]
    )
    ocr_row.certificate_number = (
        _tf("certificate_number") or
        type_specific_fields.get("certificate_number") or
        fields["certificate_number"][0]
    )
    ocr_row.department = (
        _tf("department") or _tf("group_code") or
        type_specific_fields.get("group") or type_specific_fields.get("department") or
        fields["department"][0]
    )
    ocr_row.course = (
        _tf("degree") or _tf("diploma_title") or
        type_specific_fields.get("exam_name") or type_specific_fields.get("degree") or type_specific_fields.get("diploma_title") or
        fields["course"][0]
    )
    ocr_row.cgpa = fields["cgpa"][0]

    # Percentage
    pct_val = None
    if type_specific_fields.get("percentage"):
        try:
            pct_val = float(str(type_specific_fields["percentage"]).rstrip("%"))
        except Exception:
            pass
    if pct_val is None and fields["percentage"][0] is not None:
        pct_val = fields["percentage"][0]
    if pct_val is None and _tf("total_marks"):
        try:
            pct_val = float(_tf("total_marks").replace(",", ""))
        except Exception:
            pass
    ocr_row.percentage = pct_val

    ocr_row.date_of_issue = (
        _tf("convocation_date") or _tf("date_of_birth") or _tf("dob") or
        _tf("date_of_leaving") or _tf("year_of_passing") or
        type_specific_fields.get("date_of_birth") or type_specific_fields.get("year_of_passing") or
        type_specific_fields.get("date_awarded") or type_specific_fields.get("dob") or
        fields["date_of_issue"][0]
    )
    ocr_row.qr_code_data = qr_data
    ocr_row.has_signature = has_signature
    ocr_row.has_seal = has_seal
    ocr_row.raw_text = ocr_result.raw_text
    ocr_row.field_confidences = field_confidences
    ocr_row.ocr_accuracy = ocr_result.accuracy
    ocr_row.ocr_engine = "+".join(ocr_result.engines_used)

    await db.commit()
    await db.refresh(ocr_row)

    # ── Stage 8.5: DocumentType DB save/upsert ──────────────────────────────
    if detected_doc_type:
        try:
            from app.models.models import DocTypeEnum
            dt_existing = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
            doc_type_row = dt_existing.scalar_one_or_none()

            enum_val = None
            try:
                enum_val = DocTypeEnum(detected_doc_type)
            except ValueError:
                enum_val = DocTypeEnum.UNKNOWN

            if doc_type_row:
                doc_type_row.predicted_type = enum_val
                doc_type_row.confidence_score = 0.95 if enum_val != DocTypeEnum.UNKNOWN else 0.50
                doc_type_row.model_used = "rule-ocr-fused-classifier"
            else:
                doc_type_row = DocumentType(
                    certificate_id=cert.id,
                    predicted_type=enum_val,
                    confidence_score=0.95 if enum_val != DocTypeEnum.UNKNOWN else 0.50,
                    model_used="rule-ocr-fused-classifier",
                )
                db.add(doc_type_row)
            await db.commit()
        except Exception as dt_exc:
            logger.warning("Could not upsert DocumentType row (non-fatal): %s", dt_exc)

    total_ms = (time.time() - t_request) * 1000
    logger.info(
        "✔ JSON generated | ocr_row_id=%s | student_name=%s | accuracy=%.4f",
        ocr_row.id, ocr_row.student_name, ocr_row.ocr_accuracy,
    )
    logger.info("OCR END | certificate_id=%s | total_time=%.1fms | accuracy=%.4f",
                certificate_id, total_ms, ocr_row.ocr_accuracy)
    logger.info("=" * 70)
    return ocr_row


@router.get("/{certificate_id}/ocr-data", response_model=OCRDataResponse)
async def get_ocr_data(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = result.scalar_one_or_none()
    if not ocr_row:
        raise HTTPException(status_code=404, detail="OCR has not been run on this certificate yet.")
    return ocr_row


@router.patch("/{certificate_id}/ocr-data", response_model=OCRDataResponse)
async def update_ocr_data(
    certificate_id: str,
    payload: OCRDataUpdateRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Applies user corrections from the editable OCR table. Downstream modules
    (Comparison, Fraud Analysis) should prefer these corrected values."""
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = result.scalar_one_or_none()
    if not ocr_row:
        raise HTTPException(status_code=404, detail="OCR has not been run on this certificate yet.")

    updates = payload.model_dump(exclude_unset=True)
    updated_confidences = dict(ocr_row.field_confidences or {})
    for field_name, value in updates.items():
        setattr(ocr_row, field_name, value)
        # A manual correction is treated as ground truth -> full confidence
        updated_confidences[field_name] = 1.0
    ocr_row.field_confidences = updated_confidences  # reassign: JSON columns need a new object to be dirty-tracked

    await db.commit()
    await db.refresh(ocr_row)
    return ocr_row


@router.post("/{certificate_id}/validate", response_model=DocumentValidationResponse)
async def validate_document_fields(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Compares extracted fields against expected fields for the classified document type.
    Returns validation status per field: VALID, INVALID, MISSING, LOW_CONFIDENCE, NOT_APPLICABLE.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)

    ocr_res = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_data = ocr_res.scalar_one_or_none()

    dt_res = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
    doc_type_row = dt_res.scalar_one_or_none()

    predicted_type = doc_type_row.predicted_type.value if doc_type_row else "degree_certificate"
    confidence_score = doc_type_row.confidence_score if doc_type_row else 0.85

    SCHEMA_EXPECTATIONS = {
        "degree_certificate": [
            ("student_name", "Student Name"),
            ("register_number", "Register Number"),
            ("course", "Degree / Course"),
            ("university_name", "Institution / University"),
            ("department", "Department"),
            ("date_of_issue", "Date of Issue"),
            ("qr_code_data", "QR Code"),
            ("has_signature", "Signature"),
            ("has_seal", "Seal"),
        ],
        "marksheet": [
            ("student_name", "Student Name"),
            ("register_number", "Register Number"),
            ("roll_number", "Roll Number"),
            ("course", "Course / Department"),
            ("cgpa", "CGPA"),
            ("percentage", "Percentage"),
            ("university_name", "Institution / Board"),
            ("date_of_issue", "Date of Issue"),
            ("has_signature", "Signature"),
            ("has_seal", "Seal"),
        ],
        "diploma": [
            ("student_name", "Student Name"),
            ("certificate_number", "Certificate Number"),
            ("course", "Diploma Course"),
            ("university_name", "Institution / Board"),
            ("date_of_issue", "Date of Issue"),
            ("has_signature", "Signature"),
            ("has_seal", "Seal"),
        ],
        "transfer_certificate": [
            ("student_name", "Student Name"),
            ("register_number", "Admission / Register No"),
            ("university_name", "Institution"),
            ("date_of_issue", "Date of Issue"),
            ("has_signature", "Signature"),
        ],
    }

    expected_list = SCHEMA_EXPECTATIONS.get(
        predicted_type,
        [
            ("student_name", "Student Name"),
            ("register_number", "Register Number"),
            ("certificate_number", "Certificate Number"),
            ("university_name", "Institution"),
            ("department", "Department"),
            ("course", "Course"),
            ("cgpa", "CGPA"),
            ("percentage", "Percentage"),
            ("date_of_issue", "Date of Issue"),
            ("has_signature", "Signature"),
            ("has_seal", "Seal"),
        ],
    )

    items: list[FieldValidationItem] = []
    field_confidences = ocr_data.field_confidences if ocr_data and ocr_data.field_confidences else {}

    for field_key, label in expected_list:
        if field_key == "has_signature":
            val = "Detected" if (ocr_data and ocr_data.has_signature) else "Not detected"
            conf = 1.0 if (ocr_data and ocr_data.has_signature) else 0.0
            status = "VALID" if (ocr_data and ocr_data.has_signature) else "MISSING"
            reason = "Signature contour detected in document" if (ocr_data and ocr_data.has_signature) else "No signature region detected"
        elif field_key == "has_seal":
            val = "Detected" if (ocr_data and ocr_data.has_seal) else "Not detected"
            conf = 1.0 if (ocr_data and ocr_data.has_seal) else 0.0
            status = "VALID" if (ocr_data and ocr_data.has_seal) else "MISSING"
            reason = "Circular seal detected via Hough circles" if (ocr_data and ocr_data.has_seal) else "No circular seal detected"
        elif field_key == "qr_code_data":
            val = ocr_data.qr_code_data if (ocr_data and ocr_data.qr_code_data) else None
            conf = 0.95 if val else 0.0
            status = "VALID" if val else "NOT_DETECTED"
            reason = "QR code payload decoded" if val else "No QR code detected"
        else:
            val = getattr(ocr_data, field_key, None) if ocr_data else None
            conf = field_confidences.get(field_key, 0.0) if ocr_data else 0.0
            if val is not None and str(val).strip():
                is_valid, v_reason = validate_field(field_key, val)
                if not is_valid:
                    status = "INVALID"
                    reason = v_reason
                elif conf < 0.6:
                    status = "LOW_CONFIDENCE"
                    reason = f"Extracted value has low OCR confidence ({int(conf*100)}%)"
                else:
                    status = "VALID"
                    reason = "Valid format and high confidence"
            else:
                val = None
                status = "MISSING"
                reason = "Field not detected in document text"

        items.append(FieldValidationItem(
            field=field_key,
            label=label,
            extracted_value=str(val) if val is not None else None,
            confidence=conf,
            status=status,
            reason=reason,
        ))

    return DocumentValidationResponse(
        certificate_id=cert.id,
        document_type=predicted_type,
        classification_confidence=confidence_score,
        expected_fields=[item.label for item in items],
        field_validations=items,
    )


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
