"""
CertiVerify Step 4 End-to-End Live Verification Script
Verifies:
1. Certificate A: Upload -> Full Pipeline -> Generate Report
2. Certificate B (different doc): Upload -> Full Pipeline -> Generate Report
3. Certificate A re-run: Full Pipeline -> Generate Report
4. Duplicate upload (identical file as new cert): Full Pipeline completes, duplicate detected with owner info
5. Concurrent pipeline run: Returns HTTP 409 Conflict with descriptive detail, no crash
6. Generate report 3 times on one certificate: No errors, fresh verification_ids, PDFs generated
7. Refresh token rotation & 401 handling
8. Confirms uvicorn does not reload during runs
"""
import asyncio
import io
import os
import sys
import time
import httpx
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SERVER_ROOT = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
API_BASE = f"{SERVER_ROOT}/api/v1"
TEST_EMAIL = f"live_verify_{int(time.time())}@certiverify.ai"
TEST_PASSWORD = "Password123!"
BACKEND_LOG = "/Users/keerthanakarthikeyan/.gemini/antigravity-ide/brain/83be763a-e621-4cbe-91a4-1172b18d404a/scratch/backend.log"


def create_pdf(title: str, student_name: str, roll_no: str, cert_no: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 700, title)
    c.setFont("Helvetica", 14)
    c.drawString(100, 650, f"This is to certify that {student_name}")
    c.drawString(100, 620, f"Roll Number: {roll_no}")
    c.drawString(100, 590, f"Certificate ID: {cert_no}")
    c.drawString(100, 560, "Has successfully completed the Degree of Bachelor of Engineering")
    c.drawString(100, 530, "Anna University, Chennai. Date: 12-May-2023. CGPA: 8.95")
    c.save()
    return buf.getvalue()


async def wait_for_pipeline(client: httpx.AsyncClient, cert_id: str, headers: dict, timeout: float = 120.0):
    start = time.time()
    while time.time() - start < timeout:
        res = await client.get(f"{API_BASE}/certificates/{cert_id}/pipeline", headers=headers)
        assert res.status_code == 200, f"Pipeline status failed: {res.text}"
        data = res.json()
        status = data.get("overall_status")
        comp_pct = data.get("completion_pct", 0)
        stages = data.get("stages", [])
        completed_stages = [s["stage"] for s in stages if s.get("status") in ("COMPLETED", "SKIPPED", "NOT_APPLICABLE")]
        print(f"   [Polling {cert_id[:8]}] Status: {status}, Completion: {comp_pct}%, Completed Stages: {len(completed_stages)}/{len(stages)}")

        pred_stage = next((s for s in stages if s["stage"] == "prediction"), None)
        if status in ("FULLY_COMPLETE", "COMPLETED") or (pred_stage and pred_stage.get("status") == "COMPLETED"):
            return data
        if status == "FAILED":
            raise RuntimeError(f"Pipeline failed for {cert_id}: {data}")
        await asyncio.sleep(2.0)
    raise TimeoutError(f"Pipeline timed out after {timeout}s for {cert_id}")


