"""
MODULE 5 - DOCUMENT COMPARISON API

POST /api/v1/comparisons/compare-pair           -> Compare Document A and Document B by certificate_id
POST /api/v1/comparisons/upload-and-compare      -> Upload Document B and compare against Document A
POST /api/v1/comparisons/{group_id}/run          -> Compares all OCR'd documents in the group
GET  /api/v1/comparisons/{group_id}              -> Returns stored group comparison
"""
import logging
import os
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_verified_user
from app.db.database import get_db
from app.models.models import Certificate, DocumentComparison, DocumentType, OCRData, User
from app.schemas.comparison_schemas import DocumentComparisonResponse
from app.services.document_comparison import compare_documents

logger = logging.getLogger("certiverify.comparison")

router = APIRouter(prefix="/api/v1/comparisons", tags=["Document Comparison"])


# ---------------------------------------------------------------------------
# Pydantic Schemas for Pair Comparison
# ---------------------------------------------------------------------------

class ComparePairRequest(BaseModel):
    certificate_id_a: str
    certificate_id_b: str


class FieldComparisonRow(BaseModel):
    field: str
    field_label: str
    doc_a_value: Optional[str] = None
    doc_b_value: Optional[str] = None
    status: str  # "MATCH" | "MISMATCH" | "UNKNOWN / NOT DETECTED"
    similarity: Optional[float] = None


class CertificatePairComparisonResponse(BaseModel):
    certificate_id_a: str
    certificate_id_b: str
    doc_a_filename: str
    doc_b_filename: str
    doc_a_type: str
    doc_b_type: str
    comparison_rows: List[FieldComparisonRow]
    field_comparisons: Optional[List[FieldComparisonRow]] = None
    matched_count: int
    mismatched_count: int
    unknown_count: int
    consistency_percentage: float
    overall_match_status: Optional[str] = None
    summary_narrative: str
    summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    s = text.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_field_val(ocr_row: OCRData | None, field_name: str) -> Optional[str]:
    if not ocr_row:
        return None
    val = getattr(ocr_row, field_name, None)
    if val is None and hasattr(ocr_row, "fields") and isinstance(ocr_row.fields, dict):
        val = ocr_row.fields.get(field_name)

    if val is None:
        aliases = {
            "student_name": ["name", "candidate_name", "full_name"],
            "register_number": ["certificate_number", "roll_number", "reg_no"],
            "university_name": ["institution", "school", "board", "college"],
            "date_of_issue": ["issue_date", "date"],
            "course": ["degree", "program", "course_name"],
            "department": ["branch", "stream", "specialization"],
            "qr_code_data": ["qr_data", "qr_payload"],
        }
        for alias in aliases.get(field_name, []):
            if hasattr(ocr_row, "fields") and isinstance(ocr_row.fields, dict):
                val = ocr_row.fields.get(alias)
                if val:
                    break

    if val is None:
        return None

    val_str = str(val).strip()
    if val_str.lower() in {"not detected", "not found", "n/a", "pending", "none", "null", ""}:
        return None
    return val_str


def _compare_field_values(val_a: Optional[str], val_b: Optional[str]) -> tuple[str, Optional[float]]:
    """
    Returns (status, similarity_pct)
    status ∈ {"MATCH", "MISMATCH", "UNKNOWN / NOT DETECTED"}
    Rule: Missing data in either or both documents MUST produce UNKNOWN / NOT DETECTED (never automatic MISMATCH).
    """
    if val_a is None or val_b is None:
        return "UNKNOWN / NOT DETECTED", None

    norm_a = _normalize_text(val_a)
    norm_b = _normalize_text(val_b)

    if norm_a == norm_b:
        return "MATCH", 100.0

    try:
        from rapidfuzz import fuzz
        sim_pct = float(fuzz.token_sort_ratio(norm_a, norm_b))
    except ImportError:
        from difflib import SequenceMatcher
        sim_pct = round(SequenceMatcher(None, norm_a, norm_b).ratio() * 100, 1)

    if sim_pct >= 82.0:
        return "MATCH", sim_pct
    else:
        return "MISMATCH", sim_pct


