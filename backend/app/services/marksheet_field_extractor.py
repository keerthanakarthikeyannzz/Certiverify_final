"""
MARKSHEET FIELD EXTRACTOR  —  SSLC/HSC Priority Enhancement
============================================================

Extracts all structured fields from cleaned SSLC/HSC Marksheet OCR text.
Never returns hallucinated values. Returns null for any unextractable field.

Output contract:
{
    "document_type": "SSLC Marksheet" | "HSC Marksheet",
    "confidence": 0-100,
    "fields": {
        "student_name":      str | None,
        "register_number":   str | None,  # 8-15 digits
        "roll_number":       str | None,
        "certificate_number":str | None,
        "school":            str | None,
        "board":             str | None,
        "exam_name":         str | None,
        "group":             str | None,
        "medium":            str | None,
        "date_of_birth":     str | None,
        "year_of_passing":   str | None,
        "subjects":          list[{name, marks, grade}],
        "total_marks":       str | None,
        "percentage":        str | None,
        "result":            str | None,
        "signature_present": bool,
        "qr_present":        bool,
    },
    "field_confidences": { field: 0.0-1.0 }
}

Steps 6-9 of the spec are logged at INFO level.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("certiverify.marksheet_field_extractor")


# ---------------------------------------------------------------------------
# Known institution / board / heading patterns to SKIP for name extraction
# ---------------------------------------------------------------------------

_BOARD_HEADINGS = re.compile(
    r"(?:government|state\s+board|board\s+of|directorate|department"
    r"|authority|council|commission|examination|school\s+board"
    r"|secondary\s+school|higher\s+secondary|tamil\s+nadu|india"
    r"|mark\s+(?:sheet|certificate)|statement\s+of\s+marks"
    r"|sslc|hsc|result|declaration|profile|summary|technical|skills"
    r"|experience|education|project|achievement|extracurricular)",
    re.IGNORECASE,
)

_LABEL_LINES_MS = re.compile(
    r"^\s*(?:name|student|register|roll|certificate|school|board|medium"
    r"|group|subject|marks|total|percentage|result|date|year|session"
    r"|exam|gender|dob|father|mother|pass|fail|distinction|grade"
    r"|sl\.?\s*no|serial)\s*[:\-]?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Known Indian school boards
# ---------------------------------------------------------------------------

_KNOWN_BOARDS = [
    ("Tamil Nadu State Board", ["tamil nadu state board", "state board of school examinations",
                                "directorate of government examinations", "tn state board",
                                "tamil nadu", "dge"]),
    ("CBSE", ["central board of secondary education", "cbse"]),
    ("ICSE", ["indian certificate of secondary education", "icse", "cisce"]),
    ("Matriculation Board", ["matriculation", "matric board"]),
    ("NIOS", ["national institute of open schooling", "nios"]),
]

# Known exam names
_KNOWN_EXAMS = [
    ("SSLC", ["secondary school leaving certificate", "sslc", "10th", "x std", "tenth"]),
    ("HSC", ["higher secondary certificate", "higher secondary course", "hsc",
             "12th", "xii std", "second year", "+2", "twelfth"]),
]

# Known subject names
_KNOWN_SUBJECTS = [
    "Tamil", "English", "Mathematics", "Maths", "Physics", "Chemistry",
    "Biology", "Zoology", "Botany", "Computer Science", "Computer Applications",
    "Commerce", "Economics", "History", "Political Science", "Geography",
    "Business Mathematics", "Business Maths", "Accountancy", "Accounting",
    "Hindi", "French", "Sanskrit", "Drawing", "Music", "Physical Education",
    "Home Science", "Agriculture",
]

# Known group names
_KNOWN_GROUPS = [
    "Bio-Maths", "Bio Maths", "Computer Science", "Commerce", "Arts",
    "Vocational", "Physics Chemistry Maths", "PCM", "PCB",
]


# ---------------------------------------------------------------------------
# Marksheet document detection scoring
# ---------------------------------------------------------------------------

_MARKSHEET_KEYWORDS: list[tuple[str, int]] = [
    ("mark sheet",                5),
    ("marksheet",                 5),
    ("mark certificate",          5),
    ("statement of marks",        5),
    ("secondary school leaving",  5),
    ("higher secondary",          4),
    ("board of examinations",     4),
    ("sslc",                      4),
    ("hsc",                       4),
    ("state board",               3),
    ("register number",           3),
    ("roll number",               3),
    ("subject",                   3),
    ("total marks",               3),
    ("percentage",                3),
    ("grade",                     3),
    ("result",                    2),
    ("school",                    2),
    ("medium",                    2),
    ("candidate",                 2),
    ("pass",                      1),
    ("fail",                      1),
]

_MAX_MS_SCORE = sum(w for _, w in _MARKSHEET_KEYWORDS)


def _compute_marksheet_confidence(text: str, exam_type: str = "") -> int:
    """Return 0-100 marksheet document confidence based on keyword scoring."""
    text_l = text.lower()
    score = sum(w for kw, w in _MARKSHEET_KEYWORDS if kw in text_l)
    matched = [kw for kw, _ in _MARKSHEET_KEYWORDS if kw in text_l]
    logger.info("[Marksheet] Matched Keywords: %s", matched)
    pct = min(100, int((score / _MAX_MS_SCORE) * 100))
    doc_name = ("HSC" if exam_type == "hsc" else "SSLC") + " Marksheet"
    logger.info("[Marksheet] Detected Document Type: %s (%d%%)", doc_name, pct)
    return pct


# ---------------------------------------------------------------------------
# Individual field extractors
# ---------------------------------------------------------------------------

def _extract_student_name(text: str) -> tuple[Optional[str], float]:
    """
    Extract student name.
    Strategy:
    1. Scan after 'Name of Candidate' / 'Candidate Name' for uppercase English name tokens.
    2. Regex after 'name' label.
    3. Line-by-line scanning before register number.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Strategy 1: Look for candidate name label, then gather valid uppercase/title English name tokens
    for i, ln in enumerate(lines):
        if re.search(r"name\s*of\s*(?:the\s*)?candidate|candidate\s*name|student\s*name", ln, re.IGNORECASE):
            name_candidates: list[str] = []
            for j in range(i + 1, min(i + 12, len(lines))):
                cand = lines[j].strip().strip("~").strip()
                if re.search(r"date\s*of\s*birth|permanent|register|dob|certificate|sl\s*no|subject|roll|school", cand, re.IGNORECASE):
                    break
                is_caps = bool(re.match(r"^[A-Z][A-Z\s.]*$", cand))
                is_title = bool(re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]*)*$", cand))
                is_stop = bool(re.search(r"\b(?:AND|YEAR|ISSUE|OF|MARK|CERTIFICATE|DATE|BIRTH|SCHOOL|EXAM|ROLLNO|HIGHER|SECONDARY|STATE|BOARD)\b", cand, re.IGNORECASE))
                is_heading = bool(_BOARD_HEADINGS.search(cand))
                if (is_caps or is_title) and not is_stop and not is_heading:
                    name_candidates.append(cand)
                elif name_candidates:
                    # Once name tokens start, non-name tokens terminate sequence
                    break
            if name_candidates:
                full_name = " ".join(name_candidates).strip()
                full_name = re.sub(r"\s+", " ", full_name)
                logger.info("[Marksheet] Student Name extracted (labeled sequence): %s", full_name)
                return full_name, 0.95

    # Strategy 2: Labeled single-line regex
    m = re.search(
        r"(?:name\s+of\s+(?:the\s+)?(?:candidate|student)|candidate\s+name|student\s+name)"
        r"\s*[:\-]?\s*([A-Z][A-Za-z. ]{2,60})",
        text, re.IGNORECASE
    )
    if m:
        candidate = m.group(1).strip()
        if not _BOARD_HEADINGS.search(candidate) and not _LABEL_LINES_MS.match(candidate):
            logger.info("[Marksheet] Student Name extracted (regex): %s", candidate)
            return candidate, 0.90

    # Strategy 3: First valid Title Case line not matching headings
    for ln in lines:
        if (
            re.match(r"^[A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){1,5}$", ln)
            and not _BOARD_HEADINGS.search(ln)
            and not _LABEL_LINES_MS.match(ln)
            and not re.search(r"\d", ln)
        ):
            logger.info("[Marksheet] Student Name extracted (first valid line): %s", ln)
            return ln, 0.70

    logger.info("[Marksheet] Student Name: not found")
    return None, 0.0


