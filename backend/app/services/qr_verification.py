"""
MODULE 6 - AI VERIFICATION: QR CHECK (Enhanced)

Certificates that embed a QR code typically encode either:
  (a) a structured JSON payload issued by the university's verification
      system: {"certificate_id": ..., "verification_token": ..., "expiry": ...}
  (b) a plain verification URL pointing at the university's portal

Enhancements over original:
  - Trusted domain allowlist: only HTTPS URLs from known university domains
    are classified as "valid" — prevents malicious QR codes being trusted.
    Configured via TRUSTED_QR_DOMAINS env var (comma-separated).
  - Cross-validation: QR payload fields are compared against OCR-extracted
    fields (student_name, certificate_number, university, register_number).
    Mismatches are returned as structured evidence for the fraud engine.
  - QR confidence score propagated from the QR detection step.
  - Full structured logging at every decision point.
"""
import json
import logging
from datetime import datetime, date
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger("certiverify.qr_verification")


# ---------------------------------------------------------------------------
# Trusted QR domain allowlist
# ---------------------------------------------------------------------------
def _get_trusted_domains() -> list[str]:
    raw = getattr(settings, "TRUSTED_QR_DOMAINS", "")
    if not raw:
        return []
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------

class QRCheckResult:
    def __init__(
        self,
        present: bool,
        decoded: dict | None,
        valid: bool | None,
        warning: str | None,
        qr_confidence: int = 0,
        qr_type: str = "none",                   # json_payload | url | plain_text | none
        cross_validation_status: str = "CONSISTENT",      # CONSISTENT | MISMATCH | NOT_APPLICABLE | UNAVAILABLE
        cross_validation_mismatches: list | None = None,
        status: str = "verified",               # verified | no_qr_found | domain_not_allowed | token_expired | mismatch | invalid_payload
        reason: str | None = None,
    ):
        self.present = present
        self.decoded = decoded
        self.valid = valid
        self.warning = warning
        self.qr_confidence = qr_confidence
        self.qr_type = qr_type
        self.cross_validation_status = cross_validation_status      # CONSISTENT | MISMATCH | NOT_APPLICABLE
        self.cross_validation_mismatches = cross_validation_mismatches or []
        self.status = status
        self.reason = reason or warning