async def _ensure_ocr_data(cert: Certificate, db: AsyncSession) -> OCRData:
    result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = result.scalar_one_or_none()
    if ocr_row:
        return ocr_row

    # Run OCR pipeline for cert
    from app.api.ocr import _run_ocr_pipeline
    from app.services.storage_service import get_storage_backend

    dt_res = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
    dt_row = dt_res.scalar_one_or_none()
    hint_type = dt_row.predicted_type.value if dt_row else None

    storage = get_storage_backend()
    file_bytes = await storage.read(cert.storage_path)

    (
        ocr_result, bbox_results, detected_doc_type, classification_signals,
        type_specific_fields, color_processed,
        qr_data, has_signature, has_seal,
        fields, field_confidences, template_result,
    ) = await _run_ocr_pipeline(cert, file_bytes, hint_type)

    def _extract_field_val(key: str) -> str | None:
        v = type_specific_fields.get(key)
        if v and str(v).strip():
            return str(v).strip()
        f_val = fields.get(key)
        if isinstance(f_val, (tuple, list)) and len(f_val) > 0:
            return str(f_val[0]).strip() if f_val[0] else None
        elif isinstance(f_val, str) and f_val.strip():
            return f_val.strip()
        return None

    ocr_row = OCRData(
        certificate_id=cert.id,
        raw_text=ocr_result.raw_text,
        ocr_accuracy=ocr_result.accuracy,
        student_name=_extract_field_val("student_name"),
        register_number=_extract_field_val("register_number"),
        university_name=_extract_field_val("university_name"),
        date_of_issue=_extract_field_val("date_of_issue"),
        course=_extract_field_val("course"),
        department=_extract_field_val("department"),
        qr_code_data=qr_data,
        has_signature=has_signature,
        has_seal=has_seal,
        field_confidences=field_confidences,
    )
    db.add(ocr_row)
    await db.commit()
    await db.refresh(ocr_row)
    return ocr_row


async def _get_doc_type_str(cert_id: str, db: AsyncSession) -> str:
    dt_res = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert_id))
    dt_row = dt_res.scalar_one_or_none()
    if dt_row and dt_row.predicted_type:
        return dt_row.predicted_type.value.replace("_", " ").title()
    return "Document"


# ---------------------------------------------------------------------------
# Pair Comparison Endpoints
# ---------------------------------------------------------------------------

@router.post("/compare-pair", response_model=CertificatePairComparisonResponse)
async def compare_pair(
    payload: ComparePairRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert_a_res = await db.execute(
        select(Certificate).where(Certificate.id == payload.certificate_id_a, Certificate.owner_id == user.id)
    )
    cert_a = cert_a_res.scalar_one_or_none()
    if not cert_a:
        raise HTTPException(status_code=404, detail="Document A certificate not found.")

    cert_b_res = await db.execute(
        select(Certificate).where(Certificate.id == payload.certificate_id_b, Certificate.owner_id == user.id)
    )
    cert_b = cert_b_res.scalar_one_or_none()
    if not cert_b:
        raise HTTPException(status_code=404, detail="Document B certificate not found.")

    ocr_a = await _ensure_ocr_data(cert_a, db)
    ocr_b = await _ensure_ocr_data(cert_b, db)

    doc_a_type = await _get_doc_type_str(cert_a.id, db)
    doc_b_type = await _get_doc_type_str(cert_b.id, db)

    target_fields = [
        ("student_name", "Candidate Name"),
        ("register_number", "Certificate / Registration Number"),
        ("university_name", "Issuing Institution"),
        ("date_of_issue", "Issue Date"),
        ("course", "Course / Degree"),
        ("department", "Department / Specialization"),
        ("qr_code_data", "QR Payload Cryptographic Signature"),
    ]

    rows: List[FieldComparisonRow] = []
    for field_key, label in target_fields:
        val_a = _get_field_val(ocr_a, field_key)
        val_b = _get_field_val(ocr_b, field_key)
        st, sim = _compare_field_values(val_a, val_b)
        rows.append(FieldComparisonRow(
            field=field_key,
            field_label=label,
            doc_a_value=val_a,
            doc_b_value=val_b,
            status=st,
            similarity=sim,
        ))

    matched_cnt = sum(1 for r in rows if r.status == "MATCH")
    mismatched_cnt = sum(1 for r in rows if r.status == "MISMATCH")
    unknown_cnt = sum(1 for r in rows if r.status == "UNKNOWN / NOT DETECTED")

    total_eval = matched_cnt + mismatched_cnt
    consistency_pct = round((matched_cnt / total_eval) * 100, 1) if total_eval > 0 else 100.0

    mismatched_labels = [r.field_label for r in rows if r.status == "MISMATCH"]
    if mismatched_cnt > 0:
        discrepancies_text = f"Discrepancies identified in {', '.join(mismatched_labels)}."
    else:
        discrepancies_text = "No attribute discrepancies identified across available data fields."

    summary = (
        f"Side-by-side comparative analysis between Document A ({cert_a.original_filename}, ID: {cert_a.id}) "
        f"and Document B ({cert_b.original_filename}, ID: {cert_b.id}). Evaluated {len(rows)} attribute fields: "
        f"{matched_cnt} MATCH, {mismatched_cnt} MISMATCH, and {unknown_cnt} UNKNOWN / NOT DETECTED. "
        f"Overall field consistency score: {consistency_pct}%. {discrepancies_text}"
    )

    match_status = "MATCH" if consistency_pct >= 80 else ("PARTIAL MATCH" if consistency_pct >= 40 else "MISMATCH")

    return CertificatePairComparisonResponse(
        certificate_id_a=cert_a.id,
        certificate_id_b=cert_b.id,
        doc_a_filename=cert_a.original_filename,
        doc_b_filename=cert_b.original_filename,
        doc_a_type=doc_a_type,
        doc_b_type=doc_b_type,
        comparison_rows=rows,
        field_comparisons=rows,
        matched_count=matched_cnt,
        mismatched_count=mismatched_cnt,
        unknown_count=unknown_cnt,
        consistency_percentage=consistency_pct,
        overall_match_status=match_status,
        summary_narrative=summary,
        summary=summary,
    )


@router.post("/upload-and-compare", response_model=CertificatePairComparisonResponse)
async def upload_and_compare(
    certificate_id_a: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert_a_res = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id_a, Certificate.owner_id == user.id)
    )
    cert_a = cert_a_res.scalar_one_or_none()
    if not cert_a:
        raise HTTPException(status_code=404, detail="Document A certificate not found.")

    from app.services.storage_service import get_storage_backend
    storage = get_storage_backend()
    storage_path, size_bytes, sha256_hash = await storage.save(file, subdir=f"certificates/{user.id}")
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")

    cert_b = Certificate(
        id=str(uuid.uuid4()),
        group_id=cert_a.group_id or str(uuid.uuid4()),
        owner_id=user.id,
        original_filename=file.filename or "Document_B",
        storage_path=storage_path,
        file_type=ext,
        file_size_bytes=size_bytes,
        sha256_hash=sha256_hash,
    )
    db.add(cert_b)
    await db.commit()
    await db.refresh(cert_b)

    return await compare_pair(
        payload=ComparePairRequest(certificate_id_a=cert_a.id, certificate_id_b=cert_b.id),
        user=user,
        db=db,
    )