def _extract_register_number(text: str) -> tuple[Optional[str], float]:
    """
    Extract permanent register number / register number (6-15 digits).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Labeled permanent register number
    m = re.search(
        r"(?:permanent\s*register\s*(?:no|number)|register(?:ation)?\s*(?:no|number)|reg\s*no|reg\.?\s*no\.?)"
        r"\s*[:\-]?\s*(\d{6,15})\b",
        text, re.IGNORECASE
    )
    if m:
        num = m.group(1)
        logger.info("[Marksheet] Register Number extracted (labeled): %s", num)
        return num, 0.98

    # Scan near 'PERMANENT REGISTER NUMBER' label
    for i, ln in enumerate(lines):
        if re.search(r"permanent\s*register|register\s*number", ln, re.IGNORECASE):
            for j in range(i + 1, min(i + 8, len(lines))):
                m_d = re.search(r"\b(\d{8,15})\b", lines[j])
                if m_d:
                    num = m_d.group(1)
                    logger.info("[Marksheet] Register Number extracted (near label): %s", num)
                    return num, 0.95

    # Pure-digit 8-15 block
    candidates = re.findall(r"\b(\d{8,15})\b", text)
    for c in candidates:
        if re.match(r"^[12]\d{3}$", c) or re.match(r"^[6-9]\d{9}$", c):
            continue
        logger.info("[Marksheet] Register Number extracted (unlabeled): %s", c)
        return c, 0.75

    logger.info("[Marksheet] Register Number: not found")
    return None, 0.0


def _extract_roll_number(text: str) -> tuple[Optional[str], float]:
    """Extract roll number (5-15 alphanumeric/digits)."""
    m = re.search(
        r"(?:roll\s*(?:no|number)|rollno)\s*[:\-]?\s*([A-Z0-9/\-]{5,20})\b",
        text, re.IGNORECASE
    )
    if m:
        logger.info("[Marksheet] Roll Number extracted: %s", m.group(1))
        return m.group(1).strip(), 0.95

    # 7-digit roll numbers typical in state board tables
    rolls = re.findall(r"\b(\d{7})\b", text)
    if rolls:
        logger.info("[Marksheet] Roll Number extracted (table roll): %s", rolls[0])
        return rolls[0], 0.90

    logger.info("[Marksheet] Roll Number: not found")
    return None, 0.0


def _extract_certificate_number(text: str) -> tuple[Optional[str], float]:
    """Extract certificate sl no / number."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Spaced digits at top of document (common in state board marksheets e.g. '3 3 2 3 3 5 0 8')
    for ln in lines[:10]:
        spaced_m = re.match(r"^\s*([0-9](?:\s+[0-9]){5,12})\s*$", ln)
        if spaced_m:
            cert_num = re.sub(r"\s+", "", spaced_m.group(1))
            logger.info("[Marksheet] Certificate Number extracted (spaced digits): %s", cert_num)
            return cert_num, 0.95

    m = re.search(
        r"(?:certificate\s*(?:sl|serial)?[._\s-]*(?:no|num|number|#)|cert\s*no)\s*[:\-]?\s*([A-Z0-9/\-]{4,25})\b",
        text, re.IGNORECASE
    )
    if m and not m.group(1).isalpha() and re.search(r"\d", m.group(1)):
        logger.info("[Marksheet] Certificate Number extracted: %s", m.group(1))
        return m.group(1).strip(), 0.95

    cert_label_pat = re.compile(r"certificate\s*(?:sl|serial)?[._\s-]*(?:no|num|number|#)", re.IGNORECASE)
    for i, ln in enumerate(lines):
        if cert_label_pat.search(ln):
            for j in range(i + 1, min(i + 4, len(lines))):
                digits = re.search(r"\b(\d{6,15})\b", lines[j])
                if digits:
                    logger.info("[Marksheet] Certificate Number extracted (digits): %s", digits.group(1))
                    return digits.group(1), 0.95
                elif re.match(r"^[A-Z0-9\/\-]{5,15}$", lines[j]) and not re.search(r"BOARD|SCHOOL|STATE", lines[j]):
                    logger.info("[Marksheet] Certificate Number extracted (token): %s", lines[j])
                    return lines[j], 0.90

    logger.info("[Marksheet] Certificate Number: not found")
    return None, 0.0


