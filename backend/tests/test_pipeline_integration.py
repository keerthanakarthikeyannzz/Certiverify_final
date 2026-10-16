"""
Integration test — Full 14-stage pipeline via POST /run-pipeline

Tests the complete orchestrated flow end-to-end:
  upload → OCR → classify → verify-all → fraud → trust → predict → report

Uses a synthetic JPEG certificate image. No real certificate needed.

Requirements (already in venv after Phase 1 fixes):
  pydantic[email]  aiosqlite  Pillow  pytest-asyncio
"""
import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_synthetic_certificate_jpg() -> bytes:
    """Create a small white JPEG with certificate-like text for OCR."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        lines = [
            "CERTIFICATE OF COMPLETION",
            "This is to certify that",
            "John Doe",
            "Register Number: 20CS001",
            "Department: Computer Science",
            "Course: Bachelor of Engineering",
            "University: Test University",
            "CGPA: 8.75",
            "Date of Issue: 2024-05-15",
        ]
        y = 80
        for line in lines:
            draw.text((100, y), line, fill=(0, 0, 0))
            y += 50
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except ImportError:
        # Minimal 1x1 white JPEG fallback
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4\xff\xd9"
        )


async def _register_and_login(ac: AsyncClient) -> str:
    """Register a fresh test user (bypassing email OTP) and return Bearer token."""
    email = f"pipe_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    reg = await ac.post("/api/v1/auth/register", json={
        "full_name": "Pipeline Tester",
        "email": email,
        "password": password,
        "role": "verifier",
    })
    assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

    # Bypass email verification directly in the test SQLite DB
    from app.db.database import AsyncSessionLocal
    from app.models.models import User
    from sqlalchemy import update
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.email == email).values(is_email_verified=True)
        )
        await session.commit()

    login = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, f"Login failed: {login.text}"
    return login.json()["access_token"]


async def _upload_certificate(ac: AsyncClient, token: str) -> str:
    """Upload a synthetic JPEG and return the certificate ID."""
    jpg_bytes = _make_synthetic_certificate_jpg()
    resp = await ac.post(
        "/api/v1/certificates/upload",
        files=[("files", ("test_cert.jpg", jpg_bytes, "image/jpeg"))],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201), f"Upload failed: {resp.text}"
    certs = resp.json()["certificates"]
    assert len(certs) == 1
    return certs[0]["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_pipeline_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/certificates/00000000-0000-0000-0000-000000000000/run-pipeline"
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pipeline_status_has_14_stages():
    """GET /pipeline must return exactly 14 named stages for a fresh upload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        resp = await ac.get(
            f"/api/v1/certificates/{cert_id}/pipeline",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["certificate_id"] == cert_id
    assert len(data["stages"]) == 14, f"Expected 14 stages, got {len(data['stages'])}"
    stage_ids = {s["stage"] for s in data["stages"]}
    for required in ("upload", "ocr", "blockchain", "tampering", "duplicate",
                     "fraud_analysis", "trust_score", "prediction", "report"):
        assert required in stage_ids, f"Missing pipeline stage: {required}"


@pytest.mark.asyncio
async def test_upload_stage_immediately_completed():
    """The 'upload' stage must be COMPLETED immediately after upload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        resp = await ac.get(
            f"/api/v1/certificates/{cert_id}/pipeline",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = resp.json()
    upload = next(s for s in data["stages"] if s["stage"] == "upload")
    assert upload["status"] == "COMPLETED", f"upload stage not COMPLETED: {upload}"


@pytest.mark.asyncio
async def test_run_pipeline_returns_valid_shape():
    """POST /run-pipeline must return a valid PipelineStatusResponse body."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=600.0) as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        resp = await ac.post(
            f"/api/v1/certificates/{cert_id}/run-pipeline",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, f"run-pipeline failed: {resp.text}"
    data = resp.json()
    assert data["certificate_id"] == cert_id
    assert "stages" in data
    assert "overall_status" in data
    assert "completion_pct" in data
    assert isinstance(data["completion_pct"], (int, float))
    assert data["completion_pct"] >= 0.0


@pytest.mark.asyncio
async def test_trust_score_not_pending_after_pipeline():
    """
    Regression for the compute_trust_score -> run_trust_score bug fix.

    Before the fix, run_entire_pipeline silently swallowed an ImportError
    (compute_trust_score doesn't exist) leaving trust_score PENDING.
    After the fix it must not be PENDING if OCR succeeded.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=600.0) as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        resp = await ac.post(
            f"/api/v1/certificates/{cert_id}/run-pipeline",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    stage_map = {s["stage"]: s["status"] for s in data["stages"]}

    if stage_map.get("ocr") == "COMPLETED":
        assert stage_map.get("trust_score") != "PENDING", (
            "trust_score is still PENDING after pipeline run. "
            "The compute_trust_score → run_trust_score fix may have reverted."
        )


@pytest.mark.asyncio
async def test_prediction_not_pending_after_pipeline():
    """
    Regression for the run_final_prediction -> run_prediction bug fix.

    Before the fix, the prediction stage was silently skipped.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=600.0) as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        resp = await ac.post(
            f"/api/v1/certificates/{cert_id}/run-pipeline",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    stage_map = {s["stage"]: s["status"] for s in data["stages"]}

    if stage_map.get("trust_score") == "COMPLETED":
        assert stage_map.get("prediction") != "PENDING", (
            "prediction is PENDING despite trust_score completing. "
            "The run_final_prediction → run_prediction fix may have reverted."
        )


@pytest.mark.asyncio
async def test_fraud_analysis_returns_rich_fields():
    """
    Phase 2: POST /analyze-fraud must return risk_level, factor_risks,
    and critical_overrides_applied (new fields in the expanded schema).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=600.0) as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        # Run prerequisites
        await ac.post(
            f"/api/v1/certificates/{cert_id}/extract-ocr",
            headers={"Authorization": f"Bearer {token}"},
        )
        await ac.post(
            f"/api/v1/certificates/{cert_id}/verify-all",
            headers={"Authorization": f"Bearer {token}"},
        )
        fraud_resp = await ac.post(
            f"/api/v1/certificates/{cert_id}/analyze-fraud",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert fraud_resp.status_code == 200, fraud_resp.text
    data = fraud_resp.json()

    assert 0.0 <= data["fraud_probability"] <= 1.0
    assert data.get("risk_level") in ("LOW", "MODERATE", "HIGH", "VERY_HIGH"), \
        f"Unexpected risk_level: {data.get('risk_level')}"
    assert isinstance(data.get("factor_risks"), dict), \
        f"factor_risks not a dict: {data.get('factor_risks')}"
    assert isinstance(data.get("critical_overrides_applied"), list), \
        f"critical_overrides_applied not a list: {data.get('critical_overrides_applied')}"