# ---------------------------------------------------------------------------
# Legacy Group Comparison Endpoints
# ---------------------------------------------------------------------------

@router.post("/{group_id}/run", response_model=DocumentComparisonResponse)
async def run_comparison(
    group_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    ocr_rows = await _get_ocr_rows_for_group(group_id, user, db)

    if len(ocr_rows) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Document comparison needs at least 2 documents in this group with OCR "
                "already extracted."
            ),
        )

    result = compare_documents(ocr_rows)

    existing = await db.execute(select(DocumentComparison).where(DocumentComparison.group_id == group_id))
    comparison_row = existing.scalar_one_or_none()

    if comparison_row is None:
        comparison_row = DocumentComparison(group_id=group_id)
        db.add(comparison_row)

    comparison_row.matching_fields = result.matching_fields
    comparison_row.mismatched_fields = result.mismatched_fields
    comparison_row.missing_fields = result.missing_fields
    comparison_row.consistency_percentage = result.consistency_percentage
    comparison_row.details = result.details

    await db.commit()
    await db.refresh(comparison_row)
    return comparison_row


@router.get("/{group_id}", response_model=DocumentComparisonResponse)
async def get_comparison(
    group_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_ocr_rows_for_group(group_id, user, db, require_ocr=False)

    result = await db.execute(select(DocumentComparison).where(DocumentComparison.group_id == group_id))
    comparison_row = result.scalar_one_or_none()
    if not comparison_row:
        raise HTTPException(status_code=404, detail="No comparison has been run for this document group yet.")
    return comparison_row


async def _get_ocr_rows_for_group(
    group_id: str, user: User, db: AsyncSession, require_ocr: bool = True
) -> list[OCRData]:
    cert_result = await db.execute(
        select(Certificate).where(Certificate.group_id == group_id, Certificate.owner_id == user.id)
    )
    certs = cert_result.scalars().all()
    if not certs:
        raise HTTPException(status_code=404, detail="No certificates found for this group.")

    cert_ids = [c.id for c in certs]
    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id.in_(cert_ids)))
    ocr_rows = list(ocr_result.scalars().all())

    if require_ocr and len(ocr_rows) < len(certs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more documents in this group have not had OCR run yet.",
        )
    return ocr_rows

