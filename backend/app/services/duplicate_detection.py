"""
MODULE 4 - DUPLICATE CERTIFICATE DETECTION & INTEGRITY

Layered matching pipeline (strongest first):
  Layer 1 — Exact: Same sha256_hash (O(1) indexed lookup).
  Layer 2 — Perceptual: pHash (DCT-based) and dHash (gradient-based) of the rendered first page,
            compared by Hamming distance with configurable threshold (DUPLICATE_PERCEPTUAL_MAX_DISTANCE).
            Hashes are cached in verification_results.duplicate_detail to avoid re-reading disk.
  Layer 3 — Identity: Same register_number / roll_number / certificate_number combined with a
            fuzzy student name match from ocr_data (RapidFuzz token_sort_ratio >= DUPLICATE_FUZZY_NAME_THRESHOLD).
            Normalized for case, spacing, and punctuation.
            Also flags CERTIFICATE_CONFLICT if identical registration number is registered under a conflicting name.
  Layer 4 — QR Payload: Identical QR code payload match.
  Layer 5 — Fuzzy Field Similarity: Multi-field fallback comparison across identity attributes.

Scope & Security Controls:
  - Default comparison is scoped to the same organization_id (DUPLICATE_CROSS_ORG_ALLOWED=false).
  - Always excludes the certificate itself (Certificate.id != cert.id).
  - Configurable exclusion of certificates in the same upload group_id (DUPLICATE_EXCLUDE_SAME_GROUP=false).
  - Explicit owner distinction: same owner re-upload vs different owner collision (recorded in detail and reason).
  - Efficient DB queries: queries targeted indexed fields first instead of loading all certificates into memory.
"""
from __future__ import annotations

import io
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Any

import cv2
import numpy as np
from PIL import Image
from rapidfuzz import fuzz

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Certificate, OCRData, VerificationResult
from app.core.config import settings

logger = logging.getLogger("certiverify.duplicate")

# ---------------------------------------------------------------------------
# Duplicate category constants
# ---------------------------------------------------------------------------
NO_DUPLICATE                = "NO_DUPLICATE"
EXACT_FILE_DUPLICATE        = "EXACT_FILE_DUPLICATE"
DUPLICATE_UPLOAD            = "DUPLICATE_UPLOAD"
DUPLICATE_CERTIFICATE       = "DUPLICATE_CERTIFICATE"
POSSIBLE_DUPLICATE          = "POSSIBLE_DUPLICATE"
CERTIFICATE_CONFLICT        = "CERTIFICATE_CONFLICT"
QR_DUPLICATE                = "QR_DUPLICATE"
OWN_REUPLOAD                = "own_reupload"
SUSPICIOUS_ALTERED_REUPLOAD = "suspicious: altered re-upload"

# Fields used for identity comparison
_IDENTITY_FIELDS = [
    "student_name",
    "university_name",
    "certificate_number",
    "register_number",
    "roll_number",
    "course",
    "department",
]

_CONFLICT_SENSITIVE_FIELDS = {"student_name", "university_name"}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DuplicateCheckResult:
    # ── Original fields (backward-compatible) ───────────────────────────────
    is_duplicate: bool
    duplicate_of_certificate_id: Optional[str]
    match_reason: Optional[str]

    # ── Additive structured fields (Module 4 spec) ──────────────────────────
    duplicate_type: str = NO_DUPLICATE
    duplicate_status: str = NO_DUPLICATE
    confidence: float = 0.0
    matched_fields: list[str] = field(default_factory=list)
    conflicting_fields: list[str] = field(default_factory=list)
    field_similarity: float = 0.0
    visual_similarity: float = 0.0
    same_owner: bool = False
    owner_distinction: str = "NO_DUPLICATE"   # SAME_OWNER_REUPLOAD | DIFFERENT_OWNER_DUPLICATE | NO_DUPLICATE
    match_layer: str = "NONE"                 # EXACT | PERCEPTUAL | IDENTITY | QR | FUZZY | NONE

    current_owner_id: Optional[str] = None
    matched_owner_id: Optional[str] = None
    current_org_id: Optional[str] = None
    matched_org_id: Optional[str] = None

    # Detail flags
    file_hash_match: bool = False
    perceptual_hash_match: bool = False
    certificate_number_match: bool = False
    registration_number_match: bool = False
    qr_match: bool = False

    perceptual_hashes: dict[str, str] = field(default_factory=dict)

    def to_detail_dict(self) -> dict[str, Any]:
        """Serialize to the duplicate_detail JSON column format."""
        return {
            "duplicate_status":           self.duplicate_status,
            "duplicate_type":             self.duplicate_type,
            "duplicate_detected":         self.is_duplicate,
            "confidence":                 round(self.confidence, 1),
            "matched_certificate_id":     self.duplicate_of_certificate_id,
            "match_layer":                self.match_layer,
            "same_owner":                 self.same_owner,
            "owner_distinction":          self.owner_distinction,
            "current_owner_id":           self.current_owner_id,
            "matched_owner_id":           self.matched_owner_id,
            "current_org_id":             self.current_org_id,
            "matched_org_id":             self.matched_org_id,
            "matched_fields":             self.matched_fields,
            "conflicting_fields":         self.conflicting_fields,
            "file_hash_match":            self.file_hash_match,
            "perceptual_hash_match":      self.perceptual_hash_match,
            "certificate_number_match":   self.certificate_number_match,
            "registration_number_match":  self.registration_number_match,
            "qr_match":                   self.qr_match,
            "field_similarity":           round(self.field_similarity, 1),
            "visual_similarity":          round(self.visual_similarity, 1),
            "perceptual_hashes":          self.perceptual_hashes,
            "reason":                     self.match_reason or "No matching certificate record found in registry.",
        }


