import io
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app.main import app
import asyncio
from tests.conftest import verify_test_user_email

def main():
    client = TestClient(app)
    rnd = uuid.uuid4().hex[:8]
    email = f"repro_dup_{rnd}@example.com"
    password = "TestPassword123!"

    # Register & verify test user
    reg = client.post("/api/v1/auth/register", json={
        "full_name": "Repro User",
        "email": email,
        "password": password,
        "role": "student"
    })
    assert reg.status_code == 201, f"Register failed: {reg.text}"
    asyncio.run(verify_test_user_email(email))

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Read sample_certificate.pdf
    with open("sample_certificate.pdf", "rb") as f:
        pdf_bytes = f.read()

    # 1st Upload
    files1 = {"files": ("sample_certificate.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up1 = client.post("/api/v1/certificates/upload", files=files1, headers=headers)
    assert up1.status_code == 201, f"Upload 1 failed: {up1.text}"
    cert1_id = up1.json()["certificates"][0]["id"]
    print(f"Uploaded Cert 1 ID: {cert1_id}")

    # 2nd Upload (same user, identical file)
    files2 = {"files": ("sample_certificate.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up2 = client.post("/api/v1/certificates/upload", files=files2, headers=headers)
    assert up2.status_code == 201, f"Upload 2 failed: {up2.text}"
    cert2_id = up2.json()["certificates"][0]["id"]
    print(f"Uploaded Cert 2 ID: {cert2_id}")

    # Run OCR if needed, or duplicate check directly
    ocr_res = client.post(f"/api/v1/certificates/{cert2_id}/ocr", headers=headers)
    print(f"OCR status code: {ocr_res.status_code}")

    # Run duplicate check
    dup_res = client.post(f"/api/v1/certificates/{cert2_id}/verify-duplicate", headers=headers)
    print(f"Duplicate status code: {dup_res.status_code}")
    dup_data = dup_res.json()
    print("--- DUPLICATE CHECK RESULT ---")
    print(f"is_duplicate: {dup_data.get('is_duplicate')}")
    print(f"duplicate_of_certificate_id: {dup_data.get('duplicate_of_certificate_id')}")
    print(f"duplicate_match_reason: {dup_data.get('duplicate_match_reason')}")
    print(f"duplicate_detail: {dup_data.get('duplicate_detail')}")

    # Run fraud analysis
    fraud_res = client.post(f"/api/v1/certificates/{cert2_id}/fraud-analysis", headers=headers)
    print(f"Fraud analysis status code: {fraud_res.status_code}")
    if fraud_res.status_code == 200:
        print(f"fraud_probability: {fraud_res.json().get('fraud_probability')}")

    # Run trust score
    ts_res = client.post(f"/api/v1/certificates/{cert2_id}/trust-score", headers=headers)
    print(f"Trust score status code: {ts_res.status_code}")
    if ts_res.status_code == 200:
        print(f"trust_score: {ts_res.json().get('trust_score')}")

    # Run prediction
    pred_res = client.post(f"/api/v1/certificates/{cert2_id}/predict", headers=headers)
    print(f"Prediction status code: {pred_res.status_code}")
    if pred_res.status_code == 200:
        pdata = pred_res.json()
        print("--- FINAL PREDICTION RESULT ---")
        print(f"label: {pdata.get('label')}")
        print(f"confidence_score: {pdata.get('confidence_score')}")
        print(f"recommended_action: {pdata.get('recommended_action')}")
        print(f"explanation: {pdata.get('explanation')}")
        print("reasons:")
        for r in pdata.get('reasons', []):
            print(f"  - {r.encode('ascii', 'backslashreplace').decode('ascii')}")

if __name__ == "__main__":
    main()
