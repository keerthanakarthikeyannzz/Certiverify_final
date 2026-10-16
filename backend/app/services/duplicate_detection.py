"""
MODULE 7 - DUPLICATE CERTIFICATE DETECTION & RECORD INTEGRITY (Enhanced)

Detection pipeline (ordered cheapest → most expensive):

  PART A — SHA-256 exact file hash (strongest — stops early)
  PART B — Certificate identity extraction (cert_no, reg_no, roll_no, QR)
  PART C — Certificate number duplicate + conflict detection
  PART D — Registration / roll number match
  PART E — QR payload duplicate
  PART G — Fuzzy field similarity (RapidFuzz token_sort_ratio)
  PART H — Field similarity score aggregation
  PART I — Visual similarity (OpenCV dHash, run only when needed)
  PART J — Duplicate category classification
  PART L — Confidence calculation
  PART M — Structured result

Duplicate categories (PART J):
  NO_DUPLICATE            — no matching certificate found
  EXACT_FILE_DUPLICATE    — same SHA-256 byte-for-byte
  DUPLICATE_UPLOAD        — same cert identity, same owner re-upload
  DUPLICATE_CERTIFICATE   — same cert number + all fields agree
  POSSIBLE_DUPLICATE      — high field/visual similarity, no exact key
  CERTIFICATE_CONFLICT    — same cert number but conflicting identity fields
  QR_DUPLICATE            — identical QR payload reused
  BLOCKCHAIN_DUPLICATE    — (set externally via blockchain module)

Backward compatibility:
  DuplicateCheckResult still exposes is_duplicate, duplicate_of_certificate_id,
  match_reason — all new fields are additive.  Existing callers need no changes.
"""
from __future__ import annotations

import io
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from rapidfuzz import fuzz

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Certificate, OCRData

logger = logging.getLogger("certiverify.duplicate")

# ---------------------------------------------------------------------------
# Duplicate category constants (PART J)
# ---------------------------------------------------------------------------
NO_DUPLICATE                = "NO_DUPLICATE"
EXACT_FILE_DUPLICATE        = "EXACT_FILE_DUPLICATE"
DUPLICATE_UPLOAD            = "DUPLICATE_UPLOAD"
DUPLICATE_CERTIFICATE       = "DUPLICATE_CERTIFICATE"
POSSIBLE_DUPLICATE          = "POSSIBLE_DUPLICATE"
CERTIFICATE_CONFLICT        = "CERTIFICATE_CONFLICT"
QR_DUPLICATE                = "QR_DUPLICATE"
BLOCKCHAIN_DUPLICATE        = "BLOCKCHAIN_DUPLICATE"
OWN_REUPLOAD                = "own_reupload"
SUSPICIOUS_ALTERED_REUPLOAD = "suspicious: altered re-upload"


# Fields used for identity comparison (PART G/H)
_IDENTITY_FIELDS = [
    "student_name",
    "university_name",
    "certificate_number",
    "register_number",
    "roll_number",
    "course",
    "department",
]

# Minimum fuzzy similarity to flag as POSSIBLE_DUPLICATE
_FUZZY_THRESHOLD = 85.0
# Minimum visual similarity to boost confidence
_VISUAL_THRESHOLD = 75.0
# Key conflict fields — mismatch here → CERTIFICATE_CONFLICT
_CONFLICT_SENSITIVE_FIELDS = {"student_name", "university_name"}


# ---------------------------------------------------------------------------
# Result dataclass (PART M) — additive over original
# ---------------------------------------------------------------------------

