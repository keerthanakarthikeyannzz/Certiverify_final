import asyncio
import os
import sys
import uuid
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User
from sqlalchemy import update


async def main():
    print("=== REPRODUCE VERIFY ALL FLOW ===")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=300.0) as client:
        # 1. Register new user
        email = f"verify_all_user_{uuid.uuid4().hex[:6]}@example.com"
        password = "Password123!"
        reg_resp = await client.post("/api/v1/auth/register", json={
            "full_name": "Verify All User",
            "email": email,
            "password": password,
            "role": "verifier",
        })
        print(f"Register status: {reg_resp.status_code}")

        # Mark email verified
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(User).where(User.email == email).values(is_email_verified=True)
            )
            await session.commit()

        # Login
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": email,
            "password": password,
        })
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Logged in successfully.")

        # 2. Upload sample_certificate.pdf
        pdf_path = os.path.join(os.path.dirname(__file__), "..", "..", "sample_certificate.pdf")
        if not os.path.exists(pdf_path):
            pdf_path = "sample_certificate.pdf"
        print(f"Reading PDF from: {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        upload_resp = await client.post(
            "/api/v1/certificates/upload",
            files=[("files", ("sample_certificate.pdf", pdf_bytes, "application/pdf"))],
            headers=headers,
        )
        print(f"Upload status: {upload_resp.status_code}")
        cert_data = upload_resp.json()["certificates"][0]
        cert_id = cert_data["id"]
        print(f"Uploaded Certificate ID: {cert_id}")

        # Extract OCR first (as cockpit / upload does)
        await client.post(f"/api/v1/certificates/{cert_id}/extract-ocr", headers=headers)

        # 3. Trigger what "Verify All" calls
        print("Calling POST /api/v1/certificates/{cert_id}/verify-all ...")
        verify_all_resp = await client.post(
            f"/api/v1/certificates/{cert_id}/verify-all",
            headers=headers,
        )
        print(f"Verify All status: {verify_all_resp.status_code}")

        # In Cockpit, handleVerifyAll then triggers fraud, trust score, and predict
        await client.post(f"/api/v1/certificates/{cert_id}/analyze-fraud", headers=headers)
        await client.post(f"/api/v1/certificates/{cert_id}/compute-trust-score", headers=headers)
        pred_resp = await client.post(f"/api/v1/certificates/{cert_id}/predict", headers=headers)

        # 4. GET the verification result
        verif_resp = await client.get(
            f"/api/v1/certificates/{cert_id}/verification",
            headers=headers,
        )
        verif_data = verif_resp.json()

        trust_resp = await client.get(
            f"/api/v1/certificates/{cert_id}/trust-score",
            headers=headers,
        )
        trust_data = trust_resp.json() if trust_resp.status_code == 200 else {}

        pred_data = pred_resp.json() if pred_resp.status_code == 200 else {}

        # 5. Print results
        tampering_status = verif_data.get("tampering_status") or verif_data.get("tampering_detail", {}).get("status")
        tampering_score = verif_data.get("tampering_score")
        trust_score = trust_data.get("score")
        verdict_label = pred_data.get("label")

        print("\n--- RESULTS ---")
        print(f"Tampering Status: {tampering_status}")
        print(f"Tampering Score:  {tampering_score}")
        print(f"Trust Score:      {trust_score}")
        print(f"Verdict Label:    {verdict_label}")
        print(f"Explanation:      {pred_data.get('explanation')}")


if __name__ == "__main__":
    asyncio.run(main())
