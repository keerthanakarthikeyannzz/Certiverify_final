"""
Test Suite: CERTIVERIFY AI — Certificate Pair Comparison Integration
Validates side-by-side comparison between Document A and Document B:
- Uses real certificate_ids from DB (no fake placeholders like CURRENT-UPLOAD-BASELINE)
- Evaluates extracted fields from A and B
- Returns status values: MATCH, MISMATCH, UNKNOWN / NOT DETECTED
- Never automatically treats missing data as MISMATCH
- Generates summary narrative from actual differences
- Does not modify original document reports
"""
import pytest
import os
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User, Certificate, OCRData
from sqlalchemy import select, update

@pytest.mark.asyncio
async def test_certificate_pair_comparison_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register and verify user
        email = "compare_test_user@example.com"
        password = "TestPassword123!"
        await ac.post("/api/v1/auth/register", json={
            "full_name": "Compare Test User",
            "email": email,
            "password": password,
            "role": "verifier"
        })

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(User).where(User.email == email).values(is_email_verified=True)
            )
            await session.commit()

        login_res = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        from tests.conftest import find_sample_pdf
        pdf_path = find_sample_pdf()

        # 2. Upload Document A and run pipeline
        with open(pdf_path, "rb") as f:
            upload_a_res = await ac.post(
                "/api/v1/certificates/upload",
                files={"files": ("doc_a.pdf", f, "application/pdf")},
                headers=headers
            )
        cert_id_a = upload_a_res.json()["certificates"][0]["id"]
        await ac.post(f"/api/v1/certificates/{cert_id_a}/run-pipeline", headers=headers)

        # 3. Upload Document B and run pipeline
        with open(pdf_path, "rb") as f:
            upload_b_res = await ac.post(
                "/api/v1/certificates/upload",
                files={"files": ("doc_b.pdf", f, "application/pdf")},
                headers=headers
            )
        cert_id_b = upload_b_res.json()["certificates"][0]["id"]
        await ac.post(f"/api/v1/certificates/{cert_id_b}/run-pipeline", headers=headers)

        # 4. Execute compare-pair between Document A and Document B
        compare_res = await ac.post(
            "/api/v1/comparisons/compare-pair",
            json={
                "certificate_id_a": cert_id_a,
                "certificate_id_b": cert_id_b,
            },
            headers=headers
        )
        assert compare_res.status_code == 200, f"Compare pair failed: {compare_res.text}"
        data = compare_res.json()

        assert data["certificate_id_a"] == cert_id_a
        assert data["certificate_id_b"] == cert_id_b
        assert data["doc_a_filename"] == "doc_a.pdf"
        assert data["doc_b_filename"] == "doc_b.pdf"
        assert isinstance(data["comparison_rows"], list)
        assert len(data["comparison_rows"]) >= 5

        # Check status values returned
        valid_statuses = {"MATCH", "MISMATCH", "UNKNOWN / NOT DETECTED"}
        for row in data["comparison_rows"]:
            assert row["status"] in valid_statuses, f"Invalid status: {row['status']}"
            # Critical constraint: missing data must NOT be MISMATCH
            if row["doc_a_value"] is None or row["doc_b_value"] is None:
                assert row["status"] == "UNKNOWN / NOT DETECTED", f"Field {row['field_label']} with missing data was falsely marked as {row['status']}"

        assert "summary_narrative" in data
        assert cert_id_a[:8] in data["summary_narrative"] or "doc_a.pdf" in data["summary_narrative"]

        # 5. Test upload-and-compare endpoint with a third file
        with open(pdf_path, "rb") as f:
            upload_compare_res = await ac.post(
                "/api/v1/comparisons/upload-and-compare",
                data={"certificate_id_a": cert_id_a},
                files={"file": ("doc_c.pdf", f, "application/pdf")},
                headers=headers
            )
        assert upload_compare_res.status_code == 200, f"Upload and compare failed: {upload_compare_res.text}"
        data_c = upload_compare_res.json()
        assert data_c["certificate_id_a"] == cert_id_a
        assert data_c["doc_b_filename"] == "doc_c.pdf"
