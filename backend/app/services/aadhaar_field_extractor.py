"""
AADHAAR FIELD EXTRACTOR  —  Priority 1 Enhancement
===================================================

Extracts all structured fields from cleaned Aadhaar OCR text.
Never returns raw OCR text — only validated, cleaned field values.

Output contract:
{
    "document_type": "Aadhaar Card",
    "confidence": 98,           # 0-100 int
    "fields": {
        "name":              str | None,
        "aadhaar_number":    str | None,   # 12 digits, no spaces
        "vid":               str | None,   # 16 digits
        "dob":               str | None,   # DD/MM/YYYY or YYYY
        "gender":            str | None,   # Male / Female / Transgender
        "address":           str | None,
        "district":          str | None,
        "state":             str | None,
        "pincode":           str | None,   # 6-digit
        "mobile":            str | None,   # 10-digit Indian mobile
        "enrolment_number":  str | None,   # NNNN/NNNNN/NNNNN
        "qr_present":        bool,
        "photo_present":     bool,
    },
    "field_confidences": {
        "name": 0.97, "aadhaar_number": 1.0, ...
    }
}

Logging: all 9 steps defined in the spec are logged at INFO level.
Failure handling: returns None per field — never hallucinated values.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("certiverify.aadhaar_field_extractor")


# ---------------------------------------------------------------------------
# Known Indian states for address parsing
# ---------------------------------------------------------------------------

_INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "andaman and nicobar islands", "chandigarh", "dadra and nagar haveli",
    "daman and diu", "delhi", "jammu and kashmir", "ladakh", "lakshadweep",
    "puducherry",
}

# ---------------------------------------------------------------------------
# Government heading patterns to SKIP when extracting name
# ---------------------------------------------------------------------------

_GOV_HEADINGS = re.compile(
    r"(?:government\s+of\s+india|unique\s+identification\s+authority"
    r"|uidai|of\s+india|भारत\s+सरकार|भारतीय\s+विशिष्ट\s+पहचान)"
    r"|resident|my\s+aadhaar|mera\s+aadhaar",
    re.IGNORECASE,
)

# Lines that are clearly labels / headers, not names
_LABEL_LINES = re.compile(
    r"^\s*(?:to|name|address|date\s*of\s*birth|dob|gender|year\s*of\s*birth"
    r"|vid|aadhaar|enrolment|mobile|phone|pincode|district|state|your\s+aadhaar"
    r"|male|female|transgender|resident)\s*[:\-]?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Aadhaar document detection — weighted keyword scoring
# ---------------------------------------------------------------------------

_AADHAAR_KEYWORDS: list[tuple[str, int]] = [
    ("unique identification authority of india", 5),
    ("government of india", 5),
    ("your aadhaar no", 5),
    ("aadhaar no", 5),
    ("aadhaar number", 4),
    ("uidai", 4),
    ("aadhaar", 4),
    ("masked aadhaar", 4),
    ("enrolment no", 4),
    ("enrolment number", 4),
    ("enrolment id", 3),
    ("qr code", 3),
    ("vid", 2),
    ("date of birth", 2),
    ("year of birth", 2),
    ("dob", 2),
    ("government emblem", 2),
    ("male", 1),
    ("female", 1),
    ("resident", 1),
]

_MAX_AADHAAR_SCORE = sum(w for _, w in _AADHAAR_KEYWORDS)


def _compute_aadhaar_confidence(text: str) -> int:
    """Return 0-100 Aadhaar document confidence based on weighted keyword matching."""
    text_l = text.lower()
    score = sum(w for kw, w in _AADHAAR_KEYWORDS if kw in text_l)
    matched = [kw for kw, _ in _AADHAAR_KEYWORDS if kw in text_l]
    logger.info("[Aadhaar] Matched Aadhaar Keywords: %s", matched)
    pct = min(100, int((score / _MAX_AADHAAR_SCORE) * 100))
    logger.info("[Aadhaar] Detected Document Type: Aadhaar Card (%d%%)", pct)
    return pct


# ---------------------------------------------------------------------------
# Individual field extractors
# ---------------------------------------------------------------------------

def _extract_aadhaar_number(text: str) -> tuple[Optional[str], float]:
    """
    Extract 12-digit Aadhaar number.
    Pattern: first digit 2-9, printed as XXXX XXXX XXXX or XXXXXXXXXXXX or XX-XX-XX.
    Returns (clean_12_digit_string, confidence).
    """
    # Spaced/dashed format: 5370 8621 6637 or 5370-8621-6637
    m = re.search(r"\b([2-9]\d{3})[\s\-](\d{4})[\s\-](\d{4})\b", text)
    if m:
        num = m.group(1) + m.group(2) + m.group(3)
        logger.info("[Aadhaar] Aadhaar Number extracted (spaced): %s", num)
        return num, 1.0

    # Compact 12-digit
    m = re.search(r"\b([2-9]\d{11})\b", text)
    if m:
        num = m.group(1)
        logger.info("[Aadhaar] Aadhaar Number extracted (compact): %s", num)
        return num, 0.95

    # Masked Aadhaar: XXXX XXXX 1234
    m = re.search(r"\b[Xx*]{4}[\s\-]?[Xx*]{4}[\s\-]?(\d{4})\b", text)
    if m:
        num = "XXXXXXXX" + m.group(1)
        logger.info("[Aadhaar] Masked Aadhaar Number: %s", num)
        return num, 0.90

    logger.info("[Aadhaar] Aadhaar Number: not found")
    return None, 0.0


def _extract_vid(text: str) -> tuple[Optional[str], float]:
    """
    Extract 16-digit Virtual ID.
    Pattern: VID: XXXX XXXX XXXX XXXX or VID XXXXXXXXXXXXXXXX
    """
    # Labeled VID
    m = re.search(
        r"(?:vid|virtual\s*id)\s*[:\s]+(\d[\d\s]{13,19}\d)",
        text, re.IGNORECASE
    )
    if m:
        vid = re.sub(r"\s+", "", m.group(1))
        if len(vid) == 16:
            logger.info("[Aadhaar] VID extracted (labeled): %s", vid)
            return vid, 0.98

    # Unlabeled 16-digit block (not an Aadhaar number)
    # VID is 16 digits — look for 4-group pattern after Aadhaar number
    m = re.search(r"\b(\d{4})\s(\d{4})\s(\d{4})\s(\d{4})\b", text)
    if m:
        candidate = m.group(1) + m.group(2) + m.group(3) + m.group(4)
        # Make sure this is not the Aadhaar number (12 digits)
        if len(candidate) == 16:
            logger.info("[Aadhaar] VID extracted (unlabeled 16-digit block): %s", candidate)
            return candidate, 0.85

    logger.info("[Aadhaar] VID: not found")
    return None, 0.0


def _extract_dob(text: str) -> tuple[Optional[str], float]:
    """
    Extract Date of Birth.
    Supports: DOB, Date of Birth, Year of Birth.
    Formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYY.
    """
    # Full date after label
    m = re.search(
        r"(?:dob|date\s*of\s*birth)\s*[:\s/]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})",
        text, re.IGNORECASE
    )
    if m:
        dob = m.group(1).replace("-", "/").replace(".", "/")
        logger.info("[Aadhaar] DOB extracted (labeled full date): %s", dob)
        return dob, 0.96

    # Year of Birth only
    m = re.search(
        r"(?:year\s*of\s*birth|yob)\s*[:\s]+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        dob = m.group(1)
        logger.info("[Aadhaar] DOB extracted (year of birth): %s", dob)
        return dob, 0.85

    # Unlabeled date in DD/MM/YYYY format
    m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text)
    if m:
        dob = m.group(1)
        logger.info("[Aadhaar] DOB extracted (unlabeled date): %s", dob)
        return dob, 0.75

    logger.info("[Aadhaar] DOB: not found")
    return None, 0.0


def _extract_gender(text: str) -> tuple[Optional[str], float]:
    """Extract gender: Male / Female / Transgender."""
    m = re.search(r"\b(male|female|transgender)\b", text, re.IGNORECASE)
    if m:
        gender = m.group(1).capitalize()
        logger.info("[Aadhaar] Gender extracted: %s", gender)
        return gender, 0.98
    logger.info("[Aadhaar] Gender: not found")
    return None, 0.0


def _extract_name(text: str) -> tuple[Optional[str], float]:
    """
    Extract the person name from Aadhaar OCR text.

    Strategy (in priority order):
    1. Find the first valid Title Case name line after "To" keyword
    2. Find the first valid Title Case line before DOB keyword
    3. Find name after explicit "Name:" label
    4. First Title Case line in the text that is not a government heading

    Name is NEVER:
    - "Government of India"
    - "UIDAI"
    - "Unique Identification Authority"
    - A single word < 3 chars
    - All uppercase header lines
    - Lines that are clearly labels (DOB, Gender, Address, etc.)
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    def is_valid_name(ln: str) -> bool:
        """Return True if line looks like a personal name."""
        ln = ln.strip()
        if not ln or len(ln) < 3:
            return False
        if _GOV_HEADINGS.search(ln):
            return False
        if _LABEL_LINES.match(ln):
            return False
        # Must contain at least one letter
        if not any(c.isalpha() for c in ln):
            return False
        # Should not be all digits
        if all(c.isdigit() or c.isspace() for c in ln):
            return False
        # Must not contain address-like tokens (numbers, commas in middle, etc.)
        if re.search(r"\d", ln):
            return False
        # Reject lines that are too long to be a person name (> 6 words)
        if len(ln.split()) > 6:
            return False
        # Accept: Title Case names with optional single-letter initials
        # Covers: "Keerthana K", "K. Anitha", "Ravi Kumar S", "A B Sharma"
        if re.match(r"^[A-Z][a-zA-Z.]*(?:\s+[A-Z][a-zA-Z.]*){0,5}$", ln):
            return True
        return False

    # Strategy 1: Line right after "To" keyword
    for i, ln in enumerate(lines):
        if re.match(r"^To\s*$", ln, re.IGNORECASE):
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if is_valid_name(candidate):
                    logger.info("[Aadhaar] Name extracted after 'To': %s", candidate)
                    return candidate, 0.97

    # Strategy 2: Line before DOB/Date of Birth/Year of Birth keyword
    for i, ln in enumerate(lines):
        if re.search(r"(?:date\s*of\s*birth|dob|year\s*of\s*birth)", ln, re.IGNORECASE):
            for prev in reversed(lines[max(0, i - 5): i]):
                if is_valid_name(prev):
                    logger.info("[Aadhaar] Name extracted before DOB: %s", prev)
                    return prev, 0.95

    # Strategy 3: After explicit "Name:" label
    m = re.search(r"(?:^|\n)\s*name\s*[:\-]\s*([A-Z][a-zA-Z. ]{2,50})", text, re.IGNORECASE | re.MULTILINE)
    if m:
        candidate = m.group(1).strip()
        if is_valid_name(candidate) and not _GOV_HEADINGS.search(candidate):
            logger.info("[Aadhaar] Name extracted after 'Name:' label: %s", candidate)
            return candidate, 0.90

    # Strategy 4: First valid Title Case line anywhere in text
    for ln in lines:
        if is_valid_name(ln):
            logger.info("[Aadhaar] Name extracted (first valid line): %s", ln)
            return ln, 0.70

    logger.info("[Aadhaar] Name: not found")
    return None, 0.0