# ---------------------------------------------------------------------------
# Perceptual Hashing Utilities (pHash & dHash)
# ---------------------------------------------------------------------------

def compute_phash_and_dhash_from_array(img_array: np.ndarray, hash_size: int = 8) -> tuple[str, str]:
    """
    Computes both pHash (DCT-based perceptual hash) and dHash (difference gradient hash)
    from a BGR or grayscale numpy image array.
    Returns 16-character hexadecimal strings (64-bit hashes).
    """
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_array

    # 1. dHash (Difference Hash)
    resized_d = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff_d = resized_d[:, 1:] > resized_d[:, :-1]
    bits_d = diff_d.flatten()
    val_d = sum(int(b) << i for i, b in enumerate(bits_d))
    dhash_hex = f"{val_d:016x}"

    # 2. pHash (DCT-based Perceptual Hash)
    img_size = hash_size * 4  # 32x32
    resized_p = cv2.resize(gray, (img_size, img_size), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(resized_p))
    dct_low = dct[:hash_size, :hash_size]
    med = float(np.median(dct_low))
    diff_p = dct_low > med
    bits_p = diff_p.flatten()
    val_p = sum(int(b) << i for i, b in enumerate(bits_p))
    phash_hex = f"{val_p:016x}"

    return phash_hex, dhash_hex


def hamming_distance(hex1: Optional[str], hex2: Optional[str]) -> int:
    """Computes bitwise Hamming distance between two 16-char hex strings."""
    if not hex1 or not hex2:
        return 64
    try:
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        return bin(val1 ^ val2).count("1")
    except Exception:
        return 64


# ---------------------------------------------------------------------------
# Normalization Helper
# ---------------------------------------------------------------------------

def normalize_identity_string(val: Optional[str]) -> str:
    """
    Normalizes registration numbers, certificate numbers, and student names:
    - Lowercase
    - Strip leading/trailing spaces
    - Remove punctuation and symbols
    - Collapse multiple spaces into single space
    """
    if not val:
        return ""
    s = val.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Main Detection Pipeline (Layered, Strongest First)
# ---------------------------------------------------------------------------

