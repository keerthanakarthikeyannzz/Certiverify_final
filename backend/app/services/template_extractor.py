"""
Template-Based OCR Field Extractor
===================================
Enhancement to the existing OCR pipeline (Module 4).

Strategy
--------
1. Detect document template from raw OCR text via scored keyword matching.
2. Dispatch to a dedicated parser for that template.
3. Each parser uses three complementary strategies:
     a. _find_label_value_pairs : strict label-on-one-line, value-on-next-line
        (ideal for TN state board SSLC/HSC formats)
     b. _find_after (line-anchor): finds label keyword, extracts same-line or next
        non-label line value; uses stop-word trimming to prevent bleed-over
     c. Regex anchors            : targeted patterns for known field formats
     d. Spatial bbox extraction  : EasyOCR bounding-box coordinates for
                                   "find text directly below/right of label"
4. All defined fields are returned; "Not Found" is used for missing ones.
5. Debug log: detected template, matched keywords, extracted fields, missing fields.

This file does NOT modify any existing function. It is a net-new service called
from api/ocr.py AFTER the existing extractors have run.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("certiverify.template_extractor")

# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TemplateExtractionResult:
    template_name: str
    matched_keywords: list[str]
    fields: dict[str, str]          # every field -> value or "Not Found"
    missing_fields: list[str]
    ocr_confidence: float
    debug_log: dict[str, Any]


_BBoxResult = list[tuple[list, str, float]]   # [(bbox, text, conf), ...]


# ─────────────────────────────────────────────────────────────────────────────
# Template keyword signatures
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATE_KEYWORDS: dict[str, list[str]] = {
    "aadhaar": [
        "aadhaar", "uidai", "unique identification authority",
        "government of india", "enrolment no", "vid",
        "your aadhaar no", "resident",
    ],
    "sslc": [
        "secondary school leaving certificate", "sslc",
        "state board of school examinations",
        "permanent register number", "medium of instruction",
        "date of birth", "roll no", "school name",
        "board of secondary education",
        # Added in enhancement (spec Step 5 keywords)
        "mark sheet", "mark certificate", "statement of marks",
        "board of examinations", "register number", "roll number",
        "subject", "total marks", "percentage", "grade", "result",
        "school", "state board",
    ],
    "hsc": [
        "higher secondary course", "second year mark certificate",
        "total marks", "group code", "session", "hsc",
        "higher secondary certificate", "+2 mark",
        "board of higher secondary", "second year",
        # Added in enhancement (spec Step 5 keywords)
        "mark sheet", "mark certificate", "statement of marks",
        "higher secondary", "board of examinations", "register number",
        "roll number", "subject", "percentage", "grade", "result",
        "school", "state board",
    ],
    "transfer_certificate": [
        "transfer certificate", "tc no", "tc number",
        "date of leaving", "conduct", "admission number",
        "admission no", "this is to certify that",
        "has been a student",
    ],
    "diploma": [
        "diploma", "polytechnic",
        "directorate of technical education",
        "state board of technical education",
        "dote", "diploma in engineering",
    ],
    "degree": [
        "bachelor of", "master of", "doctor of",
        "convocation", "registrar", "degree certificate",
        "awarded the degree", "b.e.", "b.tech",
        "m.e.", "m.tech", "conferred",
    ],
    "resume": [
        "email", "phone", "linkedin", "github",
        "objective", "career objective", "professional objective",
        "profile", "profile summary", "professional summary",
        "skills", "technical skills", "core competencies",
        "projects", "academic projects", "personal projects",
        "experience", "work experience", "professional experience",
        "education", "academic background",
        "internship", "internships", "training",
        "certifications", "certificates",
        "achievements", "awards",
        "languages", "language proficiency",
        "resume", "curriculum vitae", "cv",
        "address", "contact",
    ],
}

_TEMPLATE_PRIORITY: dict[str, int] = {
    "aadhaar": 10, "sslc": 9, "hsc": 9,
    "transfer_certificate": 8, "diploma": 7, "degree": 7, "resume": 6,
}


# ─────────────────────────────────────────────────────────────────────────────
# Template detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_template(text: str) -> tuple[str, list[str]]:
    text_lower = text.lower()
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for template, keywords in _TEMPLATE_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text_lower]
        scores[template] = len(hits)
        matched[template] = hits
    ranked = sorted(
        scores.keys(),
        key=lambda t: (scores[t], _TEMPLATE_PRIORITY.get(t, 0)),
        reverse=True,
    )
    best = ranked[0]
    if scores[best] == 0:
        return "unknown", []
    logger.info("Template detected: '%s' (score=%d, kw=%s)", best, scores[best], matched[best])
    return best, matched[best]


# ─────────────────────────────────────────────────────────────────────────────
# Common text-line helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _nf(val: Optional[str]) -> str:
    if val is None or not str(val).strip():
        return "Not Found"
    return str(val).strip()


_MAX_FIELD_LEN = 120

_LABEL_STOP_WORDS = [
    "father", "mother", "roll", "register", "school", "medium",
    "date of birth", "dob", "certificate", "conduct", "tc no", "admission",
    "university", "department", "total", "session", "group",
    "email", "phone", "linkedin", "github", "skills", "education",
    "experience", "projects", "internship", "address", "vid", "aadhaar",
]


def _clean_value(val: Optional[str], label: str = "") -> Optional[str]:
    """
    Trim a field value, stopping before adjacent label keywords.
    `label` is the keyword that triggered this match — skip it from stop-word cuts.
    """
    if not val:
        return None
    val = val.strip()
    if not val:
        return None
    val_lower = val.lower()
    label_lower = label.lower()
    earliest_cut = len(val)
    for stop in _LABEL_STOP_WORDS:
        if label_lower and (stop in label_lower or label_lower in stop):
            continue
        idx = val_lower.find(stop, 3)
        if 0 < idx < earliest_cut:
            earliest_cut = idx
    val = val[:earliest_cut].strip().rstrip(":-. ")
    if len(val) > _MAX_FIELD_LEN:
        val = val[:_MAX_FIELD_LEN].rsplit(" ", 1)[0]
    return val if val else None


def _is_label_line(text: str) -> bool:
    t = text.strip()
    if t.endswith(":"):
        return True
    if len(t) > 4 and t == t.upper() and not any(c.isdigit() for c in t):
        return True
    return False


def _find_label_value_pairs(lines: list[str], label: str) -> Optional[str]:
    """
    Strict label-then-value layout:
      LABEL LINE (ALL CAPS, one line)
      Value line (very next non-empty line)

    Use for SSLC/HSC that put each label on its own line above the value.
    Unlike _find_after, this DOES NOT skip 'label-looking' value lines.
    """
    label_l = label.lower()
    for i, line in enumerate(lines):
        if label_l in line.lower():
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if candidate:
                    return _clean_value(candidate, label=label)
    return None


def _find_after(lines: list[str], labels: list[str], max_look: int = 3) -> Optional[str]:
    """
    Find the first occurrence of any label keyword in lines.
    Extract value from:
      1. Same line (after the label + separator)
      2. Or the next non-empty, non-label line (up to max_look lines ahead)
    """
    for i, line in enumerate(lines):
        ll = line.lower()
        for label in labels:
            if label.lower() not in ll:
                continue
            idx = ll.index(label.lower()) + len(label)
            remainder = line[idx:].strip().lstrip(":-.– \t")
            if remainder and not _is_label_line(remainder):
                cleaned = _clean_value(remainder, label=label)
                if cleaned:
                    return cleaned
            for j in range(i + 1, min(i + 1 + max_look, len(lines))):
                candidate = lines[j].strip()
                if candidate and not _is_label_line(candidate):
                    cleaned = _clean_value(candidate, label=label)
                    if cleaned:
                        return cleaned
    return None


def _regex(pattern: str, text: str, group: int = 1) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(group).strip() if m else None


def _first_name_line(lines: list[str], start: int = 0, window: int = 8) -> Optional[str]:
    for ln in lines[start: start + window]:
        ln = ln.strip()
        if re.match(r"^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,4}$", ln):
            return ln
    return None


# ─────────────────────────────────────────────────────────────────────────────
# BBox spatial extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bbox_cy(bbox: list) -> float:
    ys = [pt[1] for pt in bbox]
    return (min(ys) + max(ys)) / 2.0


def _bbox_cx(bbox: list) -> float:
    xs = [pt[0] for pt in bbox]
    return (min(xs) + max(xs)) / 2.0


def _find_below_bbox(
    ocr_results: _BBoxResult, anchor: str,
    y_gap_min: float = 4, y_gap_max: float = 80, x_tol: float = 350,
) -> Optional[str]:
    anchor_l = anchor.lower()
    for bbox, text, _ in ocr_results:
        if anchor_l not in text.lower():
            continue
        ay, ax = _bbox_cy(bbox), _bbox_cx(bbox)
        candidates: list[tuple[float, str]] = []
        for bbox2, text2, _ in ocr_results:
            by, bx = _bbox_cy(bbox2), _bbox_cx(bbox2)
            dy = by - ay
            if y_gap_min < dy < y_gap_max and abs(bx - ax) < x_tol:
                candidates.append((dy, text2.strip()))
        if candidates:
            candidates.sort()
            return candidates[0][1]
    return None


def _find_right_bbox(
    ocr_results: _BBoxResult, anchor: str,
    x_gap_max: float = 500, y_tol: float = 20,
) -> Optional[str]:
    anchor_l = anchor.lower()
    for bbox, text, _ in ocr_results:
        if anchor_l not in text.lower():
            continue
        ay = _bbox_cy(bbox)
        ax_right = max(pt[0] for pt in bbox)
        candidates: list[tuple[float, str]] = []
        for bbox2, text2, _ in ocr_results:
            by, bx = _bbox_cy(bbox2), _bbox_cx(bbox2)
            dx = bx - ax_right
            if 0 < dx < x_gap_max and abs(by - ay) < y_tol:
                candidates.append((dx, text2.strip()))
        if candidates:
            candidates.sort()
            return candidates[0][1]
    return None


def _bbox_val(
    ocr_results: _BBoxResult, anchors: list[str], strategy: str = "below"
) -> Optional[str]:
    fn = _find_below_bbox if strategy == "below" else _find_right_bbox
    for anchor in anchors:
        v = fn(ocr_results, anchor)
        if v:
            return v
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Template-specific parsers
# ─────────────────────────────────────────────────────────────────────────────

# ── Aadhaar ──

_AADHAAR_FIELDS = [
    "name", "aadhaar_number", "vid", "dob", "gender",
    "address", "district", "state", "pincode",
    "mobile", "enrolment_number", "qr_present", "photo_present",
]


def _parse_aadhaar(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    """
    Parse Aadhaar Card fields.

    Delegates to aadhaar_field_extractor.extract_aadhaar_fields() which
    implements the full Priority-1 Aadhaar extraction pipeline with:
    - Government heading exclusion for name
    - 12-digit Aadhaar number validation
    - 16-digit VID extraction
    - Full address block with district/state/pincode
    - Mobile and enrolment number
    - QR and photo presence flags

    The _nf() sentinel "Not Found" is applied to any missing field so
    the TemplateExtractionResult missing_fields list is populated correctly.
    """
    try:
        from app.services.aadhaar_field_extractor import extract_aadhaar_fields
        result = extract_aadhaar_fields(text, qr_present=False, photo_present=False)
        raw_fields = result.get("fields", {})
    except Exception as exc:
        logger.error("aadhaar_field_extractor failed in template_extractor: %s", exc)
        raw_fields = {}

    out: dict[str, str] = {}
    for field_key in _AADHAAR_FIELDS:
        val = raw_fields.get(field_key)
        if isinstance(val, bool):
            out[field_key] = "Yes" if val else "Not Found"
        else:
            out[field_key] = _nf(str(val) if val is not None else None)

    # Keep backward-compatible "pin_code" alias used by some downstream modules
    if "pincode" in out and out["pincode"] != "Not Found":
        out["pin_code"] = out["pincode"]
    else:
        out.setdefault("pin_code", "Not Found")

    return out

# ── SSLC Marksheet ──

_SSLC_FIELDS = [
    # All 17 spec fields
    "student_name", "register_number", "roll_number", "certificate_number",
    "school", "board", "exam_name", "group", "medium", "date_of_birth",
    "year_of_passing", "subjects", "total_marks", "percentage", "result",
    "signature_present", "qr_present",
]


def _parse_sslc(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    """
    Parse SSLC Marksheet fields.

    Delegates to marksheet_field_extractor.extract_marksheet_fields() which
    implements the full SSLC extraction pipeline with:
    - Student name with board heading exclusion
    - 8-15 digit register number validation
    - 3-strategy subject table parser (columnar / known-subject / block)
    - Total marks (label -> subject sum -> fallback)
    - Percentage (label -> calculated from total)
    - Result: PASS/FAIL/FIRST CLASS/DISTINCTION/ABSENT
    - QR and signature presence flags

    _nf() sentinel "Not Found" applied to missing scalar fields;
    subjects list is preserved as-is for downstream modules.
    """
    try:
        from app.services.marksheet_field_extractor import extract_marksheet_fields
        result = extract_marksheet_fields(text, exam_type="sslc")
        raw_fields = result.get("fields", {})
    except Exception as exc:
        logger.error("marksheet_field_extractor failed in _parse_sslc: %s", exc)
        raw_fields = {}

    out: dict[str, str] = {}
    for field_key in _SSLC_FIELDS:
        val = raw_fields.get(field_key)
        if isinstance(val, bool):
            out[field_key] = "Yes" if val else "Not Found"
        elif isinstance(val, list):
            # subjects list — keep as-is (downstream modules handle it)
            out[field_key] = val if val else "Not Found"
        else:
            out[field_key] = _nf(str(val) if val is not None else None)

    return out


# ── HSC Marksheet ──

_HSC_FIELDS = [
    # All 17 spec fields
    "student_name", "register_number", "roll_number", "certificate_number",
    "school", "board", "exam_name", "group", "medium", "date_of_birth",
    "year_of_passing", "subjects", "total_marks", "percentage", "result",
    "signature_present", "qr_present",
]


def _parse_hsc(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    """
    Parse HSC Marksheet fields.

    Delegates to marksheet_field_extractor.extract_marksheet_fields() which
    implements the full HSC extraction pipeline identical to SSLC but with
    exam_type="hsc" hint for exam-name detection.
    """
    try:
        from app.services.marksheet_field_extractor import extract_marksheet_fields
        result = extract_marksheet_fields(text, exam_type="hsc")
        raw_fields = result.get("fields", {})
    except Exception as exc:
        logger.error("marksheet_field_extractor failed in _parse_hsc: %s", exc)
        raw_fields = {}

    out: dict[str, str] = {}
    for field_key in _HSC_FIELDS:
        val = raw_fields.get(field_key)
        if isinstance(val, bool):
            out[field_key] = "Yes" if val else "Not Found"
        elif isinstance(val, list):
            out[field_key] = val if val else "Not Found"
        else:
            out[field_key] = _nf(str(val) if val is not None else None)

    return out


# ── Transfer Certificate ──

_TC_FIELDS = ["student_name", "admission_number", "tc_number", "conduct", "institution", "date_of_leaving"]


def _parse_transfer_certificate(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    ls = _lines(text)
    out: dict[str, str] = {}

    out["student_name"] = _nf(
        _find_after(ls, ["name of the student", "student name"])
        or _bbox_val(ocr_results, ["STUDENT NAME", "NAME"], "below")
    )
    # Also try: grab name before 'has been a student'
    if out["student_name"] == "Not Found":
        m_stu = re.search(
            r"(?:name\s*(?:of\s*(?:the\s*)?student|:)?\s*)([A-Z][A-Za-z .]{2,50})",
            text, re.IGNORECASE
        )
        if m_stu:
            out["student_name"] = _nf(m_stu.group(1).strip())
    adm = (
        _find_after(ls, ["admission number", "admission no", "adm no"])
        or _regex(r"admission\s*(?:no|number)[.:\s]+([A-Z0-9/\-]{3,20})", text)
    )
    out["admission_number"] = _nf(adm)

    tc = (
        _find_after(ls, ["tc no", "tc number", "transfer certificate no"])
        or _regex(r"(?:tc\s*(?:no|number))[.:\s]+([A-Z0-9/\-]{3,20})", text)
    )
    out["tc_number"] = _nf(tc)

    conduct = (
        _find_after(ls, ["conduct", "character"])
        or _regex(r"(?:conduct|character)[.:\s]+([A-Za-z]{3,30})", text)
    )
    out["conduct"] = _nf(conduct)

    m = re.search(r"([A-Z][A-Za-z& .]{3,80}(?:School|College|Institution|Academy|Vidyalaya|Hr\.\s*Sec))", text)
    out["institution"] = _nf(m.group(1).strip() if m else None)

    dol = (
        _find_after(ls, ["date of leaving", "date of transfer"])
        or _regex(r"date\s*of\s*(?:leaving|transfer)[.:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", text)
    )
    out["date_of_leaving"] = _nf(dol)
    return out


# ── Diploma Certificate ──

_DIPLOMA_FIELDS = ["student_name", "diploma_title", "institute", "board", "year_of_passing", "certificate_number"]


def _parse_diploma(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    ls = _lines(text)
    out: dict[str, str] = {}

    # For diploma: look for name on line after 'awarded to'
    name = None
    for i, ln in enumerate(ls):
        if "awarded to" in ln.lower():
            # Take next non-empty line
            for j in range(i + 1, min(i + 4, len(ls))):
                candidate = ls[j].strip()
                if candidate and not _is_label_line(candidate):
                    name = candidate
                    break
            break
    if not name:
        name = (
            _find_after(ls, ["student name", "candidate name", "name"])
            or _bbox_val(ocr_results, ["STUDENT NAME", "CANDIDATE NAME"], "below")
        )
    out["student_name"] = _nf(name)
    diploma = (
        _find_after(ls, ["diploma in", "diploma of"])
        or _regex(r"diploma\s*(?:in|of)\s+([A-Za-z& ]{3,60})", text)
    )
    out["diploma_title"] = _nf(diploma)

    inst = _find_after(ls, ["institute", "institution", "college"])
    if not inst:
        m = re.search(r"([A-Z][A-Za-z& .]{3,80}(?:Polytechnic|Institute|College))", text)
        inst = m.group(1).strip() if m else None
    out["institute"] = _nf(inst)

    board = (
        _find_after(ls, ["state board of technical", "board"])
        or _regex(r"((?:board|directorate)\s*of\s*technical\s*education[A-Za-z, ]{0,50})", text)
    )
    out["board"] = _nf(board)

    year = (
        _find_after(ls, ["year of passing", "passing year"])
        or _regex(r"(?:year\s*of\s*passing|passed\s*in)[.:\s]+([12]\d{3})", text)
    )
    out["year_of_passing"] = _nf(year)

    cert = (
        _find_after(ls, ["certificate number", "certificate no"])
        or _regex(r"cert(?:ificate)?\s*(?:no|number)[.:\s]+([A-Z0-9/\-]{4,25})", text)
    )
    out["certificate_number"] = _nf(cert)
    return out


# ── Degree Certificate ──

_DEGREE_FIELDS = ["student_name", "degree", "department", "university", "certificate_number", "convocation_date", "registrar"]


def _parse_degree(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    ls = _lines(text)
    out: dict[str, str] = {}

    name = (
        _find_after(ls, ["awarded to", "student name", "name of the candidate"])
        or _bbox_val(ocr_results, ["AWARDED TO", "STUDENT NAME"], "below")
    )
    if not name:
        for i, ln in enumerate(ls):
            if "certify that" in ln.lower():
                name = _first_name_line(ls, i + 1, window=4)
                break
    out["student_name"] = _nf(name)

    degree = (
        _find_after(ls, ["degree of", "degree in", "awarded the degree"])
        or _regex(r"((?:bachelor|master|doctor)\s+of\s+[A-Za-z ]{3,60})", text)
    )
    out["degree"] = _nf(degree)

    dept = (
        _find_after(ls, ["department of", "department"])
        or _regex(r"department\s*(?:of)?[.:\s]+([A-Za-z &,]{3,60})", text)
    )
    out["department"] = _nf(dept)

    univ = _find_after(ls, ["university", "deemed university"])
    if not univ:
        m = re.search(r"\b([A-Z][A-Za-z& .]{3,60}\s+University)\b", text)
        univ = m.group(1).strip() if m else None
    out["university"] = _nf(univ)

    cert = (
        _find_after(ls, ["certificate number", "certificate no"])
        or _regex(r"cert(?:ificate)?\s*(?:no|number)[.:\s]+([A-Z0-9/\-]{4,25})", text)
    )
    out["certificate_number"] = _nf(cert)

    conv = (
        _find_after(ls, ["convocation", "date of award", "awarded on"])
        or _regex(r"(?:convocation|date\s*of\s*award|awarded\s*on)[.:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|[A-Za-z]+ \d{4})", text)
    )
    out["convocation_date"] = _nf(conv)
    out["registrar"] = _nf(_find_after(ls, ["registrar", "controller of examinations"]))
    return out


# ── Resume ──

_RESUME_FIELDS = [
    # All 14 spec-required fields
    "name", "email", "phone", "linkedin", "github",
    "address", "objective", "education", "skills",
    "projects", "internships", "experience",
    "certifications", "achievements", "languages",
]


def _parse_resume(text: str, ocr_results: _BBoxResult) -> dict[str, str]:
    """
    Parse Resume / CV fields.

    Delegates to resume_field_extractor.extract_resume_fields() which
    implements the full spec pipeline:
    - Heading-boundary section parser (robust against missing blank lines)
    - Name: Title Case + ALL CAPS + initials support
    - Email: RFC regex + OCR artifact repair
    - 3-category skills (technical / soft / tools)
    - Structured education, projects, internships, experience lists
    - All 14 required output fields with per-field confidence scores
    """
    try:
        from app.services.resume_field_extractor import extract_resume_fields
        result = extract_resume_fields(text)
        raw_fields = result.get("fields", {})
    except Exception as exc:
        logger.error("resume_field_extractor failed in _parse_resume: %s", exc)
        raw_fields = {}

    out: dict = {}
    for field_key in _RESUME_FIELDS:
        val = raw_fields.get(field_key)
        if isinstance(val, (list, dict)):
            # Preserve structured data (education list, skills dict, projects list, etc.)
            out[field_key] = val if val else "Not Found"
        else:
            out[field_key] = _nf(str(val) if val is not None else None)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch table & public entry point
# ─────────────────────────────────────────────────────────────────────────────

_PARSERS: dict[str, Any] = {
    "aadhaar":              (_parse_aadhaar,              _AADHAAR_FIELDS),
    "sslc":                 (_parse_sslc,                 _SSLC_FIELDS),
    "hsc":                  (_parse_hsc,                  _HSC_FIELDS),
    "transfer_certificate": (_parse_transfer_certificate, _TC_FIELDS),
    "diploma":              (_parse_diploma,              _DIPLOMA_FIELDS),
    "degree":               (_parse_degree,               _DEGREE_FIELDS),
    "resume":               (_parse_resume,               _RESUME_FIELDS),
}

_DOC_TYPE_ALIAS: dict[str, str] = {
    "aadhaar_card":         "aadhaar",
    "marksheet":            "sslc",
    "sslc":                 "sslc",
    "hsc":                  "hsc",
    "transfer_certificate": "transfer_certificate",
    "diploma":              "diploma",
    "degree_certificate":   "degree",
    "degree":               "degree",
    "resume":               "resume",
}


def extract_by_template(
    raw_text: str,
    ocr_results: _BBoxResult,
    ocr_accuracy: float = 0.0,
    hint_doc_type: Optional[str] = None,
) -> TemplateExtractionResult:
    """
    Main entry point called from api/ocr.py.

    Parameters
    ----------
    raw_text      : Combined OCR text from EasyOCR + Tesseract.
    ocr_results   : Raw EasyOCR [(bbox, text, conf), ...] for spatial extraction.
    ocr_accuracy  : Overall OCR confidence (0-1).
    hint_doc_type : User-selected or auto-classified doc type; skips auto-detect when given.
    """
    if hint_doc_type:
        template_key = _DOC_TYPE_ALIAS.get(hint_doc_type, "")
        if template_key in _PARSERS:
            matched_kw = [f"(hint: {hint_doc_type})"]
        else:
            template_key, matched_kw = detect_template(raw_text)
    else:
        template_key, matched_kw = detect_template(raw_text)

    if template_key in _PARSERS:
        parser_fn, defined_fields = _PARSERS[template_key]
        extracted: dict[str, str] = parser_fn(raw_text, ocr_results)
    else:
        extracted = {}
        defined_fields = []

    missing = [f for f in defined_fields if extracted.get(f, "Not Found") == "Not Found"]

    debug = {
        "detected_template": template_key,
        "matched_keywords": matched_kw,
        "extracted_fields": extracted,
        "missing_fields": missing,
        "ocr_confidence": round(ocr_accuracy, 4),
    }

    logger.info(
        "=== Template Extractor Debug ===\n"
        "  Template  : %s\n"
        "  Keywords  : %s\n"
        "  Extracted : %s\n"
        "  Missing   : %s\n"
        "  OCR Conf  : %.4f",
        template_key, matched_kw,
        {k: v for k, v in extracted.items() if v != "Not Found"},
        missing, ocr_accuracy,
    )

    return TemplateExtractionResult(
        template_name=template_key,
        matched_keywords=matched_kw,
        fields=extracted,
        missing_fields=missing,
        ocr_confidence=ocr_accuracy,
        debug_log=debug,
    )
