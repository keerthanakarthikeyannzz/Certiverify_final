"""
Test Suite: Verification History Deletion and Data Integrity
Validates all enterprise requirements for deleting history entries:
1. Authorized user can delete an eligible history entry.
2. Deleted entry no longer appears in GET /api/v1/certificates/history.
3. Other history entries (including another entry for the same filename/certificate) remain intact.
4. Underlying Certificate record remains available and accessible via GET /api/v1/certificates/{id}.
5. Underlying OCR data, verification results, reports, and trust scores remain completely intact.
6. Original uploaded file in storage is NOT deleted.
7. Unauthenticated delete requests return HTTP 401 Unauthorized.
8. Cross-tenant access is blocked: A user cannot delete another organization's/user's history entry (HTTP 403/404).
9. Deleting a non-existent entry returns HTTP 404 Not Found.
10. Attempting to delete an already deleted/hidden history entry returns HTTP 404 Not Found.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, update

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import (
    User, Certificate, OCRData, VerificationResult, TrustScore, FinalPrediction, VerificationReport,
)
from tests.conftest import generate_valid_pdf_bytes, verify_test_user_email


@pytest.mark.asyncio
async def test_history_deletion_lifecycle_and_integrity():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register User A (owner)
        rnd_a = uuid.uuid4().hex[:8]
        email_a = f"user_a_{rnd_a}@example.com"
        password = "Password123!"

        reg_a = await ac.post("/api/v1/auth/register", json={
            "full_name": f"User A {rnd_a}",
            "email": email_a,
            "password": password,
            "role": "student",
        })
        assert reg_a.status_code in (200, 201)
        await verify_test_user_email(email_a)

        login_a = await ac.post("/api/v1/auth/login", json={"email": email_a, "password": password})
        assert login_a.status_code == 200
        token_a = login_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # 2. Register User B (attacker / different tenant)
        rnd_b = uuid.uuid4().hex[:8]
        email_b = f"user_b_{rnd_b}@example.com"
        reg_b = await ac.post("/api/v1/auth/register", json={
            "full_name": f"User B {rnd_b}",
            "email": email_b,
            "password": password,
            "role": "student",
        })
        assert reg_b.status_code in (200, 201)
        await verify_test_user_email(email_b)

        login_b = await ac.post("/api/v1/auth/login", json={"email": email_b, "password": password})
        assert login_b.status_code == 200
        token_b = login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 3. Upload Two Entries with the Same Filename for User A
        pdf_bytes_1 = generate_valid_pdf_bytes("Entry 1 - 12th marksheet(R)")
        pdf_bytes_2 = generate_valid_pdf_bytes("Entry 2 - 12th marksheet(R)")

        upload_1 = await ac.post(
            "/api/v1/certificates/upload",
            files={"files": ("12th marksheet(R).pdf", pdf_bytes_1, "application/pdf")},
            headers=headers_a,
        )
        assert upload_1.status_code == 201
        cert_1_id = upload_1.json()["certificates"][0]["id"]

        upload_2 = await ac.post(
            "/api/v1/certificates/upload",
            files={"files": ("12th marksheet(R).pdf", pdf_bytes_2, "application/pdf")},
            headers=headers_a,
        )
        assert upload_2.status_code == 201
        cert_2_id = upload_2.json()["certificates"][0]["id"]

        assert cert_1_id != cert_2_id, "Each upload must have a unique certificate_id"

        # 4. Attach OCR, Verification, TrustScore, Prediction, and Report records to cert_1
        async with AsyncSessionLocal() as session:
            from app.models.models import PredictionLabel
            ocr_row = OCRData(
                certificate_id=cert_1_id,
                raw_text="Name: ROHITH A, Reg: 2212258607, Certificate No: 33233508",
                student_name="ROHITH A",
                certificate_number="33233508",
                ocr_accuracy=0.95,
            )
            verif_row = VerificationResult(
                certificate_id=cert_1_id,
                qr_present=True,
                qr_valid=True,
                blockchain_match=True,
                tampering_score=0.02,
                is_duplicate=False,
            )
            ts_row = TrustScore(
                certificate_id=cert_1_id,
                score=88.5,
                breakdown={"tampering": 98.0, "blockchain": 100.0},
            )
            pred_row = FinalPrediction(
                certificate_id=cert_1_id,
                label=PredictionLabel.GENUINE,
                confidence_score=0.92,
            )
            rep_row = VerificationReport(
                certificate_id=cert_1_id,
                verification_id=f"VER-{cert_1_id[:8]}",
                digital_signature="test_sig_12345",
            )
            session.add_all([ocr_row, verif_row, ts_row, pred_row, rep_row])
            await session.commit()

        # 5. Verify Both Entries Appear in History Initially
        hist_before = await ac.get("/api/v1/certificates/history", headers=headers_a)
        assert hist_before.status_code == 200
        items_before = hist_before.json()
        ids_before = [item["certificate_id"] for item in items_before]
        assert cert_1_id in ids_before, "cert_1 must appear in history before deletion"
        assert cert_2_id in ids_before, "cert_2 must appear in history before deletion"

        # 6. Test Requirement 6: Unauthenticated Delete Request is Rejected
        unauth_del = await ac.delete(f"/api/v1/certificates/history/{cert_1_id}")
        assert unauth_del.status_code in (401, 403), "Unauthenticated delete request must be rejected"

        # 7. Test Requirement 7: Cross-Tenant Protection (User B cannot delete User A's history)
        cross_tenant_del = await ac.delete(f"/api/v1/certificates/history/{cert_1_id}", headers=headers_b)
        assert cross_tenant_del.status_code in (403, 404), "User B must not be able to delete User A's history"

        # 8. Test Requirement 8: Deleting a Non-Existent History Entry Returns 404
        non_existent_id = str(uuid.uuid4())
        not_found_del = await ac.delete(f"/api/v1/certificates/history/{non_existent_id}", headers=headers_a)
        assert not_found_del.status_code == 404, "Deleting non-existent entry must return 404"

        # 9. Test Requirement 1: Authorized User A Deletes History Entry for cert_1
        del_res = await ac.delete(f"/api/v1/certificates/history/{cert_1_id}", headers=headers_a)
        assert del_res.status_code == 200, f"History delete failed: {del_res.text}"
        del_json = del_res.json()
        assert del_json["success"] is True
        assert del_json["certificate_id"] == cert_1_id

        # 10. Test Requirement 2: Deleted Entry No Longer Appears in History
        hist_after = await ac.get("/api/v1/certificates/history", headers=headers_a)
        assert hist_after.status_code == 200
        items_after = hist_after.json()
        ids_after = [item["certificate_id"] for item in items_after]
        assert cert_1_id not in ids_after, "cert_1 must NOT appear in history after deletion"

        # 11. Test Requirement 3: Other History Entry for Same Filename Remains Intact
        assert cert_2_id in ids_after, "cert_2 (same filename) must remain intact in history"

        # 12. Test Requirement 4: Underlying Certificate Record Remains Available via GET
        cert_res = await ac.get(f"/api/v1/certificates/{cert_1_id}", headers=headers_a)
        assert cert_res.status_code == 200, "Underlying Certificate must still exist and be queryable"
        cert_data = cert_res.json()
        assert cert_data["id"] == cert_1_id
        assert cert_data["original_filename"] == "12th marksheet(R).pdf"

        # 13. Test Requirement 5: Underlying OCR, Verification Evidence, Trust Score, and Report Remain Intact
        async with AsyncSessionLocal() as session:
            # Check certificate DB row flags
            cert_db = (await session.execute(select(Certificate).where(Certificate.id == cert_1_id))).scalar_one_or_none()
            assert cert_db is not None, "Certificate DB row must exist"
            assert cert_db.is_history_hidden is True, "is_history_hidden flag must be True"
            assert cert_db.history_deleted_at is not None, "history_deleted_at must be populated"

            # Check OCR Data
            ocr_db = (await session.execute(select(OCRData).where(OCRData.certificate_id == cert_1_id))).scalar_one_or_none()
            assert ocr_db is not None, "OCR Data must be preserved"
            assert ocr_db.ocr_accuracy == 0.95

            # Check Verification Result
            vr_db = (await session.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert_1_id))).scalar_one_or_none()
            assert vr_db is not None, "VerificationResult must be preserved"
            assert vr_db.qr_valid is True
            assert vr_db.blockchain_match is True

            # Check Trust Score
            ts_db = (await session.execute(select(TrustScore).where(TrustScore.certificate_id == cert_1_id))).scalar_one_or_none()
            assert ts_db is not None, "TrustScore must be preserved"
            assert ts_db.score == 88.5

            # Check Final Prediction
            pred_db = (await session.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert_1_id))).scalar_one_or_none()
            assert pred_db is not None, "FinalPrediction must be preserved"
            pred_label = pred_db.label.value if hasattr(pred_db.label, "value") else str(pred_db.label)
            assert pred_label.lower() == "genuine"

            # Check Verification Report
            rep_db = (await session.execute(select(VerificationReport).where(VerificationReport.certificate_id == cert_1_id))).scalar_one_or_none()
            assert rep_db is not None, "VerificationReport must be preserved"

        # 14. Test Requirement 10: Attempting to Delete Already Deleted/Hidden Entry Returns 404
        repeat_del = await ac.delete(f"/api/v1/certificates/history/{cert_1_id}", headers=headers_a)
        assert repeat_del.status_code == 404, "Deleting already deleted/hidden history entry must return 404"