async def detect_duplicates(
    cert: Certificate,
    ocr_row: Optional[OCRData],
    db: AsyncSession,
    file_bytes: Optional[bytes] = None,
) -> DuplicateCheckResult:
    """
    Layered duplicate detection (Module 4):
    1. Exact SHA-256 hash
    2. Perceptual hash (pHash/dHash) of rendered first page
    3. Identity match: reg_no / roll_no / cert_no + RapidFuzz student name match
    4. QR code payload match
    5. Fallback multi-field fuzzy similarity
    """
    t_start = time.time()
    cross_org = getattr(settings, "DUPLICATE_CROSS_ORG_ALLOWED", False)
    exclude_same_group = getattr(settings, "DUPLICATE_EXCLUDE_SAME_GROUP", False)
    perceptual_max_dist = int(getattr(settings, "DUPLICATE_PERCEPTUAL_MAX_DISTANCE", 10))
    fuzzy_name_thresh = float(getattr(settings, "DUPLICATE_FUZZY_NAME_THRESHOLD", 85.0))
    fuzzy_field_thresh = float(getattr(settings, "DUPLICATE_FUZZY_FIELD_THRESHOLD", 85.0))

    # Pre-compute or read current certificate perceptual hash
    curr_phash, curr_dhash = await _compute_or_load_hashes(cert, file_bytes)
    curr_hashes = {"phash": curr_phash, "dhash": curr_dhash} if curr_phash and curr_dhash else {}

    # =========================================================================
    # LAYER 1: Exact File Hash (SHA-256) — Strongest, O(1) indexed
    # =========================================================================
    stmt_exact = select(Certificate).where(
        Certificate.sha256_hash == cert.sha256_hash,
        Certificate.id != cert.id,
    )
    if not cross_org and cert.organization_id:
        stmt_exact = stmt_exact.where(Certificate.organization_id == cert.organization_id)
    if exclude_same_group and cert.group_id:
        stmt_exact = stmt_exact.where(Certificate.group_id != cert.group_id)

    res_exact = await db.execute(stmt_exact)
    matching_exact_certs = res_exact.scalars().all()

    if matching_exact_certs:
        same_owner_cert = next((c for c in matching_exact_certs if _is_same_owner(cert, c)), None)
        other_cert = same_owner_cert or matching_exact_certs[0]
        same_owner = _is_same_owner(cert, other_cert)

        if same_owner:
            status = OWN_REUPLOAD
            dup_type = EXACT_FILE_DUPLICATE
            owner_dist = "SAME_OWNER_REUPLOAD"
            reason = "Exact file duplicate: you previously uploaded this identical file."
        else:
            status = EXACT_FILE_DUPLICATE
            dup_type = EXACT_FILE_DUPLICATE
            owner_dist = "DIFFERENT_OWNER_DUPLICATE"
            reason = (
                f"Exact file duplicate: this identical document was previously uploaded by another owner "
                f"({other_cert.id[:8]}...). Strong fraud signal."
            )

        _log(cert.id, "EXACT", other_cert.id, 100.0, t_start)
        return DuplicateCheckResult(
            is_duplicate=True,
            duplicate_of_certificate_id=other_cert.id,
            match_reason=reason[:255],
            duplicate_type=dup_type,
            duplicate_status=status,
            confidence=100.0,
            match_layer="EXACT",
            matched_fields=["sha256_hash"],
            file_hash_match=True,
            same_owner=same_owner,
            owner_distinction=owner_dist,
            current_owner_id=cert.owner_id,
            matched_owner_id=other_cert.owner_id,
            current_org_id=cert.organization_id,
            matched_org_id=other_cert.organization_id,
            perceptual_hashes=curr_hashes,
        )

    # =========================================================================
    # LAYER 2: Perceptual Hash (pHash / dHash) of Rendered First Page
    # =========================================================================
    if curr_phash and curr_dhash:
        stmt_cand = (
            select(
                Certificate.id,
                Certificate.owner_id,
                Certificate.organization_id,
                Certificate.storage_path,
                Certificate.file_type,
                VerificationResult.duplicate_detail,
            )
            .outerjoin(VerificationResult, VerificationResult.certificate_id == Certificate.id)
            .where(Certificate.id != cert.id)
        )
        if not cross_org and cert.organization_id:
            stmt_cand = stmt_cand.where(Certificate.organization_id == cert.organization_id)
        if exclude_same_group and cert.group_id:
            stmt_cand = stmt_cand.where(Certificate.group_id != cert.group_id)

        cand_rows = (await db.execute(stmt_cand)).all()

        best_cand_id: Optional[str] = None
        best_cand_owner_id: Optional[str] = None
        best_cand_org_id: Optional[str] = None
        best_dist = 999

        for row in cand_rows:
            c_id, c_owner, c_org, c_path, c_type, c_detail = row
            cand_p, cand_d = None, None

            # 1. Read cached perceptual hashes from duplicate_detail JSON (no disk I/O)
            if isinstance(c_detail, dict) and "perceptual_hashes" in c_detail:
                cached = c_detail["perceptual_hashes"]
                if isinstance(cached, dict):
                    cand_p = cached.get("phash")
                    cand_d = cached.get("dhash")

            # 2. If not cached, compute on the fly
            if not cand_p or not cand_d:
                try:
                    cand_p, cand_d = await _compute_file_hashes_from_storage(c_path, c_type)
                except Exception:
                    pass

            if cand_p and cand_d:
                d_p = hamming_distance(curr_phash, cand_p)
                d_d = hamming_distance(curr_dhash, cand_d)
                effective_dist = max(d_p, d_d)
                if effective_dist < best_dist:
                    best_dist = effective_dist
                    best_cand_id = c_id
                    best_cand_owner_id = c_owner
                    best_cand_org_id = c_org

        if best_cand_id and best_dist <= perceptual_max_dist:
            same_owner = bool(cert.owner_id and best_cand_owner_id and cert.owner_id == best_cand_owner_id)
            vis_sim = round(max(0.0, 100.0 * (1.0 - best_dist / 64.0)), 1)
            confidence = round(max(80.0, 100.0 - (best_dist * 2.0)), 1)

            if same_owner:
                status = OWN_REUPLOAD
                dup_type = "PERCEPTUAL_DUPLICATE_OWN"
                owner_dist = "SAME_OWNER_REUPLOAD"
                reason = (
                    f"Perceptual visual match (distance {best_dist}/64): re-saved or re-scanned version of "
                    f"your previous upload ({best_cand_id[:8]}...)."
                )
            else:
                status = DUPLICATE_CERTIFICATE
                dup_type = "PERCEPTUAL_DUPLICATE_DIFFERENT_OWNER"
                owner_dist = "DIFFERENT_OWNER_DUPLICATE"
                reason = (
                    f"Perceptual visual match (distance {best_dist}/64): visually identical to a document "
                    f"uploaded by another owner ({best_cand_id[:8]}...). Strong fraud signal."
                )

            _log(cert.id, "PERCEPTUAL", best_cand_id, confidence, t_start, visual_sim=vis_sim)
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_of_certificate_id=best_cand_id,
                match_reason=reason[:255],
                duplicate_type=dup_type,
                duplicate_status=status,
                confidence=confidence,
                match_layer="PERCEPTUAL",
                matched_fields=["perceptual_hash"],
                perceptual_hash_match=True,
                visual_similarity=vis_sim,
                same_owner=same_owner,
                owner_distinction=owner_dist,
                current_owner_id=cert.owner_id,
                matched_owner_id=best_cand_owner_id,
                current_org_id=cert.organization_id,
                matched_org_id=best_cand_org_id,
                perceptual_hashes=curr_hashes,
            )

    # If OCR data is absent, we cannot proceed with identity/QR/fuzzy layers
    if ocr_row is None:
        _log(cert.id, NO_DUPLICATE, None, 0.0, t_start)
        return DuplicateCheckResult(
            is_duplicate=False,
            duplicate_of_certificate_id=None,
            match_reason="No matching certificate record found in registry.",
            duplicate_type=NO_DUPLICATE,
            duplicate_status=NO_DUPLICATE,
            perceptual_hashes=curr_hashes,
        )

    # =========================================================================
    # LAYER 3: Identity Match (Identifier + Fuzzy Name Match)
    # =========================================================================
    curr_name_norm = normalize_identity_string(ocr_row.student_name)

    identifiers = []
    if ocr_row.certificate_number:
        identifiers.append((OCRData.certificate_number, ocr_row.certificate_number, "certificate_number", "Certificate Number"))
    if ocr_row.register_number:
        identifiers.append((OCRData.register_number, ocr_row.register_number, "register_number", "Register Number"))
    if ocr_row.roll_number:
        identifiers.append((OCRData.roll_number, ocr_row.roll_number, "roll_number", "Roll Number"))

    for col, raw_val, field_name, field_title in identifiers:
        id_stmt = (
            select(OCRData, Certificate)
            .join(Certificate, OCRData.certificate_id == Certificate.id)
            .where(col == raw_val, Certificate.id != cert.id)
        )
        if not cross_org and cert.organization_id:
            id_stmt = id_stmt.where(Certificate.organization_id == cert.organization_id)
        if exclude_same_group and cert.group_id:
            id_stmt = id_stmt.where(Certificate.group_id != cert.group_id)

        matching_records = (await db.execute(id_stmt)).all()
        if not matching_records:
            continue

        for other_ocr, other_cert in matching_records:
            cand_name_norm = normalize_identity_string(other_ocr.student_name)
            name_sim = float(fuzz.token_sort_ratio(curr_name_norm, cand_name_norm)) if (curr_name_norm and cand_name_norm) else 0.0
            same_owner = _is_same_owner(cert, other_cert)

            # Case A: Same identifier AND matching student name
            if name_sim >= fuzzy_name_thresh:
                if same_owner:
                    status = SUSPICIOUS_ALTERED_REUPLOAD
                    dup_type = "IDENTITY_DUPLICATE_OWN"
                    owner_dist = "SAME_OWNER_REUPLOAD"
                    reason = (
                        f"Identity duplicate (same owner): matching {field_title.lower()} '{raw_val}' and "
                        f"student name '{other_ocr.student_name}' ({name_sim:.0f}% match) previously uploaded by you."
                    )
                    confidence = 88.0
                else:
                    status = DUPLICATE_CERTIFICATE
                    dup_type = "IDENTITY_DUPLICATE_DIFFERENT_OWNER"
                    owner_dist = "DIFFERENT_OWNER_DUPLICATE"
                    reason = (
                        f"Identity duplicate (different owner): matching {field_title.lower()} '{raw_val}' and "
                        f"student name '{other_ocr.student_name}' ({name_sim:.0f}% match) previously uploaded by another owner. Strong fraud signal."
                    )
                    confidence = 94.0

                _log(cert.id, "IDENTITY", other_cert.id, confidence, t_start)
                return DuplicateCheckResult(
                    is_duplicate=True,
                    duplicate_of_certificate_id=other_cert.id,
                    match_reason=reason[:255],
                    duplicate_type=dup_type,
                    duplicate_status=status,
                    confidence=confidence,
                    match_layer="IDENTITY",
                    matched_fields=[field_name, "student_name"],
                    certificate_number_match=(field_name == "certificate_number"),
                    registration_number_match=(field_name in ("register_number", "roll_number")),
                    field_similarity=name_sim,
                    same_owner=same_owner,
                    owner_distinction=owner_dist,
                    current_owner_id=cert.owner_id,
                    matched_owner_id=other_cert.owner_id,
                    current_org_id=cert.organization_id,
                    matched_org_id=other_cert.organization_id,
                    perceptual_hashes=curr_hashes,
                )

            # Case B: Same identifier BUT conflicting student name (< 45% match)
            elif name_sim < 45.0 and curr_name_norm and cand_name_norm:
                status = CERTIFICATE_CONFLICT
                dup_type = CERTIFICATE_CONFLICT
                owner_dist = "DIFFERENT_OWNER_DUPLICATE" if not same_owner else "SAME_OWNER_REUPLOAD"
                reason = (
                    f"Identity conflict: same {field_title.lower()} '{raw_val}' is registered to a "
                    f"different student '{other_ocr.student_name}' (vs '{ocr_row.student_name}'). Strong forgery/conflict indicator."
                )
                confidence = 92.0

                _log(cert.id, "IDENTITY_CONFLICT", other_cert.id, confidence, t_start)
                return DuplicateCheckResult(
                    is_duplicate=True,
                    duplicate_of_certificate_id=other_cert.id,
                    match_reason=reason[:255],
                    duplicate_type=dup_type,
                    duplicate_status=status,
                    confidence=confidence,
                    match_layer="IDENTITY",
                    matched_fields=[field_name],
                    conflicting_fields=["student_name"],
                    certificate_number_match=(field_name == "certificate_number"),
                    registration_number_match=(field_name in ("register_number", "roll_number")),
                    same_owner=same_owner,
                    owner_distinction=owner_dist,
                    current_owner_id=cert.owner_id,
                    matched_owner_id=other_cert.owner_id,
                    current_org_id=cert.organization_id,
                    matched_org_id=other_cert.organization_id,
                    perceptual_hashes=curr_hashes,
                )

    # =========================================================================
    # LAYER 4: QR Payload Duplicate
    # =========================================================================
    if ocr_row.qr_code_data:
        qr_stmt = (
            select(OCRData, Certificate)
            .join(Certificate, OCRData.certificate_id == Certificate.id)
            .where(OCRData.qr_code_data == ocr_row.qr_code_data, Certificate.id != cert.id)
        )
        if not cross_org and cert.organization_id:
            qr_stmt = qr_stmt.where(Certificate.organization_id == cert.organization_id)
        if exclude_same_group and cert.group_id:
            qr_stmt = qr_stmt.where(Certificate.group_id != cert.group_id)

        qr_matches = (await db.execute(qr_stmt)).all()
        if qr_matches:
            other_ocr, other_cert = qr_matches[0]
            same_owner = _is_same_owner(cert, other_cert)
            if same_owner:
                status = SUSPICIOUS_ALTERED_REUPLOAD
                dup_type = "ALTERED_REUPLOAD"
                owner_dist = "SAME_OWNER_REUPLOAD"
                reason = "Suspicious: altered re-upload — identical QR payload reused with different file content."
                confidence = 85.0
            else:
                status = QR_DUPLICATE
                dup_type = QR_DUPLICATE
                owner_dist = "DIFFERENT_OWNER_DUPLICATE"
                reason = "This QR code has already been registered on a certificate from a different owner. Strong fraud signal."
                confidence = 99.0

            _log(cert.id, "QR", other_cert.id, confidence, t_start)
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_of_certificate_id=other_cert.id,
                match_reason=reason[:255],
                duplicate_type=dup_type,
                duplicate_status=status,
                confidence=confidence,
                match_layer="QR",
                matched_fields=["qr_code_data"],
                qr_match=True,
                same_owner=same_owner,
                owner_distinction=owner_dist,
                current_owner_id=cert.owner_id,
                matched_owner_id=other_cert.owner_id,
                current_org_id=cert.organization_id,
                matched_org_id=other_cert.organization_id,
                perceptual_hashes=curr_hashes,
            )

    # =========================================================================
    # LAYER 5: Fallback Multi-Field Fuzzy Search
    # =========================================================================
    ocr_fields = _extract_ocr_fields(ocr_row)
    fuzzy_match = await _scoped_fuzzy_field_search(
        db, cert, ocr_fields, cross_org=cross_org, exclude_same_group=exclude_same_group, threshold=fuzzy_field_thresh
    )
    if fuzzy_match:
        other_ocr, field_sim, matched, conflicting = fuzzy_match
        other_cert = await _load_certificate(db, other_ocr.certificate_id)
        same_owner = _is_same_owner(cert, other_cert) if other_cert else False

        if same_owner:
            status = SUSPICIOUS_ALTERED_REUPLOAD
            dup_type = "ALTERED_REUPLOAD"
            owner_dist = "SAME_OWNER_REUPLOAD"
            reason = (
                f"Suspicious: altered re-upload — high similarity ({field_sim:.0f}%) with your previous "
                f"upload {other_ocr.certificate_id[:8]}..., but different file content."
            )
        else:
            status = POSSIBLE_DUPLICATE
            dup_type = POSSIBLE_DUPLICATE
            owner_dist = "DIFFERENT_OWNER_DUPLICATE"
            reason = (
                f"High field similarity ({field_sim:.0f}%) with certificate from another owner "
                f"{other_ocr.certificate_id[:8]}... — matched: {', '.join(matched[:3])}. Strong fraud signal."
            )

        confidence = round(min(field_sim, 95.0), 1)
        _log(cert.id, "FUZZY", other_ocr.certificate_id, confidence, t_start, field_sim=field_sim)
        return DuplicateCheckResult(
            is_duplicate=True,
            duplicate_of_certificate_id=other_ocr.certificate_id,
            match_reason=reason[:255],
            duplicate_type=dup_type,
            duplicate_status=status,
            confidence=confidence,
            match_layer="FUZZY",
            matched_fields=matched,
            conflicting_fields=conflicting,
            field_similarity=field_sim,
            same_owner=same_owner,
            owner_distinction=owner_dist,
            current_owner_id=cert.owner_id,
            matched_owner_id=other_cert.owner_id if other_cert else None,
            current_org_id=cert.organization_id,
            matched_org_id=other_cert.organization_id if other_cert else None,
            perceptual_hashes=curr_hashes,
        )

    # No duplicate found
    _log(cert.id, NO_DUPLICATE, None, 0.0, t_start)
    return DuplicateCheckResult(
        is_duplicate=False,
        duplicate_of_certificate_id=None,
        match_reason="No matching certificate record found in registry.",
        duplicate_type=NO_DUPLICATE,
        duplicate_status=NO_DUPLICATE,
        confidence=0.0,
        match_layer="NONE",
        owner_distinction="NO_DUPLICATE",
        current_owner_id=cert.owner_id,
        current_org_id=cert.organization_id,
        perceptual_hashes=curr_hashes,
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

async def _compute_or_load_hashes(cert: Certificate, file_bytes: Optional[bytes]) -> tuple[Optional[str], Optional[str]]:
    """Compute perceptual hashes for cert from given bytes or storage."""
    try:
        from app.services.image_preprocessing import load_image_as_array
        if file_bytes is None and cert.storage_path:
            from app.services.storage_service import get_storage_backend
            storage = get_storage_backend()
            file_bytes = await storage.read(cert.storage_path)

        if file_bytes:
            arr = load_image_as_array(file_bytes, cert.file_type)
            return compute_phash_and_dhash_from_array(arr)
    except Exception as e:
        logger.debug("Could not compute perceptual hashes for cert %s: %s", cert.id, e)
    return None, None


async def _compute_file_hashes_from_storage(storage_path: str, file_type: str) -> tuple[Optional[str], Optional[str]]:
    """Reads file bytes from storage and computes pHash & dHash."""
    try:
        from app.services.storage_service import get_storage_backend
        from app.services.image_preprocessing import load_image_as_array
        storage = get_storage_backend()
        b = await storage.read(storage_path)
        arr = load_image_as_array(b, file_type)
        return compute_phash_and_dhash_from_array(arr)
    except Exception:
        return None, None


def _is_same_owner(cert: Certificate, other_cert: Optional[Certificate]) -> bool:
    """Checks if two certificates share the same owner_id (robust to hyphenated vs hex UUID strings)."""
    if other_cert is None:
        return False
    o1 = str(cert.owner_id).replace("-", "").lower() if cert.owner_id else ""
    o2 = str(other_cert.owner_id).replace("-", "").lower() if other_cert.owner_id else ""
    return bool(o1 and o2 and o1 == o2)


def _is_same_org(cert: Certificate, other_cert: Optional[Certificate]) -> bool:
    """Checks if two certificates share the same organization_id (robust to hyphenated vs hex UUID strings)."""
    if other_cert is None:
        return False
    org1 = str(cert.organization_id).replace("-", "").lower() if cert.organization_id else ""
    org2 = str(other_cert.organization_id).replace("-", "").lower() if other_cert.organization_id else ""
    return bool(org1 and org2 and org1 == org2)


def _extract_ocr_fields(ocr_row: OCRData) -> dict:
    return {f: getattr(ocr_row, f, None) for f in _IDENTITY_FIELDS}


async def _scoped_fuzzy_field_search(
    db: AsyncSession,
    cert: Certificate,
    ocr_fields: dict,
    cross_org: bool,
    exclude_same_group: bool,
    threshold: float,
) -> Optional[tuple[OCRData, float, list, list]]:
    """Scoped fuzzy comparison across other OCRData records."""
    if not any(v for v in ocr_fields.values() if v):
        return None

    stmt = (
        select(OCRData)
        .join(Certificate, OCRData.certificate_id == Certificate.id)
        .where(OCRData.certificate_id != cert.id)
    )
    if not cross_org and cert.organization_id:
        stmt = stmt.where(Certificate.organization_id == cert.organization_id)
    if exclude_same_group and cert.group_id:
        stmt = stmt.where(Certificate.group_id != cert.group_id)

    all_others = (await db.execute(stmt)).scalars().all()

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

    if best_match and best_sim >= threshold:
        return best_match, best_sim, best_matched, best_conflicting
    return None


def _compute_field_similarity(fields_a: dict, fields_b: dict) -> tuple[float, list, list]:
    """Returns (overall_similarity_pct, matched_fields, conflicting_fields)."""
    scores: list[float] = []
    matched: list[str] = []
    conflicting: list[str] = []

    for fname in _IDENTITY_FIELDS:
        va = normalize_identity_string(fields_a.get(fname))
        vb = normalize_identity_string(fields_b.get(fname))
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


async def _load_certificate(db: AsyncSession, certificate_id: str) -> Optional[Certificate]:
    result = await db.execute(select(Certificate).where(Certificate.id == certificate_id))
    return result.scalar_one_or_none()


def _log(cert_id: str, layer: str, match_id: Optional[str], conf: float,
         t_start: float, field_sim: float = 0.0, visual_sim: float = 0.0) -> None:
    elapsed = round(time.time() - t_start, 3)
    logger.info(
        "Duplicate | cert=%s | layer=%s | match=%s | conf=%.1f | "
        "field_sim=%.1f | visual_sim=%.1f | time=%.3fs",
        cert_id, layer, match_id, conf, field_sim, visual_sim, elapsed,
    )