@dataclass
class DuplicateCheckResult:
    # ── Original fields (backward-compatible) ───────────────────────────────
    is_duplicate: bool
    duplicate_of_certificate_id: Optional[str]
    match_reason: Optional[str]

    # ── New additive fields ──────────────────────────────────────────────────
    duplicate_type: str = NO_DUPLICATE
    duplicate_status: str = NO_DUPLICATE
    confidence: float = 0.0
    matched_fields: list = field(default_factory=list)
    conflicting_fields: list = field(default_factory=list)
    field_similarity: float = 0.0
    visual_similarity: float = 0.0
    same_owner: bool = False

    # Detail flags (PART M structured result)
    file_hash_match: bool = False
    certificate_number_match: bool = False
    registration_number_match: bool = False
    qr_match: bool = False

    def to_detail_dict(self) -> dict:
        """Serialize to the duplicate_detail JSON column format."""
        return {
            "duplicate_status":           self.duplicate_status,
            "duplicate_type":             self.duplicate_type,
            "duplicate_detected":         self.is_duplicate,
            "confidence":                 round(self.confidence, 1),
            "matched_certificate_id":     self.duplicate_of_certificate_id,
            "matched_fields":             self.matched_fields,
            "conflicting_fields":         self.conflicting_fields,
            "file_hash_match":            self.file_hash_match,
            "certificate_number_match":   self.certificate_number_match,
            "registration_number_match":  self.registration_number_match,
            "qr_match":                   self.qr_match,
            "field_similarity":           round(self.field_similarity, 1),
            "visual_similarity":          round(self.visual_similarity, 1),
            "same_owner":                 self.same_owner,
            "reason":                     self.match_reason or "No matching certificate record found.",
        }


# ---------------------------------------------------------------------------
# Main entry point — backward-compatible signature + optional file_bytes
# ---------------------------------------------------------------------------