def _extract_school(text: str) -> tuple[Optional[str], float]:
    """Extract school name."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # After label
    m = re.search(
        r"(?:school\s*name|name\s*of\s*(?:the\s*)?school|institution)\s*[:\-]?\s*"
        r"([A-Z][A-Za-z\s&.,()-]{3,80})",
        text, re.IGNORECASE
    )
    if m:
        school = m.group(1).strip().rstrip(".,")
        if len(school) > 5:
            first_line = school.splitlines()[0].strip()
            cleaned = re.sub(r"\b([A-Za-z])\s+([A-Za-z])\s+([A-Za-z])\b", lambda mat: mat.group(0).replace(" ", "").upper(), first_line)
            logger.info("[Marksheet] School extracted (labeled): %s", cleaned)
            return cleaned, 0.95

    # Check next line after 'NAME OF THE SCHOOL'
    for i, ln in enumerate(lines):
        if re.search(r"name\s*of\s*(?:the\s*)?school", ln, re.IGNORECASE) and i + 1 < len(lines):
            cand = lines[i + 1].strip()
            if len(cand) > 5 and not _BOARD_HEADINGS.search(cand):
                first_line = cand.splitlines()[0].strip()
                cleaned = re.sub(r"\b([A-Za-z])\s+([A-Za-z])\s+([A-Za-z])\b", lambda mat: mat.group(0).replace(" ", "").upper(), first_line)
                logger.info("[Marksheet] School extracted (next line): %s", cleaned)
                return cleaned, 0.95

    # Find line with school keywords
    school_kw = re.compile(
        r"\b(?:school|hr\.?\s*sec|higher\s*secondary\s*school|vidyalaya"
        r"|matriculation|convent|college\s*of\s*education|public\s*school)\b",
        re.IGNORECASE
    )
    skip_kw = re.compile(
        r"(?:board|government\s+of|state\s+board|directorate|department\s+of"
        r"|mark\s+sheet|statement\s+of|higher\s+secondary\s+course)",
        re.IGNORECASE
    )
    for ln in lines:
        if school_kw.search(ln) and not skip_kw.search(ln):
            if 5 < len(ln) < 120:
                first_line = ln.splitlines()[0].strip()
                cleaned = re.sub(r"\b([A-Za-z])\s+([A-Za-z])\s+([A-Za-z])\b", lambda mat: mat.group(0).replace(" ", "").upper(), first_line)
                logger.info("[Marksheet] School extracted (keyword line): %s", cleaned)
                return cleaned, 0.85

    logger.info("[Marksheet] School: not found")
    return None, 0.0


def _extract_board(text: str) -> tuple[Optional[str], float]:
    """Extract exam board from known board list."""
    text_l = text.lower()
    for board_name, aliases in _KNOWN_BOARDS:
        for alias in aliases:
            if alias in text_l:
                logger.info("[Marksheet] Board extracted: %s", board_name)
                return board_name, 0.95
    logger.info("[Marksheet] Board: not found")
    return None, 0.0


def _extract_exam_name(text: str, exam_type: str = "") -> tuple[Optional[str], float]:
    """Extract exam name (SSLC / HSC / etc.)."""
    if exam_type == "sslc":
        return "SSLC", 1.0
    if exam_type == "hsc":
        return "HSC", 1.0

    text_l = text.lower()
    for exam_name, aliases in _KNOWN_EXAMS:
        for alias in aliases:
            if alias in text_l:
                logger.info("[Marksheet] Exam Name extracted: %s", exam_name)
                return exam_name, 0.95
    return "HSC" if "higher secondary" in text_l else ("SSLC" if "sslc" in text_l else None), 0.85


def _extract_group(text: str) -> tuple[Optional[str], float]:
    """Extract group."""
    text_l = text.lower()
    for known in _KNOWN_GROUPS:
        if known.lower() in text_l:
            logger.info("[Marksheet] Group extracted (known): %s", known)
            return known, 0.85

    m = re.search(
        r"group\s*(?:code\s*and\s*name|code|name)?\s*[:\-]?\s*([A-Za-z0-9\-/& ]{2,40})",
        text, re.IGNORECASE
    )
    if m:
        grp = m.group(1).strip().rstrip(".,")
        if len(grp) > 2 and grp.upper() not in {"CODE", "AND NAME"} and "medium" not in grp.lower():
            logger.info("[Marksheet] Group extracted (labeled): %s", grp)
            return grp, 0.92

    return None, 0.0


def _extract_medium(text: str) -> tuple[Optional[str], float]:
    """Extract medium of instruction."""
    m = re.search(
        r"medium\s*(?:of\s*instruction)?\s*[:\-/]?\s*([A-Za-z ]{3,30})",
        text, re.IGNORECASE
    )
    if m:
        med = m.group(1).strip().rstrip(".,")
        if len(med) >= 3 and med.upper() not in {"OF INSTRUCTION"}:
            logger.info("[Marksheet] Medium extracted: %s", med)
            return med.title(), 0.95

    if re.search(r"\btamil\s*medium\b", text, re.IGNORECASE):
        return "Tamil Medium", 0.90
    if re.search(r"\benglish\s*medium\b|\benglish\b", text, re.IGNORECASE):
        return "English Medium", 0.90

    return None, 0.0


def _extract_dob(text: str) -> tuple[Optional[str], float]:
    """Extract Date of Birth."""
    m = re.search(
        r"(?:date\s*of\s*birth|d\.?o\.?b)\s*[:\-]?\s*"
        r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        text, re.IGNORECASE
    )
    if m:
        dob = m.group(1).replace("-", "/").replace(".", "/")
        logger.info("[Marksheet] DOB extracted: %s", dob)
        return dob, 0.96

    m_any = re.search(r"\b([0-3]?\d[/\-.][0-1]?\d[/\-.][12]\d{3})\b", text)
    if m_any:
        dob = m_any.group(1).replace("-", "/").replace(".", "/")
        logger.info("[Marksheet] DOB extracted (date match): %s", dob)
        return dob, 0.90

    logger.info("[Marksheet] DOB: not found")
    return None, 0.0


def _extract_year_of_passing(text: str) -> tuple[Optional[str], float]:
    """Extract year of passing."""
    m = re.search(
        r"(?:year\s*of\s*passing|passed\s*in|month\s*[&and]\s*year|session|exam\s*year)"
        r"\s*[:\-]?\s*([A-Za-z]*\s*[12]\d{3})",
        text, re.IGNORECASE
    )
    if m:
        yr = m.group(1).strip()
        logger.info("[Marksheet] Year of Passing extracted (labeled): %s", yr)
        return yr, 0.92

    years = re.findall(r"(?<!\d)(?<![No\.#])\b(20[0-2]\d)\b", text)
    if years:
        yr = years[-1]
        logger.info("[Marksheet] Year of Passing extracted (last year): %s", yr)
        return yr, 0.75

    return None, 0.0


def _extract_subjects(text: str) -> tuple[list, float]:
    """
    Extract subjects and marks for Tamil Nadu / Indian state board marksheets.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    subjects = []
    seen = set()

    for subj in _KNOWN_SUBJECTS:
        subj_upper = subj.upper()
        for i, ln in enumerate(lines):
            if ln.upper() == subj_upper or re.match(rf"^{subj}$", ln, re.IGNORECASE):
                window = lines[max(0, i - 6): min(len(lines), i + 8)]
                window_str = "\n".join(window)

                # Look for 3-digit marks before 7-digit roll number in window
                m_before_roll = re.findall(r"\b0?(\d{2,3})\b\s*(?:\n|\s+)\s*\d{7}", window_str)
                found_mark = None
                if m_before_roll:
                    found_mark = int(m_before_roll[0])
                else:
                    m_totals = re.findall(r"\b0?(\d{2,3})\b", " ".join(window))
                    valid_marks = [int(m) for m in m_totals if 10 <= int(m) <= 100]
                    if valid_marks:
                        found_mark = valid_marks[-1]

                if found_mark is not None and subj.lower() not in seen:
                    subjects.append({"name": subj, "marks": str(found_mark), "grade": None})
                    seen.add(subj.lower())
                break

    if subjects:
        logger.info("[Marksheet] Subjects extracted: %d subjects: %s", len(subjects), [s["name"] for s in subjects])
        return subjects, 0.95

    return [], 0.0


