"""
Unit tests for MODULE 4: Duplicate Detection stage.
Validates:
1. Layer 1 Exact Match (same sha256_hash)
2. Layer 2 Perceptual Match (pHash/dHash Hamming distance on re-saved/re-scanned images)
3. Layer 3 Identity Match (same reg_no / roll_no / cert_no + RapidFuzz student name)
4. Conflict detection (same identifier with conflicting student name)
5. Scope isolation (organization_id scoping and group_id exclusion)
6. Owner distinction (same owner re-upload vs different owner collision)
"""
import uuid
import pytest
import numpy as np
import cv2

from app.models.models import Certificate, OCRData
from app.services.duplicate_detection import (
    detect_duplicates,
    compute_phash_and_dhash_from_array,
    hamming_distance,
    normalize_identity_string,
    EXACT_FILE_DUPLICATE,
    OWN_REUPLOAD,
    DUPLICATE_CERTIFICATE,
    CERTIFICATE_CONFLICT,
)
from app.core.config import settings


def _create_synthetic_cert_image(text: str) -> np.ndarray:
    """Helper to create a synthetic certificate page."""
    img = np.full((500, 400), 255, dtype=np.uint8)
    cv2.putText(img, "STATE BOARD CERTIFICATE", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 2)
    cv2.putText(img, text, (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
    cv2.putText(img, "Registration: REG-99100", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
    return img


def test_normalization_removes_punctuation_and_whitespace():
    assert normalize_identity_string("  Keerthana   K.  ") == "keerthana k"
    assert normalize_identity_string("Reg-No: 99100/A") == "regno 99100a"
    assert normalize_identity_string("CERT# 1234-5678") == "cert 12345678"


def test_perceptual_hash_computation_and_distance():
    img1 = _create_synthetic_cert_image("Student: Keerthana K")
    p1, d1 = compute_phash_and_dhash_from_array(img1)
    assert len(p1) == 16
    assert len(d1) == 16

    # Re-save with JPEG compression & minor noise (simulating scan / photo)
    _, enc = cv2.imencode(".jpg", img1, [cv2.IMWRITE_JPEG_QUALITY, 60])
    img_resaved = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    img_resaved = np.clip(img_resaved.astype(np.int16) + 5, 0, 255).astype(np.uint8)

    p2, d2 = compute_phash_and_dhash_from_array(img_resaved)
    dist_p = hamming_distance(p1, p2)
    dist_d = hamming_distance(d1, d2)

    # Identical content with minor compression noise should have small Hamming distance <= 8
    assert dist_p <= 8, f"pHash distance should be small for re-saved image, got {dist_p}"
    assert dist_d <= 8, f"dHash distance should be small for re-saved image, got {dist_d}"

    # Different certificate
    img_diff = np.full((500, 400), 255, dtype=np.uint8)
    cv2.circle(img_diff, (200, 250), 100, 0, -1)
    p3, d3 = compute_phash_and_dhash_from_array(img_diff)
    dist_diff = min(hamming_distance(p1, p3), hamming_distance(d1, d3))
    assert dist_diff > 12, f"Different images should have high distance, got {dist_diff}"


from app.db.database import AsyncSessionLocal, init_db


@pytest.mark.asyncio
async def test_exact_hash_match_same_owner_vs_different_owner():
    await init_db()
    async with AsyncSessionLocal() as db_session:
        user_a_id = uuid.uuid4().hex
        user_b_id = uuid.uuid4().hex
        org_id = uuid.uuid4().hex
        shared_hash = "a" * 64

        # 1. First uploaded certificate by user A
        cert1 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_a_id,
            original_filename="marksheet.pdf",
            storage_path="path/to/marksheet.pdf",
            file_type="pdf",
            file_size_bytes=1000,
            sha256_hash=shared_hash,
        )
        db_session.add(cert1)
        await db_session.commit()

        # 2. User A uploads the exact same file again (same owner)
        cert2_same_owner = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_a_id,
            original_filename="marksheet_copy.pdf",
            storage_path="path/to/marksheet_copy.pdf",
            file_type="pdf",
            file_size_bytes=1000,
            sha256_hash=shared_hash,
        )
        res_same = await detect_duplicates(cert2_same_owner, None, db_session)
        assert res_same.is_duplicate is True
        assert res_same.match_layer == "EXACT"
        assert res_same.same_owner is True
        assert res_same.owner_distinction == "SAME_OWNER_REUPLOAD"
        assert res_same.duplicate_status == OWN_REUPLOAD
        assert "you previously uploaded" in res_same.match_reason.lower()

        # 3. User B uploads the exact same file (different owner)
        cert3_diff_owner = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_b_id,
            original_filename="marksheet_stolen.pdf",
            storage_path="path/to/marksheet_stolen.pdf",
            file_type="pdf",
            file_size_bytes=1000,
            sha256_hash=shared_hash,
        )
        res_diff = await detect_duplicates(cert3_diff_owner, None, db_session)
        assert res_diff.is_duplicate is True
        assert res_diff.match_layer == "EXACT"
        assert res_diff.same_owner is False
        assert res_diff.owner_distinction == "DIFFERENT_OWNER_DUPLICATE"
        assert res_diff.duplicate_type == EXACT_FILE_DUPLICATE
        assert "another owner" in res_diff.match_reason.lower()


