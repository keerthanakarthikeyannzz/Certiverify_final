import pytest
import io
import os
from PIL import Image, ImageDraw
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User

def _create_sample_image(text_content: str) -> bytes:
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), text_content, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

@pytest.mark.asyncio
async def test_full_end_to_end_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        import uuid
        rnd = uuid.uuid4().hex[:8]
        email = f"final_val_{rnd}@example.com"
        password = "TestPassword123!"
        await client.post("/api/v1/auth/register", json={
            "full_name": "Final Validator",
            "email": email,
            "password": password,
            "role": "admin"
        })

        async with AsyncSessionLocal() as session:
            from sqlalchemy import update
            await session.execute(
                update(User).where(User.email == email).values(is_email_verified=True)
            )
            await session.commit()

        login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # =====================================================================
        # PHASE 1: Complete Verification Pipeline for Certificate A
        # =====================================================================
        doc_a_bytes = _create_sample_image(
            "UNIVERSITY OF TECHNOLOGY\n"
            "OFFICIAL DEGREE CERTIFICATE\n"
            "Name: Alice Johnson\n"
            "Registration No: REG-2026-9901\n"
            "Course: Bachelor of Computer Science\n"
            "Date of Issue: 2026-05-15\n"
            "Department: Engineering"
        )
        
        # 1. Upload
        files_a = [("files", ("certificate_alice.png", doc_a_bytes, "image/png"))]
        resp_upload = await client.post("/api/v1/certificates/upload", files=files_a, headers=headers)
        assert resp_upload.status_code in [200, 201], f"Upload failed: {resp_upload.text}"
        cert_a_id = resp_upload.json()["certificates"][0]["id"]
        assert cert_a_id, "Certificate A must have an ID"
        
        # 2. Run Verification Pipeline
        resp_pipe = await client.post(f"/api/v1/certificates/{cert_a_id}/run-pipeline", headers=headers)
        assert resp_pipe.status_code == 200, f"Pipeline execution failed: {resp_pipe.text}"
        pipe_data = resp_pipe.json()
        assert pipe_data["certificate_id"] == cert_a_id
        
        # 3. Check OCR endpoint
        resp_ocr = await client.get(f"/api/v1/certificates/{cert_a_id}/ocr-data", headers=headers)
        assert resp_ocr.status_code == 200
        ocr_data = resp_ocr.json()
        assert ocr_data["certificate_id"] == cert_a_id
        
        # 4. Check Tampering / Verification endpoint
        resp_forensics = await client.get(f"/api/v1/certificates/{cert_a_id}/verification", headers=headers)
        assert resp_forensics.status_code == 200
        forensics_data = resp_forensics.json()
        assert forensics_data["certificate_id"] == cert_a_id
        
        # 5. Check Trust Score endpoint
        resp_trust = await client.get(f"/api/v1/certificates/{cert_a_id}/trust-score", headers=headers)
        assert resp_trust.status_code == 200
        trust_data = resp_trust.json()
        assert trust_data["certificate_id"] == cert_a_id
        assert 0.0 <= trust_data["score"] <= 100.0
        
        # 6. Check Prediction endpoint
        resp_pred = await client.get(f"/api/v1/certificates/{cert_a_id}/prediction", headers=headers)
        assert resp_pred.status_code == 200
        pred_data = resp_pred.json()
        assert pred_data["certificate_id"] == cert_a_id
        
        # 7. Generate Report for A
        resp_rep_gen = await client.post(f"/api/v1/certificates/{cert_a_id}/generate-report", headers=headers)
        assert resp_rep_gen.status_code == 200
        report_a = resp_rep_gen.json()
        assert report_a["certificate_id"] == cert_a_id
        report_a_id = report_a["id"]
        
        # 8. Check History endpoint
        resp_hist = await client.get("/api/v1/certificates/history", headers=headers)
        assert resp_hist.status_code == 200
        hist_list = resp_hist.json()
        assert any(item["certificate_id"] == cert_a_id for item in hist_list)
        
        # 9. Test Certificate Review Action on A
        resp_rev = await client.post(
            f"/api/v1/certificates/{cert_a_id}/review",
            json={"verdict": "genuine", "review_note": "Verified authentic during validation test."},
            headers=headers
        )
        assert resp_rev.status_code == 200
        rev_data = resp_rev.json()
        assert rev_data["verdict"] == "genuine"

        # =====================================================================
        # PHASE 2: Certificate Comparison Workflow
        # =====================================================================
        doc_b_bytes = _create_sample_image(
            "STATE UNIVERSITY\n"
            "DEGREE CERTIFICATE\n"
            "Name: Bob Smith\n"
            "Registration No: REG-2026-9902\n"
            "Course: Bachelor of Computer Science\n"
            "Date of Issue: 2026-06-01\n"
            "Department: Computer Engineering"
        )
        
        # Upload Document B & compare with Document A
        files_b = {"file": ("certificate_bob.png", doc_b_bytes, "image/png")}
        resp_comp = await client.post(
            "/api/v1/comparisons/upload-and-compare",
            data={"certificate_id_a": cert_a_id},
            files=files_b,
            headers=headers
        )
        assert resp_comp.status_code == 200, f"Comparison failed: {resp_comp.text}"
        comp_res = resp_comp.json()
        
        assert comp_res["certificate_id_a"] == cert_a_id
        cert_b_id = comp_res["certificate_id_b"]
        assert cert_b_id is not None
        assert comp_res["overall_match_status"] in ["MATCH", "MISMATCH", "PARTIAL MATCH"]
        assert len(comp_res["field_comparisons"]) > 0
        assert comp_res["summary"] is not None
        
        # Verify status values for fields
        valid_statuses = {"MATCH", "MISMATCH", "UNKNOWN / NOT DETECTED"}
        for fc in comp_res["field_comparisons"]:
            assert fc["status"] in valid_statuses, f"Invalid status: {fc['status']}"
        
        # CRITICAL ASSERTION: Ensure Certificate A's report was NOT altered by comparison
        resp_rep_check = await client.get(f"/api/v1/certificates/{cert_a_id}/report", headers=headers)
        assert resp_rep_check.status_code == 200
        unaltered_report = resp_rep_check.json()
        assert unaltered_report["id"] == report_a_id
        assert unaltered_report["certificate_id"] == cert_a_id

        # =====================================================================
        # PHASE 3: Edge Cases, Error Handling & Empty States
        # =====================================================================
        # 1. Invalid certificate ID returns 404 cleanly
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp_fake = await client.get(f"/api/v1/certificates/{fake_uuid}", headers=headers)
        assert resp_fake.status_code == 404
        
        # 2. Duplicate detection returns UNIQUE for fresh single doc
        fresh_bytes = _create_sample_image("UNIQUE ONE TIME CERTIFICATE 12345")
        resp_fresh_up = await client.post("/api/v1/certificates/upload", files=[("files", ("unique.png", fresh_bytes, "image/png"))], headers=headers)
        assert resp_fresh_up.status_code in [200, 201]
        fresh_id = resp_fresh_up.json()["certificates"][0]["id"]
        resp_fresh_ver = await client.post(f"/api/v1/certificates/{fresh_id}/verify-duplicate", headers=headers)
        assert resp_fresh_ver.status_code == 200
        assert resp_fresh_ver.json()["is_duplicate"] is False