async def detect_duplicates(
    cert: Certificate,
    ocr_row: Optional[OCRData],
    db: AsyncSession,
    file_bytes: Optional[bytes] = None,   # enables visual similarity (PART I)
) -> DuplicateCheckResult:
    """
    Full multi-signal duplicate detection.

    Parameters
    ----------
    cert       : The certificate being checked.
    ocr_row    : Its OCR data row (may be None if OCR not yet run).
    db         : Async DB session.
    file_bytes : Raw file bytes for visual similarity (optional).
    """
    t_start = time.time()

    # ── PART A: Exact SHA-256 file hash ─────────────────────────────────────
    hash_match = await db.execute(
        select(Certificate).where(
            Certificate.sha256_hash == cert.sha256_hash,
            Certificate.id != cert.id,
        )
    )
    matching_certs = hash_match.scalars().all()
    if matching_certs:
        same_owner_cert = next(
            (c for c in matching_certs if _is_same_owner_or_org(cert, c)),
            None
        )
        if same_owner_cert:
            other_cert = same_owner_cert
            same_owner = True
            status = OWN_REUPLOAD
            reason = "You already uploaded this exact file"
        else:
            other_cert = matching_certs[0]
            same_owner = False
            status = EXACT_FILE_DUPLICATE
            reason = "This exact file was previously uploaded by another account or organization. Strong fraud signal."

        _log(cert.id, EXACT_FILE_DUPLICATE, other_cert.id, 100.0, t_start)
        return DuplicateCheckResult(
            is_duplicate=True,
            duplicate_of_certificate_id=other_cert.id,
            match_reason=reason[:255],
            duplicate_type=EXACT_FILE_DUPLICATE,
            duplicate_status=status,
            confidence=100.0,
            matched_fields=["sha256_hash"],
            file_hash_match=True,
            same_owner=same_owner,
        )

    if ocr_row is None:
        return DuplicateCheckResult(
            is_duplicate=False, duplicate_of_certificate_id=None, match_reason=None,
            duplicate_type=NO_DUPLICATE, duplicate_status=NO_DUPLICATE,
        )

    ocr_fields = _extract_ocr_fields(ocr_row)

    # ── PART C: Certificate number ───────────────────────────────────────────
    if ocr_row.certificate_number:
        matching_ocrs = await _find_all_by_ocr_field(
            db, OCRData.certificate_number, ocr_row.certificate_number, cert.id
        )
        if matching_ocrs:
            different_owner_match = None
            same_owner_match = None
            for o in matching_ocrs:
                c = await _load_certificate(db, o.certificate_id)
                if not _is_same_owner_or_org(cert, c):
                    different_owner_match = (o, c)
                    break
                elif same_owner_match is None:
                    same_owner_match = (o, c)

            if different_owner_match:
                other_ocr, other_cert = different_owner_match
                same_owner = False
                other_fields = _extract_ocr_fields(other_ocr)
                matched, conflicting = _compare_identity_fields(ocr_fields, other_fields)
                conflict_detected = bool(set(conflicting) & _CONFLICT_SENSITIVE_FIELDS)
                if conflict_detected:
                    reason = (
                        f"Certificate number '{ocr_row.certificate_number}' matches an existing "
                        f"certificate from a different account or organization and identity fields conflict: {', '.join(conflicting[:3])}. Strong fraud signal."
                    )
                    confidence = max(90.0, 95.0 - len(conflicting) * 1.5)
                    dup_type, dup_status = CERTIFICATE_CONFLICT, CERTIFICATE_CONFLICT
                else:
                    reason = (
                        f"Certificate number '{ocr_row.certificate_number}' is already registered "
                        f"by a different account or organization. Strong fraud signal."
                    )
                    confidence = 94.0
                    dup_type = DUPLICATE_CERTIFICATE
                    dup_status = DUPLICATE_CERTIFICATE
            else:
                other_ocr, other_cert = same_owner_match
                same_owner = True
                other_fields = _extract_ocr_fields(other_ocr)
                matched, conflicting = _compare_identity_fields(ocr_fields, other_fields)
                reason = (
                    f"Suspicious: altered re-upload — same certificate number '{ocr_row.certificate_number}' "
                    f"as your previous upload, but different file content"
                )
                confidence = 85.0
                dup_type = "ALTERED_REUPLOAD"
                dup_status = SUSPICIOUS_ALTERED_REUPLOAD

            _log(cert.id, dup_type, other_ocr.certificate_id, confidence, t_start)
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_of_certificate_id=other_ocr.certificate_id,
                match_reason=reason[:255],
                duplicate_type=dup_type,
                duplicate_status=dup_status,
                confidence=confidence,
                matched_fields=matched + ["certificate_number"],
                conflicting_fields=conflicting,
                certificate_number_match=True,
                same_owner=same_owner,
            )

    # ── PART D: Register / roll number ───────────────────────────────────────
    for col, val, fname in [
        (OCRData.register_number, ocr_row.register_number, "register_number"),
        (OCRData.roll_number,     ocr_row.roll_number,     "roll_number"),
    ]:
        if not val:
            continue
        matching_ocrs = await _find_all_by_ocr_field(db, col, val, cert.id)
        if matching_ocrs:
            different_owner_match = None
            same_owner_match = None
            for o in matching_ocrs:
                c = await _load_certificate(db, o.certificate_id)
                if not _is_same_owner_or_org(cert, c):
                    different_owner_match = (o, c)
                    break
                elif same_owner_match is None:
                    same_owner_match = (o, c)

            fname_title = fname.replace('_', ' ').title()
            if different_owner_match:
                other_ocr, other_cert = different_owner_match
                same_owner = False
                other_fields = _extract_ocr_fields(other_ocr)
                matched, conflicting = _compare_identity_fields(ocr_fields, other_fields)
                reason = (
                    f"{fname_title} '{val}' is already registered on a different file by another account or organization. "
                    f"Strong fraud signal."
                )
                confidence = 88.0
                dup_type = DUPLICATE_CERTIFICATE
                dup_status = DUPLICATE_CERTIFICATE
            else:
                other_ocr, other_cert = same_owner_match
                same_owner = True
                other_fields = _extract_ocr_fields(other_ocr)
                matched, conflicting = _compare_identity_fields(ocr_fields, other_fields)
                reason = (
                    f"Suspicious: altered re-upload — same {fname_title.lower()} '{val}' "
                    f"as your previous upload, but different file content"
                )
                confidence = 80.0
                dup_type = "ALTERED_REUPLOAD"
                dup_status = SUSPICIOUS_ALTERED_REUPLOAD

            _log(cert.id, dup_type, other_ocr.certificate_id, confidence, t_start)
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_of_certificate_id=other_ocr.certificate_id,
                match_reason=reason[:255],
                duplicate_type=dup_type,
                duplicate_status=dup_status,
                confidence=confidence,
                matched_fields=matched + [fname],
                conflicting_fields=conflicting,
                registration_number_match=True,
                same_owner=same_owner,
            )

    # ── PART E: QR payload ───────────────────────────────────────────────────
    if ocr_row.qr_code_data:
        matching_ocrs = await _find_all_by_ocr_field(
            db, OCRData.qr_code_data, ocr_row.qr_code_data, cert.id
        )
        if matching_ocrs:
            different_owner_match = None
            same_owner_match = None
            for o in matching_ocrs:
                c = await _load_certificate(db, o.certificate_id)
                if not _is_same_owner_or_org(cert, c):
                    different_owner_match = (o, c)
                    break
                elif same_owner_match is None:
                    same_owner_match = (o, c)

            if different_owner_match:
                other_ocr, other_cert = different_owner_match
                same_owner = False
                reason = "This QR code has already been registered on a certificate from a different account or organization. Strong fraud signal."
                confidence = 99.0
                dup_type = QR_DUPLICATE
                dup_status = QR_DUPLICATE
            else:
                other_ocr, other_cert = same_owner_match
                same_owner = True
                reason = "Suspicious: altered re-upload — identical QR payload reused with different file content"
                confidence = 85.0
                dup_type = "ALTERED_REUPLOAD"
                dup_status = SUSPICIOUS_ALTERED_REUPLOAD

            _log(cert.id, dup_type, other_ocr.certificate_id, confidence, t_start)
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_of_certificate_id=other_ocr.certificate_id,
                match_reason=reason[:255],
                duplicate_type=dup_type,
                duplicate_status=dup_status,
                confidence=confidence,
                matched_fields=["qr_code_data"],
                qr_match=True,
                same_owner=same_owner,
            )

    # ── PART G/H: Fuzzy field similarity ────────────────────────────────────
    fuzzy_result = await _fuzzy_field_search(db, cert.id, ocr_fields)
    if fuzzy_result:
        other_ocr, field_sim, matched, conflicting = fuzzy_result
        other_cert = await _load_certificate(db, other_ocr.certificate_id)
        same_owner = _is_same_owner_or_org(cert, other_cert)

        # ── PART I: Visual similarity (only when fuzzy ≥70%) ─────────────
        visual_sim = 0.0
        if file_bytes is not None and field_sim >= 70.0:
            try:
                other_bytes = await _load_cert_file_bytes(other_cert)
                if other_bytes:
                    visual_sim = _visual_similarity_dhash(file_bytes, other_bytes)
            except Exception as exc:
                logger.debug("Visual similarity failed (non-fatal): %s", exc)

        confidence = min(field_sim + (visual_sim * 0.1 if visual_sim >= _VISUAL_THRESHOLD else 0), 99.0)
        if same_owner:
            dup_type = "ALTERED_REUPLOAD"
            dup_status = SUSPICIOUS_ALTERED_REUPLOAD
            reason = (
                f"Suspicious: altered re-upload — high similarity ({field_sim:.0f}%) with your previous "
                f"upload {other_ocr.certificate_id[:8]}…, but different file content"
            )
        else:
            dup_type = POSSIBLE_DUPLICATE
            dup_status = POSSIBLE_DUPLICATE
            reason = (
                f"High field similarity ({field_sim:.0f}%) with certificate from another account or organization "
                f"{other_ocr.certificate_id[:8]}… — matched: {', '.join(matched[:3])}. Strong fraud signal."
            )
        _log(cert.id, dup_type, other_ocr.certificate_id, confidence, t_start,
             field_sim=field_sim, visual_sim=visual_sim)
        return DuplicateCheckResult(
            is_duplicate=True,
            duplicate_of_certificate_id=other_ocr.certificate_id,
            match_reason=reason[:255],
            duplicate_type=dup_type,
            duplicate_status=dup_status,
            confidence=confidence,
            matched_fields=matched,
            conflicting_fields=conflicting,
            field_similarity=field_sim,
            visual_similarity=visual_sim,
            same_owner=same_owner,
        )

    _log(cert.id, NO_DUPLICATE, None, 0.0, t_start)
    return DuplicateCheckResult(
        is_duplicate=False, duplicate_of_certificate_id=None, match_reason=None,
        duplicate_type=NO_DUPLICATE, duplicate_status=NO_DUPLICATE, confidence=0.0,
    )


