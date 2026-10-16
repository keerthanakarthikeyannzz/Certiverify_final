"""
MODULE 4 - Structured field extraction.

No labeled NER dataset exists for certificate fields, so extraction is
regex/keyword-based against the combined OCR text — the same honest
approach as Module 3's heuristic fallback. Each field gets its own
confidence based on how it was matched (labeled prefix vs. best-guess),
so the frontend's editable table can show the user what to double-check.

Swap in a fine-tuned NER/LayoutLM model later by replacing `extract_fields`;
the return contract (dict of field -> (value, confidence)) doesn't need to change.
"""
import re
import numpy as np
import cv2

FieldResult = dict[str, tuple[str | float | None, float]]  # value, confidence (0-1)

_LABEL_PATTERNS: dict[str, list[str]] = {
    "register_number": [r"\b(?:reg(?:istration)?|register|enrol(?:lment)?)\.?\s*(?:no|num|number)\s*[:\-]?\s*([A-Z0-9\/\-]{4,25})"],
    "roll_number": [r"\broll\s*(?:no|num|number)\s*[:\-]?\s*([A-Z0-9\/\-]{2,20})"],
    "certificate_number": [r"\bcert(?:ificate)?\.?\s*(?:no|num|number|id|code)\s*[:\-]?\s*([A-Z0-9\/\-]{4,25})"],
    "department": [r"department\s*(?:of)?\s*[:\-]?\s*([A-Za-z &,]{3,60})"],
    "date_of_issue": [
        r"date\s*of\s*issue\s*[:\-]?\s*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4})",
        r"dated?\s*[:\-]?\s*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4})",
        r"issue\s*date\s*[:\-]?\s*([\d]{1,2}[\/\-\.][\d]{1,2}[\/\-\.][\d]{2,4}|[A-Za-z]+\s+\d{4})",
    ],
    "cgpa": [r"c\.?g\.?p\.?a\.?\s*[:\-]?\s*([\d]\.\d{1,2})"],
    "percentage": [r"percentage\s*[:\-]?\s*([\d]{1,3}(?:\.\d{1,2})?)\s*%?"],
    "student_name": [
        r"(?:this is to certify that|name\s*of\s*(?:the\s*)?(?:student|candidate)|student\s*name|candidate\s*name)\s*[:\-]?\s*([A-Z][A-Za-z\. ]{2,50})",
        r"^name\s*[:\-]\s*([A-Z][A-Za-z\. ]{2,50})$",
    ],
    "university_name": [
        r"([A-Z][A-Za-z& \.\(]{3,60}\s(?:University|Institute of Technology|College)[A-Za-z\.\)]*)",
    ],
    "course": [
        r"\b(?:b\.?e\.?|b\.?tech\.?|m\.?e\.?|m\.?tech\.?|b\.?sc\.?|m\.?sc\.?|bachelor\s+of|master\s+of|diploma\s+in)\s+(?:in\s+)?([A-Za-z ]{2,40})",
    ],
}

LABELED_CONFIDENCE = 0.85   # matched via an explicit "Label: value" pattern
GUESS_CONFIDENCE = 0.5      # matched via a looser contextual pattern


def extract_fields(raw_text: str) -> FieldResult:
    """Returns {field_name: (value_or_None, confidence)} for every tracked field."""
    result: FieldResult = {}
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    flat_text = "\n".join(lines)

    for field, patterns in _LABEL_PATTERNS.items():
        value, confidence = None, 0.0
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, flat_text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip().rstrip(".,")
                confidence = LABELED_CONFIDENCE if i == 0 else GUESS_CONFIDENCE
                break
        result[field] = (value, confidence)

    # Numeric coercion for cgpa / percentage
    if result["cgpa"][0] is not None:
        try:
            result["cgpa"] = (float(result["cgpa"][0]), result["cgpa"][1])
        except ValueError:
            result["cgpa"] = (None, 0.0)
    if result["percentage"][0] is not None:
        try:
            result["percentage"] = (float(result["percentage"][0]), result["percentage"][1])
        except ValueError:
            result["percentage"] = (None, 0.0)

    return result


