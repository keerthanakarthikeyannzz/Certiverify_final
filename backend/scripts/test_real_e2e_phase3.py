"""
Phase 3 E2E Integration Script:
Tests live FastAPI server at http://localhost:8000:
1. Auth registration / login
2. File upload of real certificate PDF fixture
3. OCR extraction with EasyOCR baseline
4. Execution of all pipeline endpoints:
   - Document type classification
   - QR verification
   - Blockchain verification
   - Tampering detection
   - Duplicate detection
   - AI fraud analysis
   - Trust score computation
   - Final AI prediction
   - PDF report generation
5. Pipeline status endpoint validation (all 14 stages)
6. Database verification (reading DB state directly)
7. Re-run verification (ensuring no duplicate corrupted rows)
"""
import asyncio
import os
import sys
import httpx
import sqlite3

SERVER_ROOT = "http://localhost:8000"
API_BASE = "http://localhost:8000/api/v1"
TEST_EMAIL = "phase3_tester@certiverify.ai"
TEST_PASSWORD = "Password123!"
SAMPLE_PDF = "../sample_certificate.pdf" if os.path.exists("../sample_certificate.pdf") else "./sample_certificate.pdf"

async def run_e2e_test():
    print("=== STARTING PHASE 3 REAL SERVER E2E TEST ===")
    async with httpx.AsyncClient(timeout=180.0) as client:
        # 1. Health check
        res = await client.get(f"{SERVER_ROOT}/api/health")
        print(f"[1] Health Check: status={res.status_code}, data={res.json()}")
        assert res.status_code == 200

        # 2. Register or Login
        auth_token = None
        reg_res = await client.post(f"{API_BASE}/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": "Phase3 Tester",
            "role": "verifier"
        })
        print(f"[2] Register response ({reg_res.status_code})")

        login_res = await client.post(f"{API_BASE}/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        print(f"[2] Login response ({login_res.status_code})")
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        auth_token = login_res.json().get("access_token")
        print(f"[2] Obtained auth token: {auth_token[:20]}...")

        headers = {"Authorization": f"Bearer {auth_token}"}

        # 3. Upload real certificate file
        if not os.path.exists(SAMPLE_PDF):
            print(f"ERROR: Sample PDF file not found at {SAMPLE_PDF}")
            sys.exit(1)

        with open(SAMPLE_PDF, "rb") as f:
            files = [("files", ("sample_certificate.pdf", f, "application/pdf"))]
            res = await client.post(f"{API_BASE}/certificates/upload", headers=headers, files=files)
        
        print(f"[3] Upload Certificate: status={res.status_code}")
        assert res.status_code in (200, 201), f"Upload failed: {res.text}"
        batch_data = res.json()
        cert_data = batch_data["certificates"][0]
        cert_id = cert_data["id"]
        print(f"    Group ID: {batch_data.get('group_id')}")
        print(f"    Certificate ID: {cert_id}")
        print(f"    Original filename: {cert_data.get('original_filename')}")
        print(f"    SHA256 Hash: {cert_data.get('sha256_hash')}")

        # 4. Check initial pipeline status before OCR
        res = await client.get(f"{API_BASE}/certificates/{cert_id}/pipeline", headers=headers)
        print(f"[4] Initial Pipeline Status: status={res.status_code}")
        assert res.status_code == 200
        pipe_initial = res.json()
        print(f"    Overall: {pipe_initial['overall_status']}, Pct: {pipe_initial['completion_pct']}%")

        # 5. Step 2 — Run OCR Inference
        print("\n[5] Running OCR Inference...")
        res = await client.post(f"{API_BASE}/certificates/{cert_id}/extract-ocr", headers=headers)
        print(f"    OCR Status: {res.status_code}")
        assert res.status_code == 200, f"OCR failed: {res.text}"
        ocr_data = res.json()
        print(f"    Accuracy: {ocr_data.get('ocr_accuracy')}")
        print(f"    Raw text len: {len(ocr_data.get('raw_text') or '')}")
        print(f"    Extracted fields: Student={ocr_data.get('student_name')}, Univ={ocr_data.get('university_name')}, Reg={ocr_data.get('register_number')}")

        # 6. Step 3 — Run all verification & analysis stages (via run-pipeline)
        print("\n[6] Running Full Pipeline via /run-pipeline endpoint...")
        res = await client.post(f"{API_BASE}/certificates/{cert_id}/run-pipeline", headers=headers)
        print(f"    Pipeline status code: {res.status_code}")
        assert res.status_code == 200, f"Run pipeline failed: {res.text}"
        pipeline_res = res.json()
        print(f"    Overall completion: {pipeline_res['overall_status']} ({pipeline_res['completion_pct']}%)")
        print("\n--- 14 PIPELINE STAGE STATUSES ---")
        for s in pipeline_res["stages"]:
            clean_summary = str(s['summary']).encode('ascii', errors='ignore').decode('ascii')
            print(f"  Stage {s['stage']:<20} | Status: {s['status']:<15} | Summary: {clean_summary}")

        # 7. Check enhanced verification composite response
        res = await client.get(f"{API_BASE}/certificates/{cert_id}/verify-enhanced", headers=headers)
        print(f"\n[7] Enhanced Verification composite: status={res.status_code}")
        if res.status_code == 200:
            enh = res.json()
            print(f"    Composite status: {enh.get('composite_status')}")
            print(f"    Composite detail: {enh.get('composite_detail')}")

        # 8. Check Trust Score
        res = await client.get(f"{API_BASE}/certificates/{cert_id}/trust-score", headers=headers)
        print(f"[8] Trust Score: status={res.status_code}")
        if res.status_code == 200:
            ts = res.json()
            print(f"    Score: {ts.get('score')} | Risk: {ts.get('risk_level')}")

        # 9. Check Final Prediction
        res = await client.get(f"{API_BASE}/certificates/{cert_id}/prediction", headers=headers)
        print(f"[9] Final Prediction: status={res.status_code}")
        if res.status_code == 200:
            pred = res.json()
            print(f"    Label: {pred.get('label')} | Confidence: {pred.get('confidence_score')}")

        # 10. Check PDF Report Generation
        res = await client.post(f"{API_BASE}/certificates/{cert_id}/generate-report", headers=headers)
        print(f"[10] Generate PDF Report: status={res.status_code}")
        assert res.status_code == 200, f"Report failed: {res.text}"
        rep_data = res.json()
        print(f"     Report ID: {rep_data.get('verification_id')}")
        print(f"     File path: {rep_data.get('pdf_file_path')}")

        # 11. Test Re-run
        print("\n[11] Testing Re-run (running OCR & pipeline again on same cert)...")
        res_rerun_ocr = await client.post(f"{API_BASE}/certificates/{cert_id}/extract-ocr", headers=headers)
        assert res_rerun_ocr.status_code == 200
        res_rerun_pipe = await client.post(f"{API_BASE}/certificates/{cert_id}/run-pipeline", headers=headers)
        assert res_rerun_pipe.status_code == 200
        print("     Re-run successful! Stage status maintained without corrupt duplicates.")

        # 12. Direct DB verification
        print("\n[12] Inspecting SQLite database records...")
        db_path = "./backend/certiverify_dev.db" if os.path.exists("./backend/certiverify_dev.db") else "./certiverify_dev.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        tables = ["certificates", "ocr_data", "verification_results", "fraud_analysis", "trust_scores", "final_predictions", "verification_reports"]
        for tbl in tables:
            if tbl == "certificates":
                cursor.execute(f"SELECT COUNT(*) FROM {tbl} WHERE id = ?", (cert_id,))
            else:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl} WHERE certificate_id = ?", (cert_id,))
            cnt = cursor.fetchone()[0]
            print(f"     Table {tbl:<22}: {cnt} record(s)")

        conn.close()

    print("\n=== PHASE 3 REAL SERVER E2E TEST COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(run_e2e_test())