# ---------------------------------------------------------------------------
# PART G — Fuzzy field similarity search across all other certs
# ---------------------------------------------------------------------------

async def _fuzzy_field_search(
    db: AsyncSession, cert_id: str, ocr_fields: dict
) -> Optional[tuple[OCRData, float, list, list]]:
    """
    Compare this cert's fields against all other OCR records using RapidFuzz.
    Returns (best_match_ocr, similarity_pct, matched_fields, conflicting_fields)
    or None if no record exceeds _FUZZY_THRESHOLD.
    """
    if not any(v for v in ocr_fields.values() if v):
        return None   # insufficient data for meaningful comparison

    result = await db.execute(
        select(OCRData).where(OCRData.certificate_id != cert_id)
    )
    all_others = result.scalars().all()

    best_match: Optional[OCRData] = None
    best_sim = 0.0
    best_matched: list = []
    best_conflicting: list = []

    for other_ocr in all_others:
        other_fields = _extract_ocr_fields(other_ocr)
        sim, matched, conflicting = _compute_field_similarity(ocr_fields, other_fields)
        if sim > best_sim:
            best_sim = sim
            best_match = other_ocr
            best_matched = matched
            best_conflicting = conflicting

    if best_match and best_sim >= _FUZZY_THRESHOLD:
        return best_match, best_sim, best_matched, best_conflicting
    return None