def _extract_total_marks(text: str, subjects: list) -> tuple[Optional[str], float]:
    """Extract total marks."""
    m = re.search(
        r"(?:total\s*marks?|grand\s*total|aggregate)\s*[:\-]?\s*(\d{3,4})\b",
        text, re.IGNORECASE
    )
    if m:
        total = str(int(m.group(1)))
        logger.info("[Marksheet] Total Marks extracted (labeled): %s", total)
        return total, 0.98

    if subjects:
        try:
            total = sum(int(s["marks"]) for s in subjects if s.get("marks") and str(s["marks"]).isdigit())
            if total > 0:
                logger.info("[Marksheet] Total Marks calculated from subjects: %d", total)
                return str(total), 0.90
        except Exception:
            pass

    return None, 0.0


def _extract_percentage(text: str, total_marks: Optional[str], subjects: list) -> tuple[Optional[str], float]:
    """Extract percentage."""
    m = re.search(
        r"(?:percentage|percent|overall\s*%|%)\s*[:\-]?\s*(\d{1,3}(?:\.\d{1,2})?)\s*%?",
        text, re.IGNORECASE
    )
    if m:
        pct = m.group(1)
        logger.info("[Marksheet] Percentage extracted (labeled): %s%%", pct)
        return f"{pct}%", 0.95

    if total_marks:
        try:
            total = float(total_marks)
            max_marks = len(subjects) * 100 if len(subjects) >= 4 else 600
            if max_marks > 0 and total <= max_marks:
                pct = round((total / max_marks) * 100, 2)
                logger.info("[Marksheet] Percentage calculated: %.2f%%", pct)
                return f"{pct}%", 0.92
        except Exception:
            pass

    return None, 0.0


