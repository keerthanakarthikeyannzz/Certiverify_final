import requests
import json
import os

API_BASE = "http://127.0.0.1:8000"

import uuid

def test_full_cockpit_flow():
    print("=== Step 1: User Registration & Login ===")
    rnd = uuid.uuid4().hex[:8]
    email = f"cockpit_tester_{rnd}@certiverify.ai"
    password = "TestPassword123!"
    reg_res = requests.post(f"{API_BASE}/api/v1/auth/register", json={
        "full_name": "Cockpit Tester",
        "email": email,
        "password": password,
        "role": "student"
    })
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
    login_res = requests.post(f"{API_BASE}/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Logged in successfully as {email}. Token acquired.")

    print("\n=== Step 2: Upload Certificate ===")
    # Look for sample_certificate.pdf
    sample_path = "sample_certificate.pdf"
    if not os.path.exists(sample_path):
        sample_path = os.path.join("..", "sample_certificate.pdf")
    
    with open(sample_path, "rb") as f:
        files = {"files": ("sample_certificate.pdf", f, "application/pdf")}
        upload_res = requests.post(f"{API_BASE}/api/v1/certificates/upload", headers=headers, files=files)
    
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.status_code} {upload_res.text}"
    cert_data = upload_res.json()["certificates"][0]
    cert_id = cert_data["id"]
    print(f"Uploaded successfully! Certificate ID: {cert_id}, Filename: {cert_data['original_filename']}")

    print("\n=== Step 3: Check Preview Endpoint ===")
    preview_res = requests.get(f"{API_BASE}/api/v1/certificates/{cert_id}/preview", headers=headers)
    assert preview_res.status_code == 200, f"Preview failed: {preview_res.status_code}"
    assert len(preview_res.content) > 0, "Preview content is empty"
    print(f"Preview verified! Received {len(preview_res.content)} bytes, Content-Type: {preview_res.headers.get('content-type')}")

    print("\n=== Step 4: Check Initial Pipeline Status (NOT STARTED) ===")
    pipe_init = requests.get(f"{API_BASE}/api/v1/certificates/{cert_id}/pipeline", headers=headers)
    assert pipe_init.status_code == 200, f"Pipeline status failed: {pipe_init.status_code}"
    pipe_init_json = pipe_init.json()
    print(f"Initial Pipeline Overall Status: {pipe_init_json['overall_status']}")
    print(f"Stages count: {len(pipe_init_json['stages'])}, Completion %: {pipe_init_json['completion_pct']}%")

    print("\n=== Step 5: Execute Neural OCR Extraction ===")
    ocr_res = requests.post(f"{API_BASE}/api/v1/certificates/{cert_id}/extract-ocr", headers=headers)
    assert ocr_res.status_code == 200, f"OCR extraction failed: {ocr_res.status_code} {ocr_res.text}"
    ocr_json = ocr_res.json()
    print(f"OCR Extraction Succeeded!")
    print(f"  Student Name: {ocr_json.get('student_name')}")
    print(f"  Register Number: {ocr_json.get('register_number')}")
    print(f"  University: {ocr_json.get('university_name')}")
    print(f"  Engine: {ocr_json.get('ocr_engine')}")
    print(f"  Accuracy: {round(ocr_json.get('ocr_accuracy', 0) * 100, 1)}%")

    print("\n=== Step 6: Execute 14-Stage Verification Pipeline ===")
    run_pipe_res = requests.post(f"{API_BASE}/api/v1/certificates/{cert_id}/run-pipeline", headers=headers)
    assert run_pipe_res.status_code == 200, f"Pipeline run failed: {run_pipe_res.status_code} {run_pipe_res.text}"
    run_pipe_json = run_pipe_res.json()
    print(f"Pipeline Run Succeeded!")
    print(f"  Overall Status: {run_pipe_json['overall_status']}")
    print(f"  Completion %: {run_pipe_json['completion_pct']}%")
    completed = [s['label'] for s in run_pipe_json['stages'] if s['status'] in ('COMPLETED', 'SKIPPED')]
    print(f"  Completed/Skipped stages ({len(completed)}/14): {completed}")

    print("\n=== ALL COCKPIT WORKFLOW INTEGRATION CHECKS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_full_cockpit_flow()