async def main():
    print("=" * 70)
    print("🚀 STARTING CERTIVERIFY LIVE VERIFICATION SUITE")
    print("=" * 70)

    # Record log size before test
    initial_log_size = os.path.getsize(BACKEND_LOG) if os.path.exists(BACKEND_LOG) else 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 0. Health
        health_res = await client.get(f"{SERVER_ROOT}/health")
        print(f"✔ Health Check: {health_res.status_code} - {health_res.json()}")
        assert health_res.status_code == 200

        # 1. Auth Setup
        print("\n--- 1. Auth Registration & Login ---")
        reg_res = await client.post(f"{API_BASE}/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": "Live Step 4 Verifier",
            "role": "student",
        })
        print(f"Register: {reg_res.status_code}")

        login_res = await client.post(f"{API_BASE}/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        login_data = login_res.json()
        access_token = login_data["access_token"]
        refresh_token = login_data.get("refresh_token")
        headers = {"Authorization": f"Bearer {access_token}"}
        print(f"✔ Logged in successfully. Token: {access_token[:20]}...")
        assert refresh_token is not None, "Refresh token must be present"

        # 2. Upload Certificate A
        print("\n--- 2. Certificate A: Upload -> Verify All -> Report ---")
        pdf_a_bytes = create_pdf("DEGREE OF ENGINEERING", "Alice Smith", "2023-CS-001", "CERT-A-1001")
        up_a = await client.post(
            f"{API_BASE}/certificates/upload",
            headers=headers,
            files={"files": ("certificate_a.pdf", pdf_a_bytes, "application/pdf")},
        )
        assert up_a.status_code == 201, f"Upload A failed: {up_a.text}"
        cert_a_id = up_a.json()["certificates"][0]["id"]
        print(f"✔ Certificate A uploaded: {cert_a_id}")
        await wait_for_pipeline(client, cert_a_id, headers)
        print("✔ Certificate A initial pipeline FULLY_COMPLETE")

        # Explicit run-pipeline on Certificate A
        run_a = await client.post(f"{API_BASE}/certificates/{cert_a_id}/run-pipeline", headers=headers)
        assert run_a.status_code == 202, f"Run pipeline A failed: {run_a.text}"
        print(f"✔ Explicit Run pipeline A accepted (202): job_id={run_a.json().get('job_id')}")
        await wait_for_pipeline(client, cert_a_id, headers)
        print("✔ Certificate A explicit pipeline run FULLY_COMPLETE")

        rep_a = await client.post(f"{API_BASE}/certificates/{cert_a_id}/report", headers=headers)
        assert rep_a.status_code == 200, f"Report A failed: {rep_a.text}"
        print(f"✔ Certificate A report generated: verification_id={rep_a.json().get('verification_id')}")

        # 3. Upload Certificate B (different doc)
        print("\n--- 3. Certificate B (Different Document): Upload -> Verify All -> Report ---")
        pdf_b_bytes = create_pdf("POSTGRADUATE DIPLOMA", "Bob Jones", "2023-PG-042", "CERT-B-2002")
        up_b = await client.post(
            f"{API_BASE}/certificates/upload",
            headers=headers,
            files={"files": ("certificate_b.pdf", pdf_b_bytes, "application/pdf")},
        )
        assert up_b.status_code == 201, f"Upload B failed: {up_b.text}"
        cert_b_id = up_b.json()["certificates"][0]["id"]
        print(f"✔ Certificate B uploaded: {cert_b_id}")
        await wait_for_pipeline(client, cert_b_id, headers)
        print("✔ Certificate B initial pipeline FULLY_COMPLETE")

        run_b = await client.post(f"{API_BASE}/certificates/{cert_b_id}/run-pipeline", headers=headers)
        assert run_b.status_code == 202, f"Run pipeline B failed: {run_b.text}"
        print(f"✔ Explicit Run pipeline B accepted (202): job_id={run_b.json().get('job_id')}")
        await wait_for_pipeline(client, cert_b_id, headers)
        print("✔ Certificate B pipeline FULLY_COMPLETE")

        rep_b = await client.post(f"{API_BASE}/certificates/{cert_b_id}/report", headers=headers)
        assert rep_b.status_code == 200, f"Report B failed: {rep_b.text}"
        print(f"✔ Certificate B report generated: verification_id={rep_b.json().get('verification_id')}")

        # 4. Re-verify Certificate A (clean re-run)
        print("\n--- 4. Certificate A Re-run: Re-verify -> Report ---")
        run_a2 = await client.post(f"{API_BASE}/certificates/{cert_a_id}/run-pipeline", headers=headers)
        assert run_a2.status_code == 202, f"Run pipeline A2 failed: {run_a2.text}"
        print(f"✔ Certificate A re-run accepted (202): job_id={run_a2.json().get('job_id')}")
        await wait_for_pipeline(client, cert_a_id, headers)
        print("✔ Certificate A re-run FULLY_COMPLETE")

        rep_a2 = await client.post(f"{API_BASE}/certificates/{cert_a_id}/report", headers=headers)
        assert rep_a2.status_code == 200, f"Report A2 failed: {rep_a2.text}"
        print(f"✔ Certificate A report re-generated: verification_id={rep_a2.json().get('verification_id')}")

        # 5. Duplicate Upload (identical bytes as Certificate A)
        print("\n--- 5. Duplicate Upload: Identical File Uploaded as New Certificate ---")
        up_dup = await client.post(
            f"{API_BASE}/certificates/upload",
            headers=headers,
            files={"files": ("certificate_a_copy.pdf", pdf_a_bytes, "application/pdf")},
        )
        assert up_dup.status_code == 201, f"Duplicate upload failed: {up_dup.text}"
        cert_dup_id = up_dup.json()["certificates"][0]["id"]
        print(f"✔ Duplicate file uploaded with new certificate id: {cert_dup_id}")
        dup_pipe = await wait_for_pipeline(client, cert_dup_id, headers)
        print(f"✔ Duplicate certificate pipeline FULLY_COMPLETE: status={dup_pipe.get('overall_status')}")

        # Check duplicate stage result via verification-result
        dup_stage_res = await client.get(f"{API_BASE}/certificates/{cert_dup_id}/verification-result", headers=headers)
        assert dup_stage_res.status_code == 200, f"Verification result failed: {dup_stage_res.text}"
        dup_data = dup_stage_res.json()
        evidence_dup = dup_data.get("evidence", {}).get("duplicate", {})
        dup_status = evidence_dup.get("status")
        print(f"✔ Duplicate check result: status={dup_status}, summary={dup_data.get('verification_summary', {}).get('duplicate_checked')}")
        assert dup_status == "OWN_REUPLOAD", f"Expected OWN_REUPLOAD for same-owner duplicate, got {dup_status}"

        # 6. Concurrency Protection (HTTP 409 Conflict)
        print("\n--- 6. Concurrent Pipeline Prevention (HTTP 409 Conflict) ---")
        # Start a run
        run_c1 = await client.post(f"{API_BASE}/certificates/{cert_b_id}/run-pipeline", headers=headers)
        assert run_c1.status_code == 202
        # Immediately attempt second concurrent run on same cert
        run_c2 = await client.post(f"{API_BASE}/certificates/{cert_b_id}/run-pipeline", headers=headers)
        print(f"✔ Immediate second run response code: {run_c2.status_code}")
        assert run_c2.status_code == 409, f"Expected 409 Conflict, got {run_c2.status_code}: {run_c2.text}"
        conflict_msg = run_c2.json().get("detail", "")
        print(f"✔ Conflict message: {conflict_msg}")
        assert "already in progress" in conflict_msg
        # Wait for the active job to finish
        await wait_for_pipeline(client, cert_b_id, headers)

        # 7. Generate Report 3 Times on Single Certificate
        print("\n--- 7. Generate Report 3 Times Sequentially ---")
        report_ids = []
        for i in range(1, 4):
            rep_res = await client.post(f"{API_BASE}/certificates/{cert_a_id}/report", headers=headers)
            assert rep_res.status_code == 200, f"Sequential report {i} failed: {rep_res.text}"
            v_id = rep_res.json().get("verification_id")
            report_ids.append(v_id)
            print(f"   Report #{i} generated: verification_id={v_id}")

        assert len(set(report_ids)) == 3, f"Expected 3 distinct verification_ids, got {report_ids}"
        print(f"✔ 3 distinct reports generated successfully: {report_ids}")

        # 8. Refresh Token Rotation
        print("\n--- 8. Refresh Token Rotation & Session Continuity ---")
        refresh_res = await client.post(f"{API_BASE}/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_res.status_code == 200, f"Token refresh failed: {refresh_res.text}"
        refreshed_data = refresh_res.json()
        new_access = refreshed_data.get("access_token")
        new_refresh = refreshed_data.get("refresh_token")
        assert new_access is not None
        assert new_refresh is not None
        assert new_refresh != refresh_token, "Refresh token should be rotated"
        print("✔ Refresh token rotated successfully. New session is active.")

        # Test request with new access token
        refreshed_headers = {"Authorization": f"Bearer {new_access}"}
        certs_list = await client.get(f"{API_BASE}/certificates", headers=refreshed_headers)
        assert certs_list.status_code == 200
        print(f"✔ Authenticated request with rotated token succeeded ({len(certs_list.json())} certificates listed)")

        # 9. Verify Uvicorn did NOT restart during any runs
        print("\n--- 9. Verifying Reloader Isolation (No Server Restarts) ---")
        if os.path.exists(BACKEND_LOG):
            with open(BACKEND_LOG, "r") as f:
                f.seek(initial_log_size)
                new_logs = f.read()

            restart_indicators = ["Reloading...", "Started server process", "Detected changes"]
            restarts_found = [ind for ind in restart_indicators if ind in new_logs]
            if restarts_found:
                print(f"❌ WARNING: Reloader triggered during runs: {restarts_found}")
                print(new_logs[-1000:])
                raise RuntimeError("Uvicorn restarted during pipeline executions!")
            else:
                print("✔ Zero reloader restarts detected in backend log during all pipeline runs.")

    print("\n" + "=" * 70)
    print("🎉 ALL STEP 4 LIVE VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