def _extract_address_block(text: str) -> tuple[Optional[str], float]:
    """
    Extract the full address block.
    Locates text beginning after "To" keyword or "Address:" label,
    extracts until a 6-digit pincode or double newline.
    """
    # After "To" keyword (common Aadhaar format: To\n<Name>\n<Address lines>)
    m = re.search(
        r"(?:^|\n)To\s*\n(.+?)(?=\n{2,}|\b\d{6}\b|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if m:
        addr_raw = m.group(1).strip()
        addr = re.sub(r"\s+", " ", addr_raw)
        if len(addr) > 10:
            logger.info("[Aadhaar] Address extracted after 'To': %s", addr[:80])
            return addr, 0.92

    # After "Address:" or "S/O", "D/O", "W/O", "C/O"
    m = re.search(
        r"(?:address|s/o|d/o|w/o|c/o)\s*[:\s]*(.{10,300}?)(?=\n{2,}|\b\d{6}\b|$)",
        text, re.IGNORECASE | re.DOTALL
    )
    if m:
        addr_raw = m.group(1).strip()
        addr = re.sub(r"\s+", " ", addr_raw)
        if len(addr) > 10:
            logger.info("[Aadhaar] Address extracted after address label: %s", addr[:80])
            return addr, 0.88

    logger.info("[Aadhaar] Address: not found")
    return None, 0.0


def _extract_pincode(text: str, address: Optional[str] = None) -> tuple[Optional[str], float]:
    """
    Extract 6-digit Indian pincode.
    Searches address block first, then full text.
    """
    search_text = (address or "") + "\n" + text
    # All 6-digit numbers that start with 1-9
    pincodes = re.findall(r"\b([1-9]\d{5})\b", search_text)
    if pincodes:
        pin = pincodes[-1]  # last 6-digit number in address/text is usually pincode
        logger.info("[Aadhaar] Pincode extracted: %s", pin)
        return pin, 0.95
    logger.info("[Aadhaar] Pincode: not found")
    return None, 0.0


def _extract_state(text: str, address: Optional[str] = None) -> tuple[Optional[str], float]:
    """
    Extract Indian state from address text.
    Matches against known state names list.
    """
    search_text = ((address or "") + " " + text).lower()
    # Check longest match first to avoid "goa" matching inside "meghalaya"
    for state in sorted(_INDIAN_STATES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(state) + r"\b", search_text):
            logger.info("[Aadhaar] State extracted: %s", state.title())
            return state.title(), 0.92
    logger.info("[Aadhaar] State: not found")
    return None, 0.0


def _extract_district(text: str, address: Optional[str], state: Optional[str]) -> tuple[Optional[str], float]:
    """
    Extract district from address block or full text.
    Strategy 1: word cluster immediately before the state name in extracted address.
    Strategy 2: word cluster immediately before the state name in full text.
    Strategy 3: second-to-last comma-separated segment before the pincode.
    """
    search_texts = []
    if address:
        search_texts.append(address.strip())
    search_texts.append(text)

    if state:
        state_l = state.lower().strip()
        for src in search_texts:
            idx = src.lower().find(state_l)
            if idx > 0:
                before_state = src[:idx].strip().rstrip(", ")
                # Split by spaces or commas to get words before state
                tokens = re.split(r"[,\n\s]+", before_state)
                tokens = [t.strip() for t in tokens if t.strip() and not re.search(r"\d", t)]
                # Work backward from end to find a proper-noun-looking token
                for tok in reversed(tokens[-3:]):
                    if len(tok) > 3 and tok[0].isupper():
                        logger.info("[Aadhaar] District extracted: %s", tok)
                        return tok, 0.88

    # Fallback: remove pincode, walk address segments
    addr = (address or text).strip()
    addr_clean = re.sub(r"\b\d{6}\b", "", addr).strip()
    segments = [s.strip() for s in re.split(r"[,\n]+", addr_clean) if s.strip()]
    for seg in reversed(segments):
        seg_clean = seg.strip().rstrip(",. ")
        if (
            len(seg_clean) > 3
            and not re.search(r"\d", seg_clean)
            and (state is None or seg_clean.lower() not in state.lower())
        ):
            logger.info("[Aadhaar] District extracted (fallback): %s", seg_clean)
            return seg_clean, 0.70

    logger.info("[Aadhaar] District: not found")
    return None, 0.0



def _extract_mobile(text: str, aadhaar_number: Optional[str] = None, pincode: Optional[str] = None) -> tuple[Optional[str], float]:
    """
    Extract Indian 10-digit mobile number.
    Must start with 6, 7, 8, or 9.
    Avoids confusing with Aadhaar number digits or pincode.
    """
    # Look after mobile/phone label first
    m = re.search(
        r"(?:mobile|phone|contact|mob)\s*[:\s]+([6-9]\d{9})\b",
        text, re.IGNORECASE
    )
    if m:
        mob = m.group(1)
        # Verify it's not part of the aadhaar number
        if aadhaar_number and mob in aadhaar_number:
            logger.info("[Aadhaar] Mobile candidate %s is part of Aadhaar number — skipping", mob)
        else:
            logger.info("[Aadhaar] Mobile extracted (labeled): %s", mob)
            return mob, 0.97

    # Unlabeled 10-digit mobile starting with 6-9
    candidates = re.findall(r"\b([6-9]\d{9})\b", text)
    for mob in candidates:
        # Skip if it's the aadhaar number or part of it
        if aadhaar_number and mob in aadhaar_number:
            continue
        # Skip if it contains the pincode (unlikely to be a mobile)
        if pincode and mob.startswith(pincode):
            continue
        # Skip if it appears right after aadhaar/uid label
        aadhaar_context = re.search(
            r"(?:aadhaar|uid|uidai)\s*(?:no|number)?\s*[:\s]*" + re.escape(mob),
            text, re.IGNORECASE
        )
        if aadhaar_context:
            continue
        logger.info("[Aadhaar] Mobile extracted (unlabeled): %s", mob)
        return mob, 0.80

    logger.info("[Aadhaar] Mobile: not found")
    return None, 0.0


def _extract_enrolment_number(text: str) -> tuple[Optional[str], float]:
    """
    Extract Aadhaar enrolment number.
    Format: NNNN/NNNNN/NNNNN (e.g. 2193/10304/42335)
    """
    m = re.search(r"\b(\d{4}/\d{5}/\d{5})\b", text)
    if m:
        enrol = m.group(1)
        logger.info("[Aadhaar] Enrolment Number extracted: %s", enrol)
        return enrol, 0.98
    # Alternative format with spaces or dashes
    m = re.search(r"\b(\d{4})[\s/\-](\d{5})[\s/\-](\d{5})\b", text)
    if m:
        enrol = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        logger.info("[Aadhaar] Enrolment Number extracted (alt format): %s", enrol)
        return enrol, 0.90
    logger.info("[Aadhaar] Enrolment Number: not found")
    return None, 0.0


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def extract_aadhaar_fields(
    raw_text: str,
    qr_present: bool = False,
    photo_present: bool = False,
) -> dict:
    """
    Extract all structured Aadhaar fields from OCR text.

    Parameters
    ----------
    raw_text     : Cleaned merged OCR text from AadhaarOCRResult.raw_text
    qr_present   : From AadhaarOCRResult.qr_present
    photo_present: From AadhaarOCRResult.photo_present

    Returns
    -------
    dict with keys: document_type, confidence, fields, field_confidences
    """
    logger.info("[Aadhaar] === Extracted Fields START ===")

    # Document detection confidence
    doc_confidence = _compute_aadhaar_confidence(raw_text)

    # Extract all fields
    name, name_conf                   = _extract_name(raw_text)
    aadhaar_num, aadhaar_conf         = _extract_aadhaar_number(raw_text)
    vid, vid_conf                     = _extract_vid(raw_text)
    dob, dob_conf                     = _extract_dob(raw_text)
    gender, gender_conf               = _extract_gender(raw_text)
    address, address_conf             = _extract_address_block(raw_text)
    pincode, pincode_conf             = _extract_pincode(raw_text, address)
    state, state_conf                 = _extract_state(raw_text, address)
    district, district_conf           = _extract_district(raw_text, address, state)
    mobile, mobile_conf               = _extract_mobile(raw_text, aadhaar_number=aadhaar_num, pincode=pincode)
    enrolment_num, enrolment_conf     = _extract_enrolment_number(raw_text)

    fields = {
        "name":             name,
        "aadhaar_number":   aadhaar_num,
        "vid":              vid,
        "dob":              dob,
        "gender":           gender,
        "address":          address,
        "district":         district,
        "state":            state,
        "pincode":          pincode,
        "mobile":           mobile,
        "enrolment_number": enrolment_num,
        "qr_present":       qr_present,
        "photo_present":    photo_present,
    }

    field_confidences = {
        "name":             name_conf,
        "aadhaar_number":   aadhaar_conf,
        "vid":              vid_conf,
        "dob":              dob_conf,
        "gender":           gender_conf,
        "address":          address_conf,
        "district":         district_conf,
        "state":            state_conf,
        "pincode":          pincode_conf,
        "mobile":           mobile_conf,
        "enrolment_number": enrolment_conf,
        "qr_present":       1.0,
        "photo_present":    1.0,
    }

    # Log extracted vs missing fields
    extracted = {k: v for k, v in fields.items() if v is not None and v is not False}
    missing   = [k for k, v in fields.items() if v is None]
    logger.info("[Aadhaar] Extracted Fields: %s", list(extracted.keys()))
    logger.info("[Aadhaar] Missing Fields: %s", missing)

    result = {
        "document_type":   "Aadhaar Card",
        "confidence":      doc_confidence,
        "fields":          fields,
        "field_confidences": field_confidences,
    }

    logger.info("[Aadhaar] === Extracted Fields COMPLETE | confidence=%d%% ===", doc_confidence)
    return result
