"""
DIRECT COMPARE API — intelligent in-memory document comparison
==============================================================

POST /api/v1/direct-compare
    Accepts 2–5 uploaded files + their document types.
    Runs OCR on all files in memory (no DB writes) and returns a
    field-by-field comparison result with:
    - RapidFuzz fuzzy matching (replaces difflib)
    - partial match status (60–81% similarity → yellow)
    - document-pair-specific field sets
    - AI-generated summary bullets
    - comparison_score (0-100)

POST /api/v1/direct-compare/pdf
    Same payload, streams a PDF comparison report.
    No DB writes.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import datetime
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.image_preprocessing import load_image_as_array, preprocess_for_ocr
from app.services.ocr_engine import extract_text, extract_with_bboxes
from app.services.ocr_text_cleaner import clean_ocr_text
from app.services.template_extractor import extract_by_template
from app.api.deps import get_current_verified_user
from app.models.models import User

def _normalize_text_for_comparison(text: str) -> str:
    if not text:
        return ""
    s = text.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})", r"\1/\2/\3", s)
    return s

try:
    from rapidfuzz import fuzz as _rfuzz
    def _text_similar_score(a: str, b: str) -> float:
        """Return 0-1 similarity using rapidfuzz token_sort_ratio with text normalization."""
        na = _normalize_text_for_comparison(a)
        nb = _normalize_text_for_comparison(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        return _rfuzz.token_sort_ratio(na, nb) / 100.0
except ImportError:
    from difflib import SequenceMatcher
    def _text_similar_score(a: str, b: str) -> float:  # type: ignore[misc]
        na = _normalize_text_for_comparison(a)
        nb = _normalize_text_for_comparison(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        return SequenceMatcher(None, na, nb).ratio()

logger = logging.getLogger("certiverify.direct_compare")

router = APIRouter(prefix="/api/v1", tags=["Direct Document Comparison"])

# Similarity thresholds
_MATCH_THRESHOLD   = 0.82   # >= 82% → green match
_PARTIAL_THRESHOLD = 0.60   # 60–81% → yellow partial match
# Below 60% → red mismatch


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class FieldComparisonRow(BaseModel):
    field: str
    field_label: str
    doc1_value: Optional[str] = None
    doc2_value: Optional[str] = None
    similarity: Optional[float] = None   # 0-100, None for missing
    status: str  # "match" | "partial" | "mismatch" | "missing"


class DirectCompareResponse(BaseModel):
    doc1_type: str
    doc2_type: str
    doc1_fields: dict
    doc2_fields: dict
    comparison: list[FieldComparisonRow]
    similarity_percentage: float
    comparison_score: float              # alias for similarity_percentage (0-100)
    matched_fields: list[str]           # field names that matched
    mismatched_fields: list[str]        # field names that mismatched
    missing_fields: list[str]           # field names that were missing
    doc1_ocr_accuracy: float
    doc2_ocr_accuracy: float
    pair_hint: str                      # e.g. "Degree Certificate ↔ Resume"
    ai_summary: list[str]              # human-readable bullet sentences
    documents_compared: int = 2
    comparison_type: str = "field_comparison"  # "field_comparison" | "identical_document"



# ---------------------------------------------------------------------------
# Human-readable field labels
# ---------------------------------------------------------------------------

_FIELD_LABELS: dict[str, str] = {
    "student_name":               "Student Name",
    "candidate_name":             "Candidate Name",
    "name":                       "Name",
    "aadhaar_number":             "Aadhaar Number",
    "dob":                        "Date of Birth",
    "date_of_birth":              "Date of Birth",
    "gender":                     "Gender",
    "address":                    "Address",
    "pin_code":                   "PIN Code",
    "vid":                        "VID",
    "roll_number":                "Roll Number",
    "register_number":            "Register Number",
    "permanent_register_number":  "Permanent Register Number",
    "school_name":                "School Name",
    "board":                      "Board / University",
    "medium":                     "Medium",
    "result":                     "Result",
    "total_marks":                "Total Marks",
    "group_code":                 "Group / Stream",
    "session":                    "Session / Year",
    "certificate_number":         "Certificate Number",
    "admission_number":           "Admission Number",
    "tc_number":                  "TC Number",
    "conduct":                    "Conduct",
    "date_of_leaving":            "Date of Leaving",
    "institution":                "Institution",
    "diploma_title":              "Diploma / Course",
    "institute":                  "Institute",
    "year_of_passing":            "Year of Passing",
    "degree":                     "Degree",
    "department":                 "Department",
    "university":                 "University",
    "convocation_date":           "Convocation Date",
    "date_awarded":               "Date Awarded",
    "registrar":                  "Registrar",
    "email":                      "Email",
    "phone":                      "Phone",
    "linkedin":                   "LinkedIn",
    "github":                     "GitHub",
    "skills":                     "Skills",
    "education":                  "Education",
    "experience":                 "Experience",
    "projects":                   "Projects",
    "internships":                "Internships",
    "cgpa":                       "CGPA",
    "percentage":                 "Percentage",
    "father_name":                "Father's Name",
    "mother_name":                "Mother's Name",
    "qr_present":                 "QR Code Present",
}

# ---------------------------------------------------------------------------
# Alias groups (semantically equivalent keys across doc types)
# ---------------------------------------------------------------------------

_NAME_ALIASES       = {"student_name", "candidate_name", "name"}
_UNIVERSITY_ALIASES = {"university", "institute", "institution", "board", "school_name"}
_DEGREE_ALIASES     = {"degree", "diploma_title", "course"}
_YEAR_ALIASES       = {"year_of_passing", "convocation_date", "date_awarded", "date_of_leaving", "session"}
_DOB_ALIASES        = {"dob", "date_of_birth"}
_CERT_ALIASES       = {"certificate_number"}
_REG_ALIASES        = {"register_number", "permanent_register_number", "roll_number"}

_ALIAS_GROUPS: list[set[str]] = [
    _NAME_ALIASES, _UNIVERSITY_ALIASES, _DEGREE_ALIASES,
    _YEAR_ALIASES, _DOB_ALIASES, _CERT_ALIASES, _REG_ALIASES,
]

# ---------------------------------------------------------------------------
# Document-pair-specific field sets
# Fields listed here are the PRIORITY fields compared for each pair.
# If a pair is not found, all fields are compared (generic fallback).
# Each value is a list of canonical field names to compare.
# ---------------------------------------------------------------------------

_DOC_LABELS: dict[str, str] = {
    "aadhaar_card":         "Aadhaar Card",
    "marksheet":            "SSLC / Marksheet",
    "sslc":                 "SSLC Marksheet",
    "sslc_marksheet":       "SSLC Marksheet",
    "hsc":                  "HSC Marksheet",
    "hsc_marksheet":        "HSC Marksheet",
    "transfer_certificate": "Transfer Certificate",
    "diploma":              "Diploma Certificate",
    "degree_certificate":   "Degree Certificate",
    "degree":               "Degree Certificate",
    "resume":               "Resume",
}

def _doc_label(doc_type: str) -> str:
    return _DOC_LABELS.get(doc_type, doc_type.replace("_", " ").title())


def _pair_key(t1: str, t2: str) -> tuple[str, str]:
    """Return a sorted canonical pair key."""
    return tuple(sorted([t1, t2]))  # type: ignore[return-value]


# Canonical field names that should be compared for each pair.
# Use alias resolution, so "student_name" covers "name"/"candidate_name" etc.
_PAIR_FIELDS: dict[tuple[str, str], list[str]] = {
    _pair_key("degree_certificate", "marksheet"):            ["student_name", "register_number", "university", "department", "year_of_passing"],
    _pair_key("degree_certificate", "sslc_marksheet"):       ["student_name", "register_number", "university", "department", "year_of_passing"],
    _pair_key("degree_certificate", "hsc_marksheet"):        ["student_name", "register_number", "university", "department", "year_of_passing"],
    _pair_key("degree_certificate", "resume"):               ["student_name", "university", "degree", "department", "year_of_passing"],
    _pair_key("resume", "aadhaar_card"):                     ["student_name", "dob"],
    _pair_key("marksheet", "aadhaar_card"):                  ["student_name", "dob", "register_number"],
    _pair_key("sslc_marksheet", "aadhaar_card"):             ["student_name", "dob", "register_number"],
    _pair_key("transfer_certificate", "marksheet"):          ["student_name", "register_number", "school_name", "year_of_passing"],
    _pair_key("transfer_certificate", "sslc_marksheet"):     ["student_name", "register_number", "school_name", "year_of_passing"],
    _pair_key("diploma", "resume"):                          ["student_name", "institute", "diploma_title", "year_of_passing"],
    _pair_key("diploma", "aadhaar_card"):                    ["student_name", "dob"],
    _pair_key("degree_certificate", "diploma"):              ["student_name", "university", "department", "year_of_passing"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_str(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("not found", "none", "") else None


def _resolve_alias(field: str) -> str:
    for group in _ALIAS_GROUPS:
        if field in group:
            return sorted(group)[0]
    return field


def _compare_fields(
    fields1: dict,
    fields2: dict,
    doc_type1: str = "",
    doc_type2: str = "",
) -> tuple[list[FieldComparisonRow], int, float, int]:
    """
    Compare fields between two documents.
    Returns (rows, match_count, weighted_score, total_comparable).

    Score: match=1, partial=0.5, mismatch=0, missing not counted.
    """
    rows: list[FieldComparisonRow] = []
    match_count = 0
    weighted_score = 0.0
    total = 0

    # Build canonical map
    all_fields: set[str] = set()
    canonical_map: dict[str, str] = {}
    for f in list(fields1.keys()) + list(fields2.keys()):
        canon = _resolve_alias(f)
        canonical_map[f] = canon
        all_fields.add(canon)

    # Filter to pair-specific fields if available
    pair_key = _pair_key(doc_type1, doc_type2)
    pair_priority = _PAIR_FIELDS.get(pair_key)
    if pair_priority:
        # Always include all common fields + pair-priority fields
        priority_canons = {_resolve_alias(f) for f in pair_priority}
        # Sort: priority fields first, then others
        ordered_fields = [f for f in sorted(all_fields) if f in priority_canons] + \
                         [f for f in sorted(all_fields) if f not in priority_canons]
    else:
        ordered_fields = sorted(all_fields)

    def _best_val(fields: dict, canon: str) -> Optional[str]:
        v = _to_str(fields.get(canon))
        if v:
            return v
        for orig, c in canonical_map.items():
            if c == canon and orig in fields:
                v = _to_str(fields[orig])
                if v:
                    return v
        return None

    for canon in ordered_fields:
        v1 = _best_val(fields1, canon)
        v2 = _best_val(fields2, canon)

        label = _FIELD_LABELS.get(canon, canon.replace("_", " ").title())

        if v1 is None and v2 is None:
            continue

        total += 1

        if v1 is None or v2 is None:
            row_status = "missing"
            sim_pct = None
        else:
            sim = _text_similar_score(v1, v2)
            sim_pct = round(sim * 100, 1)
            if sim >= _MATCH_THRESHOLD:
                row_status = "match"
                match_count += 1
                weighted_score += 1.0
            elif sim >= _PARTIAL_THRESHOLD:
                row_status = "partial"
                weighted_score += 0.5
            else:
                row_status = "mismatch"

        rows.append(FieldComparisonRow(
            field=canon,
            field_label=label,
            doc1_value=v1,
            doc2_value=v2,
            similarity=sim_pct,
            status=row_status,
        ))

    return rows, match_count, weighted_score, total


def _generate_ai_summary(
    rows: list[FieldComparisonRow],
    doc_type1: str,
    doc_type2: str,
    similarity_pct: float,
) -> list[str]:
    """
    Generate rule-based human-readable summary bullets.
    Deterministic — no external AI call needed.
    """
    bullets: list[str] = []
    d1 = _doc_label(doc_type1)
    d2 = _doc_label(doc_type2)

    matches    = [r for r in rows if r.status == "match"]
    partials   = [r for r in rows if r.status == "partial"]
    mismatches = [r for r in rows if r.status == "mismatch"]
    missing    = [r for r in rows if r.status == "missing"]

    # Overall verdict
    if similarity_pct >= 90:
        bullets.append(
            f"✅ Strong consistency detected between {d1} and {d2} "
            f"({similarity_pct:.0f}% overall similarity). Documents appear to belong to the same individual."
        )
    elif similarity_pct >= 70:
        bullets.append(
            f"⚠️ Moderate consistency between {d1} and {d2} "
            f"({similarity_pct:.0f}% similarity). Manual review recommended."
        )
    else:
        bullets.append(
            f"❌ Low consistency between {d1} and {d2} "
            f"({similarity_pct:.0f}% similarity). Significant discrepancies detected — possible fraud risk."
        )

    # Matched fields (group the important ones)
    if matches:
        key_matches = [r.field_label for r in matches if r.field in {
            "student_name", "candidate_name", "name",
            "register_number", "permanent_register_number",
            "university", "degree", "department",
        }]
        if key_matches:
            bullets.append(f"✅ Key fields match: {', '.join(key_matches)}.")
        elif len(matches) > 1:
            bullets.append(f"✅ {len(matches)} field{'s' if len(matches) > 1 else ''} matched successfully.")

    # Partial matches
    for r in partials[:3]:  # max 3 partials in summary
        bullets.append(
            f"⚠️ {r.field_label} is a partial match "
            f"({r.similarity:.0f}% similar) — minor OCR noise or abbreviation difference."
        )

    # Mismatches
    for r in mismatches[:3]:  # max 3 mismatches
        fraud_flag = " — potential fraud indicator" if r.field in {
            "student_name", "candidate_name", "register_number",
            "permanent_register_number", "aadhaar_number", "dob", "date_of_birth",
        } else ""
        bullets.append(
            f"❌ {r.field_label} mismatch: '{r.doc1_value}' vs '{r.doc2_value}'{fraud_flag}."
        )

    # Missing fields note
    if missing:
        missing_labels = [r.field_label for r in missing[:4]]
        bullets.append(
            f"— Fields not found in one or both documents: {', '.join(missing_labels)}. "
            "These could not be compared."
        )

    return bullets


def _run_ocr_and_extract(file_bytes: bytes, filename: str, doc_type: str):
    """Run preprocessing → OCR → text cleaning → template extraction. Returns (fields, accuracy)."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() or "jpg"
    raw = load_image_as_array(file_bytes, ext)
    color, binary = preprocess_for_ocr(raw)
    ocr_result = extract_text(color, binary_gray=binary)

    # ── Clean / Normalize OCR Text (shared pipeline step) ──────────────────
    raw_text_before = ocr_result.raw_text
    cleaned_text = clean_ocr_text(raw_text_before)
    logger.debug(
        "OCR text cleaned for comparison | file=%s | chars: %d → %d (-%d)",
        filename, len(raw_text_before), len(cleaned_text),
        len(raw_text_before) - len(cleaned_text),
    )

    bbox_results = extract_with_bboxes(color)
    template_result = extract_by_template(
        raw_text=cleaned_text,
        ocr_results=bbox_results,
        ocr_accuracy=ocr_result.accuracy,
        hint_doc_type=doc_type,
    )
    return template_result.fields, ocr_result.accuracy


