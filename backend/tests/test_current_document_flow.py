"""
Test Suite: Current Document Flow & Certificate ID Single Source of Truth
Validates:
1. Certificate ID creation on upload.
2. File association and preview with certificate_id.
3. Subsequent pipeline endpoints using certificate_id.
4. Single document state isolation (old document cannot overwrite current document).
"""
import pytest
import io
import uuid
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_upload_and_certificate_id_flow(client):
    # 1. Register and login test user
    email = f"docflow_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPassword123!"
    reg_res = client.post("/api/v1/auth/register", json={
        "full_name": "Doc Flow User",
        "email": email,
        "password": password,
        "role": "student"
    })
    from tests.conftest import verify_test_user_email_sync, generate_valid_pdf_bytes
    verify_test_user_email_sync(email)
    
    login_res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload Document 1
    file1_content = generate_valid_pdf_bytes("Mock Certificate Content Document 1")
    files1 = {"files": ("cert1.pdf", io.BytesIO(file1_content), "application/pdf")}
    upload1_res = client.post("/api/v1/certificates/upload", files=files1, headers=headers)
    assert upload1_res.status_code == 201
    cert1_data = upload1_res.json()["certificates"][0]
    cert1_id = cert1_data["id"]
    assert cert1_id is not None
    assert cert1_data["original_filename"] == "cert1.pdf"

    # 3. Confirm actual file is associated with cert1_id
    get1_res = client.get(f"/api/v1/certificates/{cert1_id}", headers=headers)
    assert get1_res.status_code == 200
    assert get1_res.json()["id"] == cert1_id

    preview1_res = client.get(f"/api/v1/certificates/{cert1_id}/preview", headers=headers)
    assert preview1_res.status_code == 200
    assert preview1_res.content == file1_content

    # 4. Upload Document 2 (New Current Document)
    file2_content = generate_valid_pdf_bytes("Mock Certificate Content Document 2")
    files2 = {"files": ("cert2.pdf", io.BytesIO(file2_content), "application/pdf")}
    upload2_res = client.post("/api/v1/certificates/upload", files=files2, headers=headers)
    assert upload2_res.status_code == 201
    cert2_data = upload2_res.json()["certificates"][0]
    cert2_id = cert2_data["id"]
    assert cert2_id != cert1_id
    assert cert2_data["original_filename"] == "cert2.pdf"

    # 5. Confirm cert2 file association
    preview2_res = client.get(f"/api/v1/certificates/{cert2_id}/preview", headers=headers)
    assert preview2_res.status_code == 200
    assert preview2_res.content == file2_content

    # 6. Confirm pipeline status endpoint returns exact current cert2_id
    pipeline_res = client.get(f"/api/v1/certificates/{cert2_id}/pipeline", headers=headers)
    assert pipeline_res.status_code == 200
    assert pipeline_res.json()["certificate_id"] == cert2_id
    assert pipeline_res.json()["filename"] == "cert2.pdf"

    # 7. Isolation Check: Document 1 results remain bound to Document 1 and do not pollute Document 2
    pipeline1_res = client.get(f"/api/v1/certificates/{cert1_id}/pipeline", headers=headers)
    assert pipeline1_res.status_code == 200
    assert pipeline1_res.json()["certificate_id"] == cert1_id
    assert pipeline1_res.json()["filename"] == "cert1.pdf"