@pytest.mark.asyncio
async def test_identity_match_with_fuzzy_name():
    await init_db()
    async with AsyncSessionLocal() as db_session:
        user_a = uuid.uuid4().hex
        user_b = uuid.uuid4().hex
        org_id = uuid.uuid4().hex

        # Cert 1 with OCR data: Reg No 778899, Name "Keerthana K"
        cert1 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_a,
            original_filename="cert1.pdf",
            storage_path="path/to/cert1.pdf",
            file_type="pdf",
            file_size_bytes=2000,
            sha256_hash="b" * 64,
        )
        db_session.add(cert1)
        ocr1 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert1.id,
            register_number="REG-778899",
            student_name="Keerthana K",
        )
        db_session.add(ocr1)
        await db_session.commit()

        # Cert 2 (uploaded by different owner) with same Reg No and fuzzy name "keerthana k."
        cert2 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_b,
            original_filename="cert2.pdf",
            storage_path="path/to/cert2.pdf",
            file_type="pdf",
            file_size_bytes=3000,
            sha256_hash="c" * 64,  # different hash
        )
        ocr2 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert2.id,
            register_number="REG-778899",
            student_name="keerthana k.",
        )

        res = await detect_duplicates(cert2, ocr2, db_session)
        assert res.is_duplicate is True
        assert res.match_layer == "IDENTITY"
        assert res.registration_number_match is True
        assert res.same_owner is False
        assert res.duplicate_status == DUPLICATE_CERTIFICATE
        assert "matching register number" in res.match_reason.lower()


@pytest.mark.asyncio
async def test_identity_conflict_detection():
    """When same registration number is used but student names conflict severely (<45% match)."""
    await init_db()
    async with AsyncSessionLocal() as db_session:
        user_a = uuid.uuid4().hex
        user_b = uuid.uuid4().hex
        org_id = uuid.uuid4().hex

        cert1 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_a,
            original_filename="cert1.pdf",
            storage_path="path/to/cert1.pdf",
            file_type="pdf",
            file_size_bytes=2000,
            sha256_hash="d" * 64,
        )
        db_session.add(cert1)
        ocr1 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert1.id,
            certificate_number="CERT-445566",
            student_name="Keerthana K",
        )
        db_session.add(ocr1)
        await db_session.commit()

        # Cert 2 has SAME cert number, but completely different student name: "Rizvan Ahmed"
        cert2 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org_id,
            owner_id=user_b,
            original_filename="cert2.pdf",
            storage_path="path/to/cert2.pdf",
            file_type="pdf",
            file_size_bytes=3000,
            sha256_hash="e" * 64,
        )
        ocr2 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert2.id,
            certificate_number="CERT-445566",
            student_name="Rizvan Ahmed",
        )

        res = await detect_duplicates(cert2, ocr2, db_session)
        assert res.is_duplicate is True
        assert res.match_layer == "IDENTITY"
        assert res.duplicate_status == CERTIFICATE_CONFLICT
        assert res.duplicate_type == CERTIFICATE_CONFLICT
        assert "different student" in res.match_reason.lower()


@pytest.mark.asyncio
async def test_organization_scoping_prevents_cross_org_leakage():
    """By default, duplicate check only compares within same organization_id."""
    await init_db()
    async with AsyncSessionLocal() as db_session:
        org1 = uuid.uuid4().hex
        org2 = uuid.uuid4().hex
        shared_hash = "f" * 64

        cert_org1 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org1,
            owner_id=uuid.uuid4().hex,
            original_filename="file.pdf",
            storage_path="path/org1.pdf",
            file_type="pdf",
            file_size_bytes=1000,
            sha256_hash=shared_hash,
        )
        db_session.add(cert_org1)
        await db_session.commit()

        # Cert uploaded to Org 2 with same file hash
        cert_org2 = Certificate(
            id=uuid.uuid4().hex,
            organization_id=org2,
            owner_id=uuid.uuid4().hex,
            original_filename="file.pdf",
            storage_path="path/org2.pdf",
            file_type="pdf",
            file_size_bytes=1000,
            sha256_hash=shared_hash,
        )

        res = await detect_duplicates(cert_org2, None, db_session)
        # Since DUPLICATE_CROSS_ORG_ALLOWED is False by default, cert_org1 should not be matched
        assert res.is_duplicate is False
        assert res.duplicate_status == "NO_DUPLICATE"