def detect_qr_code(image: np.ndarray) -> tuple[str | None, int]:
    """
    Detect and decode a QR code from the image.

    Strategy (in priority order):
    1. pyzbar on original grayscale
    2. pyzbar on 2× upscaled grayscale (helps low-res/small QR codes)
    3. OpenCV QRCodeDetector / QRCodeDetectorMulti on original
    4. OpenCV on Otsu binarized image
    5. OpenCV on 2x upscaled image
    6. OpenCV on brightened image

    Returns
    -------
    (decoded_text, confidence)
        decoded_text : str | None  — raw QR payload, or None if not found
        confidence   : int         — 0-100 (95=pyzbar orig, 80=pyzbar upscale, 70=OpenCV, 0=not found)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ── Strategy 1: pyzbar on original ──────────────────────────────────────
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        decoded = pyzbar_decode(gray)
        if decoded:
            text = decoded[0].data.decode("utf-8", errors="ignore").strip()
            if text:
                return text, 95
        # ── Strategy 2: pyzbar on 2× upscaled (helps small/blurry QR) ───────
        h, w = gray.shape[:2]
        upscaled = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        decoded2 = pyzbar_decode(upscaled)
        if decoded2:
            text = decoded2[0].data.decode("utf-8", errors="ignore").strip()
            if text:
                return text, 80
    except ImportError:
        pass  # pyzbar not installed — fall through to OpenCV
    except Exception:
        pass

    # ── Strategy 3: OpenCV QRCodeDetector / QRCodeDetectorMulti ─────────────
    try:
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(gray)
        if data and data.strip():
            return data.strip(), 70

        # Try MultiDetector (helps off-center / multi-code layouts)
        det_multi = cv2.QRCodeDetectorMulti()
        retval, decoded_info, _, _ = det_multi.detectAndDecodeMulti(gray)
        if retval and decoded_info:
            for d in decoded_info:
                if d and d.strip():
                    return d.strip(), 72

        # Retry on Otsu binarized image (helps crisp document scans)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        data_thresh, _, _ = detector.detectAndDecode(thresh)
        if data_thresh and data_thresh.strip():
            return data_thresh.strip(), 75

        # Retry on 2x upscaled image
        h, w = gray.shape[:2]
        upscaled = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        data_up, _, _ = detector.detectAndDecode(upscaled)
        if data_up and data_up.strip():
            return data_up.strip(), 70

        # Retry on brightened image (helps dark/low-contrast QR)
        brightened = cv2.convertScaleAbs(gray, alpha=1.2, beta=30)
        data2, _, _ = detector.detectAndDecode(brightened)
        if data2 and data2.strip():
            return data2.strip(), 65
    except Exception:
        pass

    return None, 0


def detect_signature(image: np.ndarray) -> bool:
    """
    Heuristic: signatures are irregular, low-density ink strokes typically in
    the bottom third of the document. We look for contours there with high
    aspect-ratio irregularity (unlike printed text lines, which are uniform).
    This is a heuristic, not a trained detector — flag for human review in
    borderline Trust Score cases (Module 8) rather than trusting blindly.
    """
    h, w = image.shape[:2]
    bottom_region = image[int(h * 0.7):, :]
    gray = cv2.cvtColor(bottom_region, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    irregular_count = 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 10 or ch < 5:
            continue
        aspect = cw / ch
        if 1.5 <= aspect <= 8 and cv2.contourArea(c) > 150:
            irregular_count += 1

    return irregular_count >= 2


def detect_seal(image: np.ndarray) -> bool:
    """Circular seal detection via Hough circles — optimized with image scaling to run in <50ms."""
    h, w = image.shape[:2]
    scale = 1.0
    if max(h, w) > 800:
        scale = 800.0 / max(h, w)
        resized = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        resized = image
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.medianBlur(gray, 5)
    rh, rw = gray.shape[:2]
    min_r = max(10, int(25 * scale))
    max_r = max(min_r + 5, min(rh, rw) // 3)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(20, int(100 * scale)),
        param1=100, param2=40, minRadius=min_r, maxRadius=max_r,
    )
    return circles is not None and len(circles[0]) > 0



# ===========================================================================
# DOCUMENT-TYPE-AWARE FIELD EXTRACTION  (Enhancement)
# ===========================================================================
# Extracts only the fields relevant to the detected document type.
# Existing extract_fields() is preserved and still called for generic fields.
# This function is called AFTER classify_from_text() identifies the doc type.
# ===========================================================================

def extract_fields_by_type(raw_text: str, doc_type: str) -> dict:
    """
    Dispatch to the correct type-specific field extractor.

    Args:
        raw_text:  Raw OCR text.
        doc_type:  DocTypeEnum value string, e.g. "aadhaar_card", "marksheet".

    Returns:
        dict of {field_name: extracted_value_or_None}
    """
    import logging as _log
    _logger = _log.getLogger("certiverify.ocr_field_extractor")
    _logger.info("extract_fields_by_type called for doc_type='%s'", doc_type)

    dispatch: dict[str, callable] = {
        "aadhaar_card":         _extract_aadhaar_fields,
        "marksheet":            _extract_marksheet_fields,
        "transfer_certificate": _extract_tc_fields,
        "diploma":              _extract_diploma_fields,
        "degree_certificate":   _extract_degree_fields,
        "resume":               _extract_resume_fields,
    }
    extractor = dispatch.get(doc_type)
    if extractor is None:
        _logger.info("No type-specific extractor for '%s', returning empty dict.", doc_type)
        return {}

    fields = extractor(raw_text)
    _logger.info("extract_fields_by_type result for '%s': %s", doc_type, fields)
    return fields


# ---------------------------------------------------------------------------
# Aadhaar Card
# ---------------------------------------------------------------------------

def _extract_aadhaar_fields(text: str) -> dict:
    """
    Extract structured Aadhaar Card fields.

    Delegates to aadhaar_field_extractor.extract_aadhaar_fields() which
    implements the full Priority-1 Aadhaar extraction pipeline:
    - Name (with government heading exclusion)
    - Aadhaar Number (12-digit, validated)
    - VID (16-digit)
    - DOB (full date or year-only)
    - Gender
    - Address (multi-line, complete)
    - District, State, Pincode
    - Mobile
    - Enrolment Number
    - QR and Photo presence flags

    qr_present and photo_present default to False here because this function
    is called without the image; the API layer (ocr.py) passes the real values
    when running via run_aadhaar_ocr().
    """
    try:
        from app.services.aadhaar_field_extractor import extract_aadhaar_fields
        result = extract_aadhaar_fields(text, qr_present=False, photo_present=False)
        return result.get("fields", {})
    except Exception as exc:
        import logging as _log
        _log.getLogger("certiverify.ocr_field_extractor").error(
            "aadhaar_field_extractor failed, using fallback: %s", exc
        )
        # Minimal fallback — never returns hallucinated values
        fields: dict = {}
        m = re.search(r"\b([2-9]\d{3}[\s\-]\d{4}[\s\-]\d{4})\b", text)
        fields["aadhaar_number"] = re.sub(r"[\s\-]", "", m.group(1)) if m else None
        m = re.search(
            r"(?:dob|date\s*of\s*birth|year\s*of\s*birth)[:\s]+([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4}|[0-9]{4})",
            text, re.IGNORECASE
        )
        fields["dob"] = m.group(1).strip() if m else None
        m = re.search(r"\b(male|female|transgender)\b", text, re.IGNORECASE)
        fields["gender"] = m.group(1).capitalize() if m else None
        fields["name"] = None
        fields["address"] = None
        return fields



# ---------------------------------------------------------------------------
# Marksheet
# ---------------------------------------------------------------------------

def _extract_marksheet_fields(text: str) -> dict:
    """
    Extract all SSLC/HSC Marksheet fields.

    Delegates to marksheet_field_extractor.extract_marksheet_fields() which
    implements the full Priority SSLC/HSC extraction pipeline with:
    - Student name with board heading exclusion
    - 8-15 digit register number validation
    - 3-strategy subject table parser
    - Total marks (label -> subject sum -> fallback)
    - Percentage (label -> calculated)
    - Result: PASS/FAIL/FIRST CLASS/DISTINCTION
    - QR and signature presence flags
    """
    try:
        from app.services.marksheet_field_extractor import extract_marksheet_fields
        result = extract_marksheet_fields(text, exam_type="")
        return result.get("fields", {})
    except Exception as exc:
        import logging as _log
        _log.getLogger("certiverify.ocr_field_extractor").error(
            "_extract_marksheet_fields delegation failed: %s", exc
        )
        return {}


# ---------------------------------------------------------------------------
# Transfer Certificate
# ---------------------------------------------------------------------------

def _extract_tc_fields(text: str) -> dict:
    """Extract Student Name, Admission No, TC No, Date of Leaving, Conduct, Institution."""
    fields: dict = {}

    # Student Name
    m = re.search(
        r"(?:student\s*name|name\s*of\s*(?:the\s*)?student|this\s*is\s*to\s*certify\s*that)[:\s]+([A-Z][A-Za-z .]{2,50})",
        text, re.IGNORECASE
    )
    fields["student_name"] = m.group(1).strip().rstrip(".,") if m else None

    # Admission Number
    m = re.search(r"admission\s*(?:no|number)[:\s.]+([A-Z0-9/\-]{3,20})", text, re.IGNORECASE)
    fields["admission_number"] = m.group(1).strip() if m else None

    # TC Number
    m = re.search(r"tc\s*(?:no|number)[:\s.]+([A-Z0-9/\-]{3,20})", text, re.IGNORECASE)
    fields["tc_number"] = m.group(1).strip() if m else None

    # Date of Leaving
    m = re.search(
        r"date\s*of\s*leaving[:\s]+([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4})",
        text, re.IGNORECASE
    )
    fields["date_of_leaving"] = m.group(1).strip() if m else None

    # Conduct / Character
    m = re.search(r"(?:conduct|character)[:\s]+([A-Za-z]{3,30})", text, re.IGNORECASE)
    fields["conduct"] = m.group(1).strip() if m else None

    # Institution / School Name
    m = re.search(
        r"([A-Z][A-Za-z& .]{3,80}(?:School|College|Institution|Academy|Vidyalaya))",
        text
    )
    fields["institution"] = m.group(1).strip() if m else None

    return fields


# ---------------------------------------------------------------------------
# Diploma Certificate
# ---------------------------------------------------------------------------

def _extract_diploma_fields(text: str) -> dict:
    """Extract Student Name, Diploma Title, Institute, Board, Year of Passing."""
    fields: dict = {}

    # Student Name
    m = re.search(
        r"(?:this\s*is\s*to\s*certify\s*that|awarded\s*to|student\s*name|name)[:\s]+([A-Z][A-Za-z .]{2,50})",
        text, re.IGNORECASE
    )
    fields["student_name"] = m.group(1).strip().rstrip(".,") if m else None

    # Diploma Title
    m = re.search(r"diploma\s*(?:in|of)\s+([A-Za-z ]{3,60})", text, re.IGNORECASE)
    fields["diploma_title"] = m.group(1).strip().rstrip(".,") if m else None

    # Institute
    m = re.search(
        r"([A-Z][A-Za-z& .]{3,80}(?:Polytechnic|Institute|College|Institution))",
        text
    )
    fields["institute"] = m.group(1).strip() if m else None

    # Board
    m = re.search(
        r"((?:board|directorate)\s*of\s*technical\s*education[A-Za-z ,]{0,60})",
        text, re.IGNORECASE
    )
    fields["board"] = m.group(1).strip() if m else None

    # Year of Passing
    m = re.search(
        r"(?:year\s*of\s*passing|passed\s*in|passing\s*year)[:\s]+([12][0-9]{3})",
        text, re.IGNORECASE
    )
    fields["year_of_passing"] = m.group(1).strip() if m else None

    return fields


# ---------------------------------------------------------------------------
# Degree Certificate
# ---------------------------------------------------------------------------

def _extract_degree_fields(text: str) -> dict:
    """Extract Student Name, Degree, University, Department, Date Awarded."""
    fields: dict = {}

    # Student Name — typically follows "awarded to" or "this is to certify that" or top line
    m = re.search(
        r"(?:awarded\s*(?:the\s*degree)?\s*to|this\s*is\s*to\s*certify\s*that|name\s*of\s*(?:the\s*)?candidate|student\s*name)[:\s]+([A-Z][A-Za-z .]{2,60})",
        text, re.IGNORECASE
    )
    if m:
        fields["student_name"] = m.group(1).strip().rstrip(".,")
    else:
        # Fallback: check top 5 lines for standalone uppercase candidate name
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        exclude = {"PROFILE", "SUMMARY", "CURRICULUM", "VITAE", "RESUME", "BIODATA", "CONTACT", "TECHNICAL", "SKILLS", "EDUCATION", "CERTIFICATE"}
        candidate_name = None
        for ln in lines[:5]:
            clean_ln = re.sub(r"[\$\#\*\_\=\+\~]+$", "", ln).strip()
            words = clean_ln.split()
            if words and all(w.isupper() or w.istitle() for w in words):
                if not any(w.upper() in exclude for w in words) and len(clean_ln) >= 3:
                    candidate_name = clean_ln
                    break
        fields["student_name"] = candidate_name

    # Degree Title
    m = re.search(
        r"\b((?:b\.?e\.?|b\.?tech\.?|m\.?e\.?|m\.?tech\.?|b\.?sc\.?|m\.?sc\.?|bachelor\s+of|master\s+of|doctor\s+of)\s+(?:in\s+)?[A-Za-z ]{2,60})",
        text, re.IGNORECASE
    )
    fields["degree"] = m.group(1).strip().rstrip(".,") if m else None

    # University
    m = re.search(
        r"([A-Z][A-Za-z& .]{3,60}\s+(?:University|Institute\s+of\s+Technology))",
        text
    )
    fields["university"] = m.group(1).strip() if m else None

    # Department
    m = re.search(
        r"department\s*(?:of)?[:\s]+([A-Za-z &,]{3,60})",
        text, re.IGNORECASE
    )
    dept_val = m.group(1).strip().rstrip(".,") if m else None
    if dept_val and "association" in dept_val.lower():
        dept_val = None
    fields["department"] = dept_val

    # Date Awarded / Convocation Date
    m = re.search(
        r"(?:date\s*of\s*award|awarded\s*on|convocation|date\s*of\s*issue|dated)[:\s]+([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[A-Za-z]+\s+[0-9]{4}|[0-9]{4})",
        text, re.IGNORECASE
    )
    fields["date_awarded"] = m.group(1).strip() if m else None

    return fields


# ---------------------------------------------------------------------------
# Resume / CV
# ---------------------------------------------------------------------------

def _extract_resume_fields(text: str) -> dict:
    """
    Extract all Resume / CV structured fields.

    Delegates to resume_field_extractor.extract_resume_fields() which
    implements the full 8-step spec pipeline:
    - Step 1-3: OCR preprocessing + artifact repair (done by resume_ocr_engine)
    - Step 4: Heading-boundary section detection (robust keyword-boundary approach)
    - Step 5: All 14 structured output fields with proper data types
    - Step 6: Per-field confidence scores
    - Step 7: All extraction events logged at INFO level
    - Step 8: Unextractable fields return None / [] — never guessed
    """
    try:
        from app.services.resume_field_extractor import extract_resume_fields
        result = extract_resume_fields(text)
        return result.get("fields", {})
    except Exception as exc:
        import logging as _log
        _log.getLogger("certiverify.ocr_field_extractor").error(
            "_extract_resume_fields delegation failed: %s", exc
        )
        return {}


# ===========================================================================
# LAYOUT-AWARE FIELD EXTRACTION  (Enhancement — uses bounding boxes)
# ===========================================================================

def _find_value_near_label(
    label_text: str,
    structured_bboxes: list[dict],
    search_direction: str = "right_or_below",
    max_y_distance: float = 60.0,
    max_x_distance: float = 500.0,
) -> tuple[str | None, float]:
    """
    Find a field value near a label using bounding box coordinates.

    Strategy:
    1. Find all bbox entries matching the label text (case-insensitive)
    2. For each match, search nearby entries (right or below) for the value
    3. Return the closest value with its confidence

    Parameters
    ----------
    label_text       : text to search for (e.g. "Student Name")
    structured_bboxes: list of dicts with {text, confidence, x, y, width, height, page}
    search_direction : "right_or_below" or "right" or "below"
    max_y_distance   : max vertical distance to search
    max_x_distance   : max horizontal distance to search

    Returns
    -------
    (value_text, confidence) or (None, 0.0) if not found
    """
    if not structured_bboxes:
        return None, 0.0

    label_lower = label_text.lower()

    # Find label bboxes
    label_matches = []
    for i, bbox in enumerate(structured_bboxes):
        if label_lower in bbox["text"].lower():
            label_matches.append((i, bbox))

    if not label_matches:
        return None, 0.0

    best_value = None
    best_conf = 0.0
    best_distance = float("inf")

    for label_idx, label_bbox in label_matches:
        label_right = label_bbox["x"] + label_bbox["width"]
        label_bottom = label_bbox["y"] + label_bbox["height"]
        label_page = label_bbox["page"]

        for j, candidate in enumerate(structured_bboxes):
            if j == label_idx:
                continue
            if candidate["page"] != label_page:
                continue

            cand_text = candidate["text"].strip()
            if not cand_text or len(cand_text) < 2:
                continue

            # Skip if candidate IS a label/header
            if cand_text.lower().endswith(":") and len(cand_text) < 20:
                continue

            dx = candidate["x"] - label_right
            dy = candidate["y"] - label_bbox["y"]

            is_right = (0 <= dx <= max_x_distance and abs(dy) <= max_y_distance * 0.5)
            is_below = (abs(candidate["x"] - label_bbox["x"]) <= max_x_distance * 0.5
                        and 0 <= dy <= max_y_distance)

            if search_direction == "right" and not is_right:
                continue
            if search_direction == "below" and not is_below:
                continue
            if search_direction == "right_or_below" and not (is_right or is_below):
                continue

            distance = (dx ** 2 + dy ** 2) ** 0.5
            if distance < best_distance:
                best_distance = distance
                best_value = cand_text
                best_conf = candidate["confidence"]

    return best_value, best_conf


def extract_fields_with_bboxes(
    raw_text: str,
    structured_bboxes: list[dict],
    doc_type: str,
) -> dict:
    """
    Layout-aware field extraction using bounding box coordinates.

    Combines spatial extraction with text-based regex extraction.
    For each field, tries bbox-based extraction first, falls back to regex.

    Returns dict of {field_name: {"value": str|None, "confidence": float, "source": str}}
    """
    import logging as _log
    _logger = _log.getLogger("certiverify.ocr_field_extractor")
    _logger.info("extract_fields_with_bboxes: doc_type=%s bboxes=%d", doc_type, len(structured_bboxes))

    results = {}

    # Define label-to-field mappings per document type
    label_mappings = {
        "aadhaar_card": {
            "name": ["name", "to"],
            "aadhaar_number": ["aadhaar", "aadhaar no"],
            "dob": ["dob", "date of birth", "year of birth"],
            "gender": ["gender", "male", "female"],
            "address": ["address", "s/o", "d/o", "w/o", "c/o"],
        },
        "marksheet": {
            "student_name": ["name of candidate", "student name", "candidate name", "name"],
            "register_number": ["register no", "register number", "reg no", "permanent register number"],
            "roll_number": ["roll no", "roll number"],
            "school": ["school name", "name of school", "school"],
            "board": ["board", "state board"],
        },
        "resume": {
            "name": ["name"],
            "email": ["email", "e-mail", "mail"],
            "phone": ["phone", "mobile", "contact", "mob"],
        },
    }

    mappings = label_mappings.get(doc_type, {})
    for field_name, labels in mappings.items():
        for label in labels:
            value, conf = _find_value_near_label(label, structured_bboxes)
            if value:
                results[field_name] = {
                    "value": value,
                    "confidence": conf,
                    "source": f"bbox_near_{label}",
                }
                break

    _logger.info("extract_fields_with_bboxes: extracted %d fields via bbox: %s",
                 len(results), list(results.keys()))
    return results


# ===========================================================================
# FIELD VALIDATION RULES  (Enhancement)
# ===========================================================================

_VALIDATION_RULES = {
    "aadhaar_number": {
        "pattern": re.compile(r"^\d{12}$"),
        "description": "Must be exactly 12 digits",
    },
    "email": {
        "pattern": re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"),
        "description": "Must match email format",
    },
    "phone": {
        "pattern": re.compile(r"^[6-9]\d{9}$"),
        "description": "Must be 10 digits starting with 6-9",
    },
    "mobile": {
        "pattern": re.compile(r"^[6-9]\d{9}$"),
        "description": "Must be 10 digits starting with 6-9",
    },
    "pincode": {
        "pattern": re.compile(r"^[1-9]\d{5}$"),
        "description": "Must be 6 digits starting with 1-9",
    },
    "percentage": {
        "pattern": re.compile(r"^\d{1,3}(\.\d{1,2})?%?$"),
        "description": "Must be numeric 0-100",
        "range": (0, 100),
    },
    "cgpa": {
        "pattern": re.compile(r"^\d\.\d{1,2}$"),
        "description": "Must be numeric (e.g. 8.5)",
        "range": (0, 10),
    },
    "register_number": {
        "max_length": 25,
        "min_length": 4,
        "no_sentence": True,
        "description": "Must be 4-25 chars, not a sentence",
    },
    "certificate_number": {
        "max_length": 25,
        "min_length": 4,
        "no_sentence": True,
        "description": "Must be 4-25 chars, not a sentence",
    },
}


def validate_field(field_name: str, value) -> tuple[bool, str]:
    """
    Validate an extracted field value against its rules.

    Returns (is_valid, reason).
    If no rule exists for the field, returns (True, "no validation rule").
    """
    if value is None:
        return True, "null value (acceptable)"

    rule = _VALIDATION_RULES.get(field_name)
    if not rule:
        return True, "no validation rule"

    str_value = str(value).strip()

    # Pattern check
    if "pattern" in rule:
        if not rule["pattern"].match(str_value):
            return False, f"Failed pattern: {rule['description']}"

    # Range check
    if "range" in rule:
        try:
            num = float(str_value.rstrip("%"))
            if not (rule["range"][0] <= num <= rule["range"][1]):
                return False, f"Out of range {rule['range']}"
        except ValueError:
            return False, "Not numeric"

    # Length check
    if "max_length" in rule and len(str_value) > rule["max_length"]:
        return False, f"Too long (>{rule['max_length']} chars)"
    if "min_length" in rule and len(str_value) < rule["min_length"]:
        return False, f"Too short (<{rule['min_length']} chars)"

    # Sentence check (register numbers should not contain spaces forming sentences)
    if rule.get("no_sentence") and len(str_value.split()) > 5:
        return False, "Looks like a sentence, not an identifier"

    return True, "valid"


def calculate_field_confidence(
    field_name: str,
    value,
    ocr_confidence: float = 0.0,
    label_matched: bool = False,
    bbox_proximity: bool = False,
    format_valid: bool = True,
    engine_agreement: bool = False,
) -> float:
    """
    Calculate confidence for a single extracted field.

    Factors:
    - OCR engine confidence (base)
    - Label/keyword match quality
    - Spatial proximity (bbox-based)
    - Format validation pass
    - Agreement between EasyOCR and Tesseract

    Returns confidence 0.0 - 1.0
    """
    if value is None:
        return 0.0

    confidence = 0.0

    # Base: OCR confidence (40% weight)
    confidence += ocr_confidence * 0.40

    # Label match (25% weight)
    if label_matched:
        confidence += 0.25

    # Spatial proximity (15% weight)
    if bbox_proximity:
        confidence += 0.15

    # Format validation (10% weight)
    if format_valid:
        confidence += 0.10

    # Engine agreement (10% weight)
    if engine_agreement:
        confidence += 0.10

    return min(1.0, round(confidence, 2))

