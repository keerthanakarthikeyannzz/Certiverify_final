"""
Test Suite: Real Persisted History Verification
Validates that History functionality uses actual persisted verification records:
- Retrieves certificate_id, filename, document_type, trust_score, prediction, status, timestamp, report_reference.
- Supports multiple completed certificates.
- Isolates Document A results from Document B results (no cross-contamination).
- Employs zero hardcoded fallbacks.
"""
import pytest
import os
import io
import json
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User, Certificate
from sqlalchemy import select, update

@pytest.mark.asyncio
async def test_persisted_history_with_multiple_certificates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register & Verify User
        import uuid
        from tests.conftest import find_sample_pdf
        rnd = uuid.uuid4().hex[:8]
        email = f"history_user_{rnd}@example.com"
        password = "TestPassword123!"
        await ac.post("/api/v1/auth/register", json={
            "full_name": f"History User {rnd}",
            "email": email,
            "password": password,
            "role": "student"
        })

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(User).where(User.email == email).values(is_email_verified=True)
            )
            await session.commit()

        login_res = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        pdf_path = find_sample_pdf()

        # 2. Upload Document A
        with open(pdf_path, "rb") as f:
            upload_a = await ac.post(
                "/api/v1/certificates/upload",
                files={"files": ("doc_a_marksheet.pdf", f, "application/pdf")},
                headers=headers
            )
        assert upload_a.status_code == 201
        cert_a_id = upload_a.json()["certificates"][0]["id"]

        # Run pipeline & generate report for Document A
        pipe_a = await ac.post(f"/api/v1/certificates/{cert_a_id}/run-pipeline", headers=headers)
        assert pipe_a.status_code == 200
        rep_a = await ac.post(f"/api/v1/certificates/{cert_a_id}/generate-report", headers=headers)
        assert rep_a.status_code == 200

        # 3. Upload Document B
        with open(pdf_path, "rb") as f:
            upload_b = await ac.post(
                "/api/v1/certificates/upload",
                files={"files": ("doc_b_degree.pdf", f, "application/pdf")},
                headers=headers
            )
        assert upload_b.status_code == 201
        cert_b_id = upload_b.json()["certificates"][0]["id"]
        assert cert_a_id != cert_b_id, "Certificate IDs must be unique"

        # Run pipeline & generate report for Document B
        pipe_b = await ac.post(f"/api/v1/certificates/{cert_b_id}/run-pipeline", headers=headers)
        assert pipe_b.status_code == 200
        rep_b = await ac.post(f"/api/v1/certificates/{cert_b_id}/generate-report", headers=headers)
        assert rep_b.status_code == 200

        # 4. Query History Endpoint
        hist_res = await ac.get("/api/v1/certificates/history", headers=headers)
        assert hist_res.status_code == 200, f"History fetch failed: {hist_res.text}"
        history = hist_res.json()

        assert len(history) >= 2, "History must return at least the 2 completed certificates"

        # Map items by certificate_id
        history_map = {item["certificate_id"]: item for item in history}
        assert cert_a_id in history_map, "Document A must exist in history"
        assert cert_b_id in history_map, "Document B must exist in history"

        item_a = history_map[cert_a_id]
        item_b = history_map[cert_b_id]

        # 5. Assert actual persisted values and isolation between Document A and Document B
        assert item_a["filename"] == "doc_a_marksheet.pdf"
        assert item_b["filename"] == "doc_b_degree.pdf"

        assert item_a["certificate_id"] == cert_a_id
        assert item_b["certificate_id"] == cert_b_id

        assert item_a["document_type"] is not None
        assert item_b["document_type"] is not None

        assert item_a["trust_score"] is not None
        assert item_b["trust_score"] is not None

        assert item_a["prediction"] in ["genuine", "suspicious", "fake"]
        assert item_b["prediction"] in ["genuine", "suspicious", "fake"]

        assert item_a["status"] == "COMPLETED"
        assert item_b["status"] == "COMPLETED"

        assert item_a["timestamp"] is not None
        assert item_b["timestamp"] is not None

        assert item_a["report_reference"] is not None
        assert item_b["report_reference"] is not None
        assert item_a["report_reference"] != item_b["report_reference"], "Report references must be distinct"

        # Verify Document A result API does not mix with Document B
        res_a = await ac.get(f"/api/v1/certificates/{cert_a_id}/verification-result", headers=headers)
        res_b = await ac.get(f"/api/v1/certificates/{cert_b_id}/verification-result", headers=headers)

        assert res_a.json()["certificate_id"] == cert_a_id
        assert res_b.json()["certificate_id"] == cert_b_id
