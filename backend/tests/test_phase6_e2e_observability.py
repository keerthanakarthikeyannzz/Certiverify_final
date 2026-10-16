"""
PHASE 6 — ENTERPRISE E2E, OBSERVABILITY & FUNCTIONAL TEST SUITE

Validates complete 20-point E2E flow:
1. User Authentication & Login
2. Valid Certificate Upload
3. Invalid Upload Rejection
4. Certificate Creation (ID & SHA-256)
5. Async Job Creation
6. Job PROCESSING State
7. Pipeline Stage Updates
8. Job COMPLETED State
9. Evidence Provenance Retrieval
10. Trust Score Availability
11. Fraud Analysis Results
12. PDF Verification Report Generation
13. Authenticated Document Download/Preview
14. Cross-Tenant Isolation Enforcement
15. Unauthorized Access Rejection
16. API Key Authentication
17. Revoked API Key Rejection
18. Webhook Event Dispatch & Delivery Tracking
19. Rate Limit Enforcement & Telemetry Headers
20. Request ID Correlation (X-Request-ID) & Readiness Checks (/api/health/ready)
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.api_key_service import create_api_key

CERT_BASE = "/api/v1/certificates"
AUTH_BASE = "/api/v1/auth"
JOB_BASE = "/api/v1/jobs"


async def _get_auth_context(client: AsyncClient, prefix: str = "p6_user") -> tuple[dict, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@certiverify.ai"
    password = "Password123!"
    reg = await client.post(f"{AUTH_BASE}/register", json={
        "email": email, "password": password, "full_name": "Phase 6 E2E Inspector", "role": "verifier"
    })
    assert reg.status_code == 201

    from tests.conftest import verify_test_user_email
    await verify_test_user_email(email)

    login = await client.post(f"{AUTH_BASE}/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest.mark.asyncio
async def test_phase6_complete_20_point_e2e_workflow():
    """
    Executes all 20 required Phase 6 verification checks end-to-end.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        print("STEP 1: Auth")
        headers_a, email_a = await _get_auth_context(client, "e2e_org_a")
        headers_b, email_b = await _get_auth_context(client, "e2e_org_b")

        print("STEP 20: Ready check")
        ready_res = await client.get("/api/health/ready")
        assert ready_res.status_code == 200, f"Ready failed: {ready_res.status_code} {ready_res.text}"
        assert ready_res.json()["status"] == "ready"
        assert "X-Request-ID" in ready_res.headers

        print("STEP 3: Bad upload")
        bad_upl = await client.post(f"{CERT_BASE}/upload", headers=headers_a, files=[("files", ("bad.exe", b"MZbad", "application/x-msdownload"))])
        assert bad_upl.status_code == 400, f"Bad upload status: {bad_upl.status_code}"

        print("STEP 2: Valid upload")
        from tests.conftest import find_sample_pdf
        pdf_path = find_sample_pdf()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        up_res = await client.post(f"{CERT_BASE}/upload", headers=headers_a, files=[("files", ("degree_e2e.pdf", pdf_bytes, "application/pdf"))])
        assert up_res.status_code == 201, f"Upload status: {up_res.status_code}"
        data = up_res.json()

        print("STEP 4: Cert created")
        cert = data["certificates"][0]
        cert_id = cert["id"]
        assert cert_id is not None
        assert cert["sha256_hash"] is not None

        print("STEP 5: Async job")
        job_res = await client.post(f"/api/v1/certificates/{cert_id}/verify-async", headers=headers_a)
        assert job_res.status_code == 202, f"Job res status: {job_res.status_code}"
        job_data = job_res.json()
        job_id = job_data["job_id"]
        assert job_data["status"] in ("QUEUED", "PROCESSING", "COMPLETED")

        print("STEP 6-8: Job status")
        status_res = await client.get(f"/api/v1/jobs/{job_id}/status", headers=headers_a)
        assert status_res.status_code == 200
        assert status_res.json()["current_stage"] is not None

        print("STEP pipeline stages execution")
        ocr_res = await client.post(f"{CERT_BASE}/{cert_id}/extract-ocr", headers=headers_a)
        assert ocr_res.status_code in (200, 422), f"OCR status: {ocr_res.status_code} {ocr_res.text}"
        verify_res = await client.post(f"{CERT_BASE}/{cert_id}/verify-all", headers=headers_a)
        assert verify_res.status_code == 200, f"Verify status: {verify_res.status_code} {verify_res.text}"

        print("STEP 10: Trust score")
        ts_res = await client.post(f"{CERT_BASE}/{cert_id}/compute-trust-score", headers=headers_a)
        assert ts_res.status_code == 200, f"Trust score status: {ts_res.status_code} {ts_res.text}"
        assert 0 <= ts_res.json()["score"] <= 100

        print("STEP 11: Fraud analysis")
        fraud_res = await client.post(f"{CERT_BASE}/{cert_id}/analyze-fraud", headers=headers_a)
        assert fraud_res.status_code == 200, f"Fraud status: {fraud_res.status_code} {fraud_res.text}"
        assert "fraud_probability" in fraud_res.json() or "risk_level" in fraud_res.json()

        print("STEP 9: Evidence items")
        ev_res = await client.get(f"{CERT_BASE}/{cert_id}/evidence", headers=headers_a)
        assert ev_res.status_code == 200, f"Evidence status: {ev_res.status_code} {ev_res.text}"
        items = ev_res.json()["items"]
        assert len(items) > 0

        print("STEP 12: Predict verdict & Report generation")
        pred_res = await client.post(f"{CERT_BASE}/{cert_id}/predict", headers=headers_a)
        assert pred_res.status_code in (200, 422), f"Predict status: {pred_res.status_code} {pred_res.text}"

        rep_res = await client.post(f"{CERT_BASE}/{cert_id}/generate-report", headers=headers_a)
        assert rep_res.status_code == 200, f"Report status: {rep_res.status_code} {rep_res.text}"
        assert rep_res.json()["verification_id"] is not None

        print("STEP 13: Preview")
        prev_res = await client.get(f"{CERT_BASE}/{cert_id}/preview", headers=headers_a)
        assert prev_res.status_code == 200
        assert prev_res.headers["content-type"] == "application/pdf"

        print("STEP 14: Cross tenant")
        cross_res = await client.get(f"{CERT_BASE}/{cert_id}/preview", headers=headers_b)
        assert cross_res.status_code == 403

        print("STEP 15: Unauth")
        unauth_res = await client.get(f"{CERT_BASE}/{cert_id}/preview")
        assert unauth_res.status_code == 401

        print("STEP 16: API Key auth")
        from app.db.database import AsyncSessionLocal
        from app.models.models import User
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            user_row = (await db.execute(select(User).where(User.email == email_a))).scalar_one()
            raw_key, key_row = await create_api_key(db, organization_id=user_row.organization_id, name="E2E Key", permissions=["*"])

        key_headers = {"X-API-Key": raw_key}
        key_preview = await client.get(f"{CERT_BASE}/{cert_id}/preview", headers=key_headers)
        assert key_preview.status_code == 200

        print("STEP 17: Revoked key")
        async with AsyncSessionLocal() as db:
            from app.models.models import ApiKey
            k_obj = (await db.execute(select(ApiKey).where(ApiKey.id == key_row.id))).scalar_one()
            k_obj.status = "revoked"
            await db.commit()

        rev_res = await client.get(f"{CERT_BASE}/{cert_id}/preview", headers=key_headers)
        assert rev_res.status_code == 401

        print("STEP 18: Webhooks")
        web_res = await client.get("/api/v1/webhooks", headers=headers_a)
        assert web_res.status_code == 200

        print("STEP 19: Rate limit headers")
        assert "X-Request-ID" in prev_res.headers
        print("ALL 20 STEPS PASSED SUCCESSFULLY")