# ---------------------------------------------------------------------------
# PART H — Field similarity score (RapidFuzz token_sort_ratio)
# ---------------------------------------------------------------------------

def _compute_field_similarity(fields_a: dict, fields_b: dict) -> tuple[float, list, list]:
    """
    Returns (overall_similarity_pct, matched_fields, conflicting_fields).
    Skips fields that are None/empty in either record.
    """
    scores: list[float] = []
    matched: list[str] = []
    conflicting: list[str] = []

    for fname in _IDENTITY_FIELDS:
        va = _normalize(fields_a.get(fname))
        vb = _normalize(fields_b.get(fname))
        if not va or not vb:
            continue
        ratio = float(fuzz.token_sort_ratio(va, vb))
        scores.append(ratio)
        if ratio >= 90:
            matched.append(fname)
        elif ratio < 60:
            conflicting.append(fname)

    if not scores:
        return 0.0, [], []
    return round(sum(scores) / len(scores), 2), matched, conflicting


def _compare_identity_fields(fields_a: dict, fields_b: dict) -> tuple[list, list]:
    _, matched, conflicting = _compute_field_similarity(fields_a, fields_b)
    return matched, conflicting


# ---------------------------------------------------------------------------
# PART I — Visual similarity (OpenCV dHash — no imagehash dependency)
# ---------------------------------------------------------------------------

