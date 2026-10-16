import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, update

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User
from app.api.pipeline_status import run_entire_pipeline

pytestmark = pytest.mark.asyncio

def _make_synthetic_certificate_jpg() -> bytes:
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        lines = [
            "CERTIFICATE OF COMPLETION",
            "This is to certify that John Doe",
            "Register Number: 20CS001",
        ]
        y = 80
        for line in lines:
            draw.text((100, y), line, fill=(0, 0, 0))
            y += 50
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except ImportError:
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4\xff\xd9"
        )

async def _register_and_login(ac: AsyncClient) -> str:
    email = f"seq_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    reg = await ac.post("/api/v1/auth/register", json={
        "full_name": "Sequential Pipeline Tester",
        "email": email,
        "password": password,
        "role": "verifier",
    })
    assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.email == email).values(is_email_verified=True)
        )
        await session.commit()

    login = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return token

async def select_user_by_token(token: str, db):
    from app.core.security import decode_token
    payload = decode_token(token)
    user_id = payload.get("sub")
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one()

async def _upload_certificate(ac: AsyncClient, token: str) -> str:
    jpg_bytes = _make_synthetic_certificate_jpg()
    resp = await ac.post(
        "/api/v1/certificates/upload",
        files=[("files", ("seq_cert.jpg", jpg_bytes, "image/jpeg"))],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201), f"Upload failed: {resp.text}"
    certs = resp.json()["certificates"]
    return certs[0]["id"]

async def test_sequential_pipeline_execution():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=300.0) as ac:
        token = await _register_and_login(ac)
        cert_id = await _upload_certificate(ac, token)
        
        async with AsyncSessionLocal() as db:
            user = await select_user_by_token(token, db)
            res = await run_entire_pipeline(cert_id, user, db)
            print("\nPipeline Result Stages:")
            for s in res.stages:
                print(f"  Stage '{s.stage}': {s.status} ({s.summary})")
            print("Completion Pct:", res.completion_pct)

        resp = await ac.get(f"/api/v1/certificates/{cert_id}/pipeline", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        stages = {s["stage"]: s for s in data["stages"]}
        assert stages["ocr"]["status"] in ("COMPLETED", "FAILED")