# ---------------------------------------------------------------------------
# Main comparison endpoint (2–5 documents)
# ---------------------------------------------------------------------------

async def _extract_form_string(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if hasattr(val, "read"):
        try:
            content = await val.read()
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="ignore").strip()
            return str(content).strip()
        except Exception:
            return ""
    return str(val).strip()


async def _execute_direct_comparison(request: Request) -> DirectCompareResponse:
    form = await request.form()

    all_files: list[UploadFile] = []
    all_doc_types: list[str] = []

    # 1. Parse files from 'files' array OR 'file1'..'file5'
    raw_files = form.getlist("files")
    for f in raw_files:
        if hasattr(f, "filename") and getattr(f, "filename", None):
            all_files.append(f)

    if not all_files:
        for key in ["file1", "file2", "file3", "file4", "file5"]:
            f = form.get(key)
            if f is not None and hasattr(f, "filename") and getattr(f, "filename", None):
                all_files.append(f)

    # 2. Parse doc_types from 'doc_types' array OR 'doc_type1'..'doc_type5'
    raw_types = form.getlist("doc_types")
    for dt in raw_types:
        val = await _extract_form_string(dt)
        all_doc_types.append(val)

    if not any(all_doc_types):
        all_doc_types = []
        for key in ["doc_type1", "doc_type2", "doc_type3", "doc_type4", "doc_type5"]:
            dt = form.get(key)
            if dt is not None:
                val = await _extract_form_string(dt)
                if val:
                    all_doc_types.append(val)

    logger.info("direct_compare called | all_files=%d, all_doc_types=%s", len(all_files), all_doc_types)

    if len(all_files) < 2 or len(all_files) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "status": "failed",
                "stage": "file_validation",
                "message": f"Document comparison requires between 2 and 5 documents. Received {len(all_files)}.",
            },
        )

    file_bytes_list: list[bytes] = []
    filenames: list[str] = []
    final_doc_types: list[str] = []

    for i, file_obj in enumerate(all_files):
        doc_idx = i + 1
        fn = file_obj.filename or f"Document_{doc_idx}"
        filenames.append(fn)

        try:
            content = await file_obj.read()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "failed",
                    "stage": "file_validation",
                    "document_index": doc_idx,
                    "message": f"Document {doc_idx} ('{fn}') could not be read: {exc}",
                },
            )

        if not content or len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "failed",
                    "stage": "file_validation",
                    "document_index": doc_idx,
                    "message": f"Document {doc_idx} ('{fn}') is empty (0 bytes).",
                },
            )

        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "failed",
                    "stage": "file_validation",
                    "document_index": doc_idx,
                    "message": f"Document {doc_idx} ('{fn}') exceeds 15 MB limit.",
                },
            )

        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
        if ext and ext not in ("pdf", "jpg", "jpeg", "png"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "failed",
                    "stage": "file_validation",
                    "document_index": doc_idx,
                    "message": f"Document {doc_idx} ('{fn}') has unsupported format '{ext}'. Allowed: PDF, JPG, PNG.",
                },
            )

        try:
            load_image_as_array(content, ext or "jpg")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "failed",
                    "stage": "file_validation",
                    "document_index": doc_idx,
                    "message": f"Document {doc_idx} ('{fn}') is unreadable: {exc}",
                },
            )

        file_bytes_list.append(content)

        given_dt = all_doc_types[i] if i < len(all_doc_types) else ""
        if not given_dt or given_dt in ("auto", "unknown", ""):
            try:
                from app.services.document_classifier import classify
                res = classify(content, ext or "jpg")
                dt_val = res.predicted_type.value if hasattr(res.predicted_type, "value") else str(res.predicted_type)
            except Exception:
                dt_val = "marksheet"
            final_doc_types.append(dt_val)
        else:
            final_doc_types.append(given_dt)

    hashes = [hashlib.sha256(b).hexdigest() for b in file_bytes_list]
    is_identical = len(set(hashes)) == 1

    extracted_fields_list: list[dict] = []
    accuracy_list: list[float] = []

    for i in range(len(file_bytes_list)):
        doc_idx = i + 1
        fn = filenames[i]
        dt = final_doc_types[i]
        b = file_bytes_list[i]

        try:
            fields, acc = _run_ocr_and_extract(b, fn, dt)
            extracted_fields_list.append(fields)
            accuracy_list.append(acc)
        except Exception as exc:
            logger.exception("OCR failed for document %d (%s): %s", doc_idx, fn, exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "failed",
                    "stage": "ocr",
                    "document_index": doc_idx,
                    "message": f"OCR extraction failed for Document {doc_idx} ('{fn}'): {exc}",
                },
            )

    if is_identical:
        fields1 = extracted_fields_list[0]
        fields2 = extracted_fields_list[0]
        dt1 = final_doc_types[0]
        dt2 = final_doc_types[1] if len(final_doc_types) > 1 else dt1

        comparison, match_count, weighted_score, total = _compare_fields(fields1, fields2, dt1, dt2)

        for r in comparison:
            if r.doc1_value is not None or r.doc2_value is not None:
                r.status = "match"
                r.similarity = 100.0
                r.doc2_value = r.doc1_value

        matched_fields = [r.field for r in comparison if r.status == "match"]
        mismatched_fields = []
        missing_fields = [r.field for r in comparison if r.status == "missing"]

        ai_summary = [
            "✅ The uploaded documents are identical. No field differences detected.",
            "✅ Document SHA-256 hash match verified.",
        ]
        pair_hint = f"{_doc_label(dt1)} ↔ {_doc_label(dt2)} (Identical Documents)"

        return DirectCompareResponse(
            doc1_type=dt1,
            doc2_type=dt2,
            doc1_fields={k: _to_str(v) for k, v in fields1.items()},
            doc2_fields={k: _to_str(v) for k, v in fields1.items()},
            comparison=comparison,
            similarity_percentage=100.0,
            comparison_score=100.0,
            matched_fields=matched_fields,
            mismatched_fields=mismatched_fields,
            missing_fields=missing_fields,
            doc1_ocr_accuracy=accuracy_list[0],
            doc2_ocr_accuracy=accuracy_list[0],
            pair_hint=pair_hint,
            ai_summary=ai_summary,
            documents_compared=len(all_files),
            comparison_type="identical_document",
        )

    dt1 = final_doc_types[0]
    dt2 = final_doc_types[1]
    fields1 = extracted_fields_list[0]
    fields2 = extracted_fields_list[1]
    acc1 = accuracy_list[0]
    acc2 = accuracy_list[1]

    comparison, match_count, weighted_score, total = _compare_fields(fields1, fields2, dt1, dt2)
    similarity = round((weighted_score / total * 100), 1) if total > 0 else 0.0

    matched_fields = [r.field for r in comparison if r.status == "match"]
    mismatched_fields = [r.field for r in comparison if r.status == "mismatch"]
    missing_fields = [r.field for r in comparison if r.status == "missing"]

    ai_summary = _generate_ai_summary(comparison, dt1, dt2, similarity)

    if len(all_files) > 2:
        pair_hint = f"{len(all_files)} Documents Comparison ({_doc_label(dt1)} + {len(all_files)-1} others)"
        ai_summary.insert(0, f"ℹ️ Comparing {len(all_files)} documents simultaneously.")
    else:
        pair_hint = f"{_doc_label(dt1)} ↔ {_doc_label(dt2)}"

    return DirectCompareResponse(
        doc1_type=dt1,
        doc2_type=dt2,
        doc1_fields={k: _to_str(v) for k, v in fields1.items()},
        doc2_fields={k: _to_str(v) for k, v in fields2.items()},
        comparison=comparison,
        similarity_percentage=similarity,
        comparison_score=similarity,
        matched_fields=matched_fields,
        mismatched_fields=mismatched_fields,
        missing_fields=missing_fields,
        doc1_ocr_accuracy=acc1,
        doc2_ocr_accuracy=acc2,
        pair_hint=pair_hint,
        ai_summary=ai_summary,
        documents_compared=len(all_files),
        comparison_type="field_comparison",
    )


@router.post("/direct-compare", response_model=DirectCompareResponse)
async def direct_compare(
    request: Request,
    user: User = Depends(get_current_verified_user),
):
    """In-memory OCR + intelligent comparison for 2–5 documents. No DB writes."""
    return await _execute_direct_comparison(request)


@router.post("/direct-compare/pdf")
async def direct_compare_pdf(
    request: Request,
    user: User = Depends(get_current_verified_user),
):
    """Same as /direct-compare but streams a PDF comparison report for download."""
    result = await _execute_direct_comparison(request)
    pdf_bytes = _generate_comparison_pdf(result)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"CertiVerify_Comparison_{ts}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
