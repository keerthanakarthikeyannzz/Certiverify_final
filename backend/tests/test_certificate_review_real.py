"""
Test Suite: Certificate Review Backend Integration
Validates that review decisions (Confirm Genuine, Mark Suspicious, Mark Fake/Fraudulent)
update actual DB records for the selected certificate_id and persist reviewer notes.
"""
import pytest
import os
import io
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User, Certificate, FinalPrediction, TrustScore
from sqlalchemy import select, update

@pytest.mark.asyncio
async def test_all_three_certificate_review_actions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register and verify user
        import uuid
        from tests.conftest import find_sample_pdf
        rnd = uuid.uuid4().hex[:8]
        email = f"review_user_{rnd}@example.com"
        password = "TestPassword123!"
        await ac.post("/api/v1/auth/register", json={
            "full_name": f"Review User {rnd}",
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

        pdf_path = find_sample_pdf()

        # Upload & run pipeline for a test certificate
        with open(pdf_path, "rb") as f:
            upload_res = await ac.post(
                "/api/v1/certificates/upload",
                files={"files": ("review_target_cert.pdf", f, "application/pdf")},
                headers=headers
            )
        cert_id = upload_res.json()["certificates"][0]["id"]

        await ac.post(f"/api/v1/certificates/{cert_id}/run-pipeline", headers=headers)

        # ── Test Review Action 1: Mark Suspicious ─────────────────────────────
        suspicious_note = "Tamper anomaly observed in seal area during manual review."
        rev1_res = await ac.post(
            f"/api/v1/certificates/{cert_id}/review",
            json={"verdict": "suspicious", "review_note": suspicious_note},
            headers=headers
        )
        assert rev1_res.status_code == 200
        rev1_data = rev1_res.json()
        assert rev1_data["verdict"] == "suspicious"
        assert suspicious_note in rev1_data["explanation"]

        async with AsyncSessionLocal() as session:
            pred1 = (await session.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert_id))).scalars().first()
            ts1 = (await session.execute(select(TrustScore).where(TrustScore.certificate_id == cert_id))).scalars().first()
            assert pred1.label == "suspicious"
            assert suspicious_note in pred1.explanation
            assert ts1.score <= 55.0

        # ── Test Review Action 2: Mark Fake / Fraudulent ─────────────────────
        fake_note = "Confirmed fake certificate after registrar cross-check."
        rev2_res = await ac.post(
            f"/api/v1/certificates/{cert_id}/review",
            json={"verdict": "fake", "review_note": fake_note},
            headers=headers
        )
        assert rev2_res.status_code == 200
        rev2_data = rev2_res.json()
        assert rev2_data["verdict"] == "fake"
        assert fake_note in rev2_data["explanation"]

        async with AsyncSessionLocal() as session:
            pred2 = (await session.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert_id))).scalars().first()
            ts2 = (await session.execute(select(TrustScore).where(TrustScore.certificate_id == cert_id))).scalars().first()
            assert pred2.label == "fake"
            assert fake_note in pred2.explanation
            assert ts2.score == 0.0

        # ── Test Review Action 3: Confirm Genuine ─────────────────────────────
        genuine_note = "Official transcript verified directly with university registrar."
        rev3_res = await ac.post(
            f"/api/v1/certificates/{cert_id}/review",
            json={"verdict": "genuine", "review_note": genuine_note},
            headers=headers
        )
        assert rev3_res.status_code == 200
        rev3_data = rev3_res.json()
        assert rev3_data["verdict"] == "genuine"
        assert genuine_note in rev3_data["explanation"]

        async with AsyncSessionLocal() as session:
            pred3 = (await session.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert_id))).scalars().first()
            ts3 = (await session.execute(select(TrustScore).where(TrustScore.certificate_id == cert_id))).scalars().first()
            assert pred3.label == "genuine"
            assert genuine_note in pred3.explanation
            assert ts3.score >= 90.0