def _extract_result(text: str) -> tuple[Optional[str], float]:
    """Extract result: Pass / Fail."""
    m = re.search(
        r"\b(PASS|FAIL|FIRST\s*CLASS|DISTINCTION|PASSED)\b",
        text, re.IGNORECASE
    )
    if m:
        result = "PASS" if "PASS" in m.group(1).upper() else m.group(1).strip().upper()
        logger.info("[Marksheet] Result extracted: %s", result)
        return result, 0.98

    return "PASS" if "passed" in text.lower() else None, 0.85


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def extract_marksheet_fields(
    raw_text: str,
    exam_type: str = "",
    qr_present: bool = False,
    signature_present: bool = False,
) -> dict:
    """
    Extract all structured SSLC/HSC Marksheet fields from OCR text.

    Parameters
    ----------
    raw_text         : Cleaned merged OCR text from MarksheetOCRResult.raw_text
    exam_type        : "sslc" | "hsc" | "" (auto-detect)
    qr_present       : From MarksheetOCRResult.qr_present
    signature_present: From MarksheetOCRResult.signature_present

    Returns
    -------
    dict with keys: document_type, confidence, fields, field_confidences
    """
    logger.info("[Marksheet] === Field Extraction START | exam_type=%s ===", exam_type)

    # Auto-detect exam type from text if not provided
    if not exam_type:
        text_l = raw_text.lower()
        if any(kw in text_l for kw in ["higher secondary", "hsc", "12th", "+2", "second year"]):
            exam_type = "hsc"
        else:
            exam_type = "sslc"
        logger.info("[Marksheet] Auto-detected exam_type: %s", exam_type)

    # Document detection confidence
    doc_confidence = _compute_marksheet_confidence(raw_text, exam_type)

    # Extract all fields
    student_name, name_conf         = _extract_student_name(raw_text)
    register_number, reg_conf       = _extract_register_number(raw_text)
    roll_number, roll_conf          = _extract_roll_number(raw_text)
    cert_number, cert_conf          = _extract_certificate_number(raw_text)
    school, school_conf             = _extract_school(raw_text)
    board, board_conf               = _extract_board(raw_text)
    exam_name, exam_conf            = _extract_exam_name(raw_text, exam_type)
    group, group_conf               = _extract_group(raw_text)
    medium, medium_conf             = _extract_medium(raw_text)
    dob, dob_conf                   = _extract_dob(raw_text)
    year_of_passing, yop_conf       = _extract_year_of_passing(raw_text)
    subjects, subj_conf             = _extract_subjects(raw_text)
    total_marks, total_conf         = _extract_total_marks(raw_text, subjects)
    percentage, pct_conf            = _extract_percentage(raw_text, total_marks, subjects)
    result, result_conf             = _extract_result(raw_text)

    fields = {
        "student_name":       student_name,
        "register_number":    register_number,
        "roll_number":        roll_number,
        "certificate_number": cert_number,
        "school":             school,
        "board":              board,
        "exam_name":          exam_name,
        "group":              group,
        "medium":             medium,
        "date_of_birth":      dob,
        "year_of_passing":    year_of_passing,
        "subjects":           subjects,
        "total_marks":        total_marks,
        "percentage":         percentage,
        "result":             result,
        "signature_present":  signature_present,
        "qr_present":         qr_present,
    }

    field_confidences = {
        "student_name":       name_conf,
        "register_number":    reg_conf,
        "roll_number":        roll_conf,
        "certificate_number": cert_conf,
        "school":             school_conf,
        "board":              board_conf,
        "exam_name":          exam_conf,
        "group":              group_conf,
        "medium":             medium_conf,
        "date_of_birth":      dob_conf,
        "year_of_passing":    yop_conf,
        "subjects":           subj_conf,
        "total_marks":        total_conf,
        "percentage":         pct_conf,
        "result":             result_conf,
        "signature_present":  1.0,
        "qr_present":         1.0,
    }

    # Log extracted vs missing
    extracted = {k: v for k, v in fields.items()
                 if v is not None and v is not False and v != []}
    missing = [k for k, v in fields.items()
               if v is None or (isinstance(v, list) and len(v) == 0)]
    logger.info("[Marksheet] Extracted Fields: %s", list(extracted.keys()))
    logger.info("[Marksheet] Missing Fields: %s", missing)

    doc_type = ("HSC Marksheet" if exam_type == "hsc" else "SSLC Marksheet")

    result_dict = {
        "document_type":   doc_type,
        "confidence":      doc_confidence,
        "fields":          fields,
        "field_confidences": field_confidences,
    }

    logger.info("[Marksheet] === Field Extraction COMPLETE | confidence=%d%% ===", doc_confidence)
    return result_dict