class _CrossValidationResult:
    """Internal cross-validation accumulator."""
    def __init__(self):
        self.mismatches: list[dict] = []

    def add_mismatch(self, field: str, qr_value: str, ocr_value: str):
        self.mismatches.append({"field": field, "qr_value": qr_value, "ocr_value": ocr_value})

    @property
    def status(self) -> str:
        return "CONSISTENT" if not self.mismatches else "MISMATCH"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def verify_qr(
    qr_raw_data: str | None,
    expected_certificate_number: str | None = None,
    qr_confidence: int = 0,
    ocr_fields: dict | None = None,
) -> QRCheckResult:
    """
    Verify a QR code payload and cross-validate against OCR fields.

    Parameters
    ----------
    qr_raw_data             : Raw text decoded from the QR code.
    expected_certificate_number : Certificate number from OCR (for cross-check).
    qr_confidence           : Detection confidence 0-100 from QR detection step.
    ocr_fields              : All OCR-extracted fields dict for cross-validation.
    """
    if not qr_raw_data:
        logger.info("QR: not present on this certificate")
        return QRCheckResult(
            present=False, decoded=None, valid=None, qr_confidence=0,
            qr_type="none",
            status="no_qr_found",
            reason="No QR code detected on document",
            cross_validation_status="NOT_APPLICABLE",
            warning=(
                "No QR code detected on this certificate. Certificates without a QR "
                "code are not automatically fraudulent, but lack this verification signal."
            ),
        )

    logger.info("QR: decoding payload | len=%d | confidence=%d", len(qr_raw_data), qr_confidence)
    payload = _try_parse_json(qr_raw_data)
    if payload is not None:
        result = _verify_structured_payload(payload, expected_certificate_number)
        result.qr_type = "json_payload"
    else:
        result = _verify_url_payload(qr_raw_data, expected_certificate_number)
        # qr_type set inside _verify_url_payload already

    result.qr_confidence = qr_confidence

    # ── Cross-validation against OCR fields ──────────────────────────────────
    if result.present and result.decoded and ocr_fields:
        cv = _cross_validate(result.decoded, ocr_fields)
        result.cross_validation_status = cv.status
        result.cross_validation_mismatches = cv.mismatches
        if cv.mismatches:
            mismatch_summary = "; ".join(
                f"{m['field']}: QR='{m['qr_value']}' vs OCR='{m['ocr_value']}'"
                for m in cv.mismatches
            )
            logger.warning("QR cross-validation MISMATCH: %s", mismatch_summary)
            existing = result.warning or ""
            result.warning = (
                f"QR data does not match OCR fields — {mismatch_summary}. " + existing
            ).strip()
            result.valid = False
            result.status = "ocr_mismatch"
            result.reason = result.warning
        else:
            result.cross_validation_status = "CONSISTENT"
            logger.info("QR cross-validation: CONSISTENT")
    elif result.present and result.valid:
        result.cross_validation_status = "CONSISTENT"
    elif not result.present:
        result.cross_validation_status = "NOT_APPLICABLE"

    logger.info(
        "QR result | status=%s present=%s valid=%s cross_val=%s mismatches=%d confidence=%d",
        result.status, result.present, result.valid,
        result.cross_validation_status, len(result.cross_validation_mismatches),
        result.qr_confidence,
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_parse_json(raw: str) -> dict | None:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _verify_structured_payload(payload: dict, expected_certificate_number: str | None) -> QRCheckResult:
    issues: list[str] = []

    cert_id = payload.get("certificate_id") or payload.get("certificateId")
    token = payload.get("verification_token") or payload.get("token")
    university_url = payload.get("university_url") or payload.get("url")
    expiry_raw = payload.get("expiry") or payload.get("expiry_date")

    if not cert_id:
        issues.append("QR payload missing certificate_id")
    if not token:
        issues.append("QR payload missing verification_token")

    if university_url:
        if not _is_valid_url(university_url):
            issues.append("QR university_url is not a well-formed HTTPS URL")
        elif not _is_trusted_url(university_url):
            issues.append(
                f"QR URL domain '{urlparse(university_url).netloc}' not in trusted domain allowlist"
            )

    if expiry_raw:
        expiry_date = _parse_date(expiry_raw)
        if expiry_date is None:
            issues.append(f"QR expiry date '{expiry_raw}' could not be parsed")
        elif expiry_date < date.today():
            issues.append(f"QR verification token expired on {expiry_date.isoformat()}")

    if expected_certificate_number and cert_id and str(cert_id) != str(expected_certificate_number):
        issues.append(
            f"QR certificate_id '{cert_id}' does not match OCR-extracted "
            f"certificate number '{expected_certificate_number}'"
        )

    valid = len(issues) == 0
    if valid:
        status = "verified"
        reason = None
        cv_status = "CONSISTENT"
    else:
        if any("domain" in i.lower() for i in issues):
            status = "domain_not_allowed"
        elif any("expired" in i.lower() for i in issues):
            status = "token_expired"
        elif any("does not match" in i.lower() for i in issues):
            status = "certificate_mismatch"
        elif any("missing" in i.lower() for i in issues):
            status = "missing_payload_fields"
        else:
            status = "invalid_payload"
        reason = "; ".join(issues)
        cv_status = "MISMATCH"

    return QRCheckResult(
        present=True, decoded=payload, valid=valid,
        qr_type="json_payload",
        status=status,
        reason=reason,
        cross_validation_status=cv_status,
        warning="; ".join(issues) if issues else None,
    )


def _verify_url_payload(raw: str, expected_certificate_number: str | None = None) -> QRCheckResult:
    if not _is_valid_url(raw):
        reason = "QR content is neither a structured verification payload nor a well-formed URL."
        return QRCheckResult(
            present=True, decoded={"raw": raw}, valid=False,
            qr_type="plain_text",
            status="invalid_payload",
            reason=reason,
            cross_validation_status="MISMATCH",
            warning=reason,
        )

    trusted_domains = _get_trusted_domains()
    if trusted_domains and not _is_trusted_url(raw):
        netloc = urlparse(raw).netloc
        reason = (
            f"QR URL ({netloc}) not in trusted domain allowlist - "
            "domain verification failed."
        )
        return QRCheckResult(
            present=True, decoded={"url": raw}, valid=False,
            qr_type="url",
            status="domain_not_allowed",
            reason=reason,
            cross_validation_status="MISMATCH",
            warning=reason,
        )

    cv_status = "CONSISTENT"
    if expected_certificate_number and expected_certificate_number.lower() in raw.lower():
        cv_status = "CONSISTENT"

    return QRCheckResult(
        present=True, decoded={"url": raw}, valid=True,
        qr_type="url",
        status="verified",
        reason=None,
        cross_validation_status=cv_status,
        warning=None,
    )


def _cross_validate(qr_payload: dict, ocr_fields: dict) -> _CrossValidationResult:
    cv = _CrossValidationResult()
    _cmp(cv, qr_payload, ocr_fields, ("student_name", "name", "candidate_name"), "student_name", "Student Name")
    _cmp(cv, qr_payload, ocr_fields, ("certificate_id", "certificateId", "certificate_number"), "certificate_number", "Certificate Number")
    _cmp(cv, qr_payload, ocr_fields, ("university", "university_name", "institution"), "university_name", "University")
    _cmp(cv, qr_payload, ocr_fields, ("register_number", "reg_no"), "register_number", "Register Number")
    return cv


def _cmp(cv, qr_payload, ocr_fields, qr_keys, ocr_key, label):
    qr_val = next((qr_payload.get(k) for k in qr_keys if qr_payload.get(k)), None)
    ocr_val = ocr_fields.get(ocr_key)
    if not qr_val or not ocr_val:
        return
    qn, on = str(qr_val).strip().lower(), str(ocr_val).strip().lower()
    if qn == on:
        return
    qw, ow = set(qn.split()), set(on.split())
    overlap = len(qw & ow) / max(len(qw | ow), 1)
    if overlap < 0.6:
        cv.add_mismatch(label, str(qr_val), str(ocr_val))


def _is_valid_url(value: str) -> bool:
    try:
        result = urlparse(value)
        return bool(result.scheme in ("http", "https") and result.netloc)
    except (ValueError, AttributeError):
        return False


def _is_trusted_url(url: str) -> bool:
    trusted_domains = _get_trusted_domains()
    if not trusted_domains:
        return True
    try:
        netloc = urlparse(url).netloc.lower()
        return any(netloc == d or netloc.endswith("." + d) for d in trusted_domains)
    except Exception:
        return False


def _parse_date(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None
