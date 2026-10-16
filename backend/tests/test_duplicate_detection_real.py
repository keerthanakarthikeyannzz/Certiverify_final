"""
Test Suite: Duplicate Detection Across Documents
Tests exact duplicate detection vs historical documents:
1. Unique document -> returns UNIQUE (is_duplicate=False, type=NO_DUPLICATE)
2. Exact historical duplicate -> returns DUPLICATE (is_duplicate=True, type=EXACT_FILE_DUPLICATE, matches historical cert_id)
3. Different document -> returns UNIQUE or SIMILAR (compared against stored DB records)
"""
import pytest
import io
import json
import hashlib
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def create_sample_doc(text: str = "Unique Document 1") -> bytes:
    """Helper to generate distinct image document bytes with text and visual graphics."""
    doc_img = Image.new("RGB", (800, 1000), color="white")
    draw = ImageDraw.Draw(doc_img)
    draw.text((100, 100), f"CERTIFICATE DOCUMENT: {text}", fill="black")
    
    # Render unique graphic shapes based on text hash to ensure distinct dHash
    h = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
    x1 = 50 + (h % 200)
    y1 = 200 + ((h >> 4) % 200)
    x2 = x1 + 300
    y2 = y1 + 300
    draw.rectangle([x1, y1, x2, y2], fill=((h >> 8) % 255, (h >> 16) % 255, (h >> 24) % 255))

    buf = io.BytesIO()
    doc_img.save(buf, format="PNG")
    return buf.getvalue()

def test_duplicate_detection_flow(client):
    import uuid
    rnd = uuid.uuid4().hex[:8]
    email = f"dup_user_{rnd}@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": "Duplicate Test User",
        "email": email,
        "password": password,
        "role": "student"
    })
    from tests.conftest import verify_test_user_email_sync
    verify_test_user_email_sync(email)
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # ── 1. Upload Unique Document 1 ───────────────────────────────────────────
    doc1_bytes = create_sample_doc(f"Document 1 Payload Alpha {rnd}")
    files1 = {"files": ("unique_doc1.png", io.BytesIO(doc1_bytes), "image/png")}
    upload1 = client.post("/api/v1/certificates/upload", files=files1, headers=headers)
    assert upload1.status_code == 201
    cert1_id = upload1.json()["certificates"][0]["id"]

    dup1_res = client.post(f"/api/v1/certificates/{cert1_id}/verify-duplicate", headers=headers)
    assert dup1_res.status_code == 200
    dup1_data = dup1_res.json()

    # Verify Document 1 is UNIQUE and NOT a duplicate of itself
    assert dup1_data["certificate_id"] == cert1_id
    assert dup1_data["is_duplicate"] is False
    assert dup1_data["duplicate_of_certificate_id"] is None
    detail1 = dup1_data["duplicate_detail"]
    assert detail1["duplicate_status"] == "NO_DUPLICATE"
    assert detail1["duplicate_type"] == "NO_DUPLICATE"

    # ── 2. Upload Exact Historical Duplicate of Document 1 ───────────────────
    files2 = {"files": ("exact_duplicate_doc.png", io.BytesIO(doc1_bytes), "image/png")}
    upload2 = client.post("/api/v1/certificates/upload", files=files2, headers=headers)
    assert upload2.status_code == 201
    cert2_id = upload2.json()["certificates"][0]["id"]
    assert cert2_id != cert1_id

    dup2_res = client.post(f"/api/v1/certificates/{cert2_id}/verify-duplicate", headers=headers)
    assert dup2_res.status_code == 200
    dup2_data = dup2_res.json()

    # Verify Document 2 is detected as an EXACT HISTORICAL DUPLICATE of Document 1
    assert dup2_data["certificate_id"] == cert2_id
    assert dup2_data["is_duplicate"] is True
    assert dup2_data["duplicate_of_certificate_id"] == cert1_id
    detail2 = dup2_data["duplicate_detail"]
    assert detail2["duplicate_type"] == "EXACT_FILE_DUPLICATE"
    assert detail2["file_hash_match"] is True
    assert detail2["matched_certificate_id"] == cert1_id
    assert detail2["duplicate_status"] == "own_reupload"
    assert detail2["same_owner"] is True

    # ── 3. Upload Different Document 3 ─────────────────────────────────────────
    doc3_bytes = create_sample_doc(f"Document 3 Completely Different Beta Spectrum {rnd}")
    files3 = {"files": ("different_doc3.png", io.BytesIO(doc3_bytes), "image/png")}
    upload3 = client.post("/api/v1/certificates/upload", files=files3, headers=headers)
    assert upload3.status_code == 201
    cert3_id = upload3.json()["certificates"][0]["id"]
    assert cert3_id not in (cert1_id, cert2_id)

    dup3_res = client.post(f"/api/v1/certificates/{cert3_id}/verify-duplicate", headers=headers)
    assert dup3_res.status_code == 200
    dup3_data = dup3_res.json()

    # Verify Document 3 is evaluated against stored records and is NOT an exact duplicate of Document 1 or 2
    assert dup3_data["certificate_id"] == cert3_id
    detail3 = dup3_data["duplicate_detail"]
    assert detail3["duplicate_type"] != "EXACT_FILE_DUPLICATE"
    assert dup3_data["duplicate_of_certificate_id"] != cert3_id  # never duplicate of itself