def _dhash(image_bytes: bytes, hash_size: int = 8) -> Optional[int]:
    """
    Compute difference hash from raw image bytes.
    Works with JPEG, PNG, WebP via OpenCV; PDF first-page via PIL fallback.
    Returns 64-bit integer or None on failure.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("L")
            img = np.array(pil_img)
        img_resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
        diff = img_resized[:, 1:] > img_resized[:, :-1]
        bits = diff.flatten()
        return int(sum(int(b) << i for i, b in enumerate(bits)))
    except Exception:
        return None


def _visual_similarity_dhash(bytes_a: bytes, bytes_b: bytes) -> float:
    """Returns visual similarity 0–100 (100 = visually identical)."""
    h1 = _dhash(bytes_a)
    h2 = _dhash(bytes_b)
    if h1 is None or h2 is None:
        return 0.0
    dist = bin(h1 ^ h2).count("1")
    return round(max(0.0, 100.0 * (1.0 - dist / 64.0)), 1)


# ---------------------------------------------------------------------------
# PART B — OCR field extraction
# ---------------------------------------------------------------------------

def _extract_ocr_fields(ocr_row: OCRData) -> dict:
    return {f: getattr(ocr_row, f, None) for f in _IDENTITY_FIELDS}


def _normalize(value: Optional[str]) -> Optional[str]:
    """Lowercase, strip, remove punctuation for fair fuzzy comparison."""
    if not value:
        return None
    return re.sub(r"[^\w\s]", "", value.lower().strip())


# ---------------------------------------------------------------------------
# Shared DB / file helpers
# ---------------------------------------------------------------------------

async def _find_by_ocr_field(
    db: AsyncSession, column, value: str, exclude_certificate_id: str
) -> Optional[OCRData]:
    result = await db.execute(
        select(OCRData).where(column == value, OCRData.certificate_id != exclude_certificate_id)
    )
    return result.scalars().first()


async def _find_all_by_ocr_field(
    db: AsyncSession, column, value: str, exclude_certificate_id: str
) -> list[OCRData]:
    result = await db.execute(
        select(OCRData).where(column == value, OCRData.certificate_id != exclude_certificate_id)
    )
    return list(result.scalars().all())


async def _load_certificate(db: AsyncSession, certificate_id: str) -> Optional[Certificate]:
    result = await db.execute(select(Certificate).where(Certificate.id == certificate_id))
    return result.scalar_one_or_none()


async def _load_cert_file_bytes(cert: Optional[Certificate]) -> Optional[bytes]:
    """Load raw file bytes for visual comparison (best-effort, no crash)."""
    if cert is None or not getattr(cert, "storage_path", None):
        return None
    try:
        from app.services.storage_service import get_storage_backend
        storage = get_storage_backend()
        return await storage.read(cert.storage_path)
    except Exception:
        return None


def _is_same_owner_or_org(cert: Certificate, other_cert: Optional[Certificate]) -> bool:
    if other_cert is None:
        return False
    if cert.owner_id and other_cert.owner_id and cert.owner_id == other_cert.owner_id:
        return True
    if (
        cert.organization_id
        and other_cert.organization_id
        and cert.organization_id == other_cert.organization_id
    ):
        return True
    return False


def _describe(other_cert: Optional[Certificate], cert: Certificate, base_message: str) -> str:
    if other_cert is None:
        return base_message
    if not _is_same_owner_or_org(cert, other_cert):
        return f"{base_message}, uploaded by a different account or organization. This is a strong fraud signal."
    return f"{base_message} (previously uploaded by you)."


def _log(cert_id: str, dup_type: str, match_id: Optional[str], conf: float,
         t_start: float, field_sim: float = 0.0, visual_sim: float = 0.0) -> None:
    elapsed = round(time.time() - t_start, 3)
    logger.info(
        "Duplicate | cert=%s | type=%s | match=%s | conf=%.1f | "
        "field_sim=%.1f | visual_sim=%.1f | time=%.3fs",
        cert_id, dup_type, match_id, conf, field_sim, visual_sim, elapsed,
    )