def _register_and_login(client, prefix="user"):
    import uuid
    rnd = uuid.uuid4().hex[:8]
    email = f"{prefix}_{rnd}@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": f"{prefix.capitalize()} User",
        "email": email,
        "password": password,
        "role": "student"
    })
    from tests.conftest import verify_test_user_email_sync
    verify_test_user_email_sync(email)
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_ocr_sync(cert_id: str, register_number: str = None, certificate_number: str = None):
    import sqlite3, uuid
    conn = sqlite3.connect("./test_certiverify.db")
    cur = conn.cursor()
    ocr_id = uuid.uuid4().hex
    cid = cert_id.replace("-", "")
    cur.execute(
        """
        INSERT INTO ocr_data (id, certificate_id, student_name, university_name, register_number, certificate_number, ocr_accuracy)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ocr_id, cid, "Test Student", "Apex Institute", register_number, certificate_number, 0.95),
    )
    conn.commit()
    conn.close()


def test_case_1_own_reupload_informational_only(client):
    """
    Case 1: Same file hash and same owner (re-upload of user's own file).
    -> duplicate_status: 'own_reupload'
    -> Informational only: no penalty, not fraud evidence.
    -> Trust score not capped to 15, verdict genuine, informative reason.
    """
    import uuid
    rnd = uuid.uuid4().hex[:8]
    headers = _register_and_login(client, f"case1_{rnd}")
    doc_bytes = create_sample_doc(f"Case 1 Payload Content Exactly Identical {rnd}")

    # Upload 1
    up1 = client.post("/api/v1/certificates/upload", files={"files": ("file1.png", io.BytesIO(doc_bytes), "image/png")}, headers=headers)
    assert up1.status_code == 201
    cert1_id = up1.json()["certificates"][0]["id"]

    # Upload 2 (exact same file, same user)
    up2 = client.post("/api/v1/certificates/upload", files={"files": ("file1_copy.png", io.BytesIO(doc_bytes), "image/png")}, headers=headers)
    assert up2.status_code == 201
    cert2_id = up2.json()["certificates"][0]["id"]

    # Duplicate detection on 2nd upload
    dup_res = client.post(f"/api/v1/certificates/{cert2_id}/verify-duplicate", headers=headers)
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["is_duplicate"] is True
    detail = dup_data["duplicate_detail"]
    assert detail["duplicate_status"] == "own_reupload"
    assert detail["same_owner"] is True
    assert detail["duplicate_type"] == "EXACT_FILE_DUPLICATE"
    assert "You already uploaded this exact file" in dup_data["duplicate_match_reason"]

    # Compute trust score on 2nd upload: must NOT be capped at 15.0
    ts_res = client.post(f"/api/v1/certificates/{cert2_id}/compute-trust-score", headers=headers)
    assert ts_res.status_code == 200
    ts_data = ts_res.json()
    assert ts_data["score"] >= 80.0
    ev = ts_data["breakdown"].get("evidence_breakdown", {})
    assert ev.get("duplicate", {}).get("status") == "OWN_REUPLOAD"
    assert ev.get("duplicate", {}).get("display_status") == "PASS"

    # Prediction on 2nd upload: genuine verdict
    pred_res = client.post(f"/api/v1/certificates/{cert2_id}/predict", headers=headers)
    assert pred_res.status_code == 200
    pred_data = pred_res.json()
    assert pred_data["label"] == "genuine"
    assert any("You already uploaded this exact file" in r for r in pred_data["reasons"])
    assert "benign re-upload" in pred_data["explanation"]


def test_case_2_different_owner_cross_account_duplicate(client):
    """
    Case 2: Same certificate/register number but a DIFFERENT owner or organization.
    -> Keep as a strong fraud signal.
    -> Trust score capped to <= 15.0, verdict fake.
    """
    import uuid
    rnd = uuid.uuid4().hex[:8]
    headers_a = _register_and_login(client, f"user_a_{rnd}")
    headers_b = _register_and_login(client, f"user_b_{rnd}")

    # User A uploads cert A
    doc_a_bytes = create_sample_doc(f"Document Account A Original Certificate {rnd}")
    up_a = client.post("/api/v1/certificates/upload", files={"files": ("doc_a.png", io.BytesIO(doc_a_bytes), "image/png")}, headers=headers_a)
    assert up_a.status_code == 201
    cert_a_id = up_a.json()["certificates"][0]["id"]
    reg_val = f"REG-CROSS-{rnd}"
    cert_num = f"CERT-CROSS-{rnd}"
    _seed_ocr_sync(cert_a_id, register_number=reg_val, certificate_number=cert_num)

    # User B uploads cert B (different bytes, same register number in OCR)
    doc_b_bytes = create_sample_doc(f"Document Account B Different Content But Same Reg {rnd}")
    up_b = client.post("/api/v1/certificates/upload", files={"files": ("doc_b.png", io.BytesIO(doc_b_bytes), "image/png")}, headers=headers_b)
    assert up_b.status_code == 201
    cert_b_id = up_b.json()["certificates"][0]["id"]
    _seed_ocr_sync(cert_b_id, register_number=reg_val, certificate_number=cert_num)

    # Duplicate check on cert B
    dup_res = client.post(f"/api/v1/certificates/{cert_b_id}/verify-duplicate", headers=headers_b)
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["is_duplicate"] is True
    detail = dup_data["duplicate_detail"]
    assert detail["same_owner"] is False
    assert detail["duplicate_status"] in ("DUPLICATE_CERTIFICATE", "CERTIFICATE_CONFLICT")
    assert "different account or organization" in dup_data["duplicate_match_reason"]

    # Compute trust score on cert B: strong fraud penalty (<= 15.0)
    ts_res = client.post(f"/api/v1/certificates/{cert_b_id}/compute-trust-score", headers=headers_b)
    assert ts_res.status_code == 200
    ts_data = ts_res.json()
    assert ts_data["score"] <= 15.0
    ev = ts_data["breakdown"].get("evidence_breakdown", {})
    assert ev.get("duplicate", {}).get("display_status") == "FAIL"

    # Prediction on cert B: fake verdict
    pred_res = client.post(f"/api/v1/certificates/{cert_b_id}/predict", headers=headers_b)
    assert pred_res.status_code == 200
    pred_data = pred_res.json()
    assert pred_data["label"] == "fake"
    assert any("Duplicate certificate detected" in r for r in pred_data["reasons"])


def test_case_3_same_owner_altered_reupload(client):
    """
    Case 3: Same owner, same register number, but different file content.
    -> Flag as 'suspicious: altered re-upload' (moderate signal).
    -> Trust score capped to moderate ceiling (<= 65.0, not <= 15.0), verdict suspicious.
    """
    import uuid
    rnd = uuid.uuid4().hex[:8]
    headers = _register_and_login(client, f"case3_{rnd}")

    # Upload 1
    doc_1_bytes = create_sample_doc(f"Case 3 Initial Document Content 1 {rnd}")
    up1 = client.post("/api/v1/certificates/upload", files={"files": ("doc1.png", io.BytesIO(doc_1_bytes), "image/png")}, headers=headers)
    assert up1.status_code == 201
    cert1_id = up1.json()["certificates"][0]["id"]
    reg_val = f"REG-ALTER-{rnd}"
    _seed_ocr_sync(cert1_id, register_number=reg_val)

    # Upload 2 (different content, same user, same register number)
    doc_2_bytes = create_sample_doc(f"Case 3 Altered Document Content 2 Completely Different File Bytes {rnd}")
    up2 = client.post("/api/v1/certificates/upload", files={"files": ("doc2.png", io.BytesIO(doc_2_bytes), "image/png")}, headers=headers)
    assert up2.status_code == 201
    cert2_id = up2.json()["certificates"][0]["id"]
    _seed_ocr_sync(cert2_id, register_number=reg_val)

    # Duplicate check on upload 2
    dup_res = client.post(f"/api/v1/certificates/{cert2_id}/verify-duplicate", headers=headers)
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["is_duplicate"] is True
    detail = dup_data["duplicate_detail"]
    assert detail["same_owner"] is True
    assert detail["duplicate_status"] == "suspicious: altered re-upload"
    assert detail["duplicate_type"] == "ALTERED_REUPLOAD"
    assert "altered re-upload" in dup_data["duplicate_match_reason"]

    # Compute trust score on upload 2: moderate ceiling (<= 65.0), NOT fake ceiling (<= 15.0)
    ts_res = client.post(f"/api/v1/certificates/{cert2_id}/compute-trust-score", headers=headers)
    assert ts_res.status_code == 200
    ts_data = ts_res.json()
    assert 15.0 < ts_data["score"] <= 65.0
    ev = ts_data["breakdown"].get("evidence_breakdown", {})
    assert ev.get("duplicate", {}).get("status") == "ALTERED_REUPLOAD"
    assert ev.get("duplicate", {}).get("display_status") == "WARN"

    # Prediction on upload 2: suspicious verdict (NOT fake)
    pred_res = client.post(f"/api/v1/certificates/{cert2_id}/predict", headers=headers)
    assert pred_res.status_code == 200
    pred_data = pred_res.json()
    assert pred_data["label"] == "suspicious"
    assert any("altered re-upload" in r for r in pred_data["reasons"])
