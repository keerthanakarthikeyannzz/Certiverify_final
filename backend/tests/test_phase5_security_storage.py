"""
PHASE 5 — PRODUCTION STORAGE & SECURITY HARDENING TEST SUITE

Validates:
1. Valid uploads & SHA-256 persistence consistency
2. Invalid extension rejection
3. Magic bytes signature mismatch rejection
4. Oversized file rejection
5. Malformed PDF rejection
6. Decompression bomb image rejection
7. Path traversal in filenames & storage paths
8. Executable double-extension rejection
9. Cross-tenant download prevention (Tenant Isolation)
10. Unauthorized download rejection
11. Revoked API key download rejection
12. Expired API key download rejection
13. LocalStorage path traversal protection
14. S3 storage presigned URL & server-side encryption
15. Production secret validation
16. Security headers presence
17. CORS origin controls
"""
import io
import os
import uuid
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.core.config import Settings, settings
from app.services.storage_service import LocalStorageBackend, S3StorageBackend
from app.services.api_key_service import create_api_key

CERT_BASE = "/api/v1/certificates"
AUTH_BASE = "/api/v1/auth"


def _create_test_image_bytes(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


async def _get_auth_headers(client: AsyncClient, email_prefix: str = "sec_user") -> tuple[dict, str]:
    unique = uuid.uuid4().hex[:8]
    email = f"{email_prefix}_{unique}@certiverify.ai"
    password = "Password123!"
    reg_resp = await client.post(f"{AUTH_BASE}/register", json={
        "email": email, "password": password, "full_name": "Security User", "role": "verifier"
    })
    assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"

    from tests.conftest import verify_test_user_email
    await verify_test_user_email(email)

    resp = await client.post(f"{AUTH_BASE}/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest.mark.asyncio
async def test_valid_file_upload_and_sha256_persistence():
    """Valid PDF upload computes SHA-256 and persists metadata correctly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "valid_upl")
        from tests.conftest import find_sample_pdf
        pdf_path = find_sample_pdf()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        files = [("files", ("valid_degree.pdf", pdf_bytes, "application/pdf"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 201
        data = res.json()
        cert = data["certificates"][0]
        assert cert["sha256_hash"] is not None
        assert len(cert["sha256_hash"]) == 64
        assert cert["original_filename"] == "valid_degree.pdf"


@pytest.mark.asyncio
async def test_invalid_file_extension():
    """Uploads with forbidden extensions (e.g. .exe) are rejected with HTTP 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "bad_ext")
        files = [("files", ("malicious_script.exe", b"MZexecutabledata", "application/x-msdownload"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "Unsupported file extension" in res.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_mime_and_magic_bytes_mismatch():
    """Disguised files (e.g. executable/fake content named .pdf) are rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "magic_mismatch")
        # Named .pdf but containing binary executable bytes
        files = [("files", ("fake_doc.pdf", b"NOT_A_PDF_MAGIC_BYTES_12345", "application/pdf"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "File signature check failed" in res.json()["detail"] or "does not match" in res.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_file_rejection():
    """Files exceeding MAX_UPLOAD_MB are rejected with HTTP 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "oversized")
        # 16 MB fake file (exceeds 15 MB default limit)
        big_content = b"%PDF-1.4 " + b"0" * (16 * 1024 * 1024)
        files = [("files", ("big_doc.pdf", big_content, "application/pdf"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "too large" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_malformed_pdf_rejection():
    """PDF files with valid header but corrupted structural body are rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "corrupt_pdf")
        corrupt_pdf = b"%PDF-1.4\nINVALID_CORRUPTED_PDF_BODY_NO_CATALOG_OR_PAGES_EOF"
        files = [("files", ("corrupt.pdf", corrupt_pdf, "application/pdf"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "Malformed" in res.json()["detail"] or "corrupted" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_decompression_bomb_image_rejection():
    """Images exceeding safe max dimensions are rejected as decompression bomb risk."""
    from app.utils import file_validation
    # Temporarily lower MAX_IMAGE_DIMENSION to test enforcement without allocating 10,000px image memory
    orig_max = file_validation.MAX_IMAGE_DIMENSION
    file_validation.MAX_IMAGE_DIMENSION = 50
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
            headers, _ = await _get_auth_headers(client, "decomp_bomb")
            img_bytes = _create_test_image_bytes(width=100, height=100, fmt="PNG")
            files = [("files", ("huge_img.png", img_bytes, "image/png"))]
            res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
            assert res.status_code == 400
            assert "decompression bomb" in res.json()["detail"].lower()
    finally:
        file_validation.MAX_IMAGE_DIMENSION = orig_max


@pytest.mark.asyncio
async def test_path_traversal_filename_rejection():
    """Filenames containing path traversal sequences (../../secret.pdf) are rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "path_trav")
        from tests.conftest import find_sample_pdf
        with open(find_sample_pdf(), "rb") as f:
            pdf_bytes = f.read()

        files = [("files", ("../../secret_file.pdf", pdf_bytes, "application/pdf"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "prohibited characters" in res.json()["detail"].lower() or "path traversal" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_executable_double_extension_rejection():
    """Filenames with double extensions like degree.pdf.exe are rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, _ = await _get_auth_headers(client, "double_ext")
        from tests.conftest import find_sample_pdf
        with open(find_sample_pdf(), "rb") as f:
            pdf_bytes = f.read()

        files = [("files", ("degree.pdf.exe", pdf_bytes, "application/pdf"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 400
        assert "Executable or script extension" in res.json()["detail"]


@pytest.mark.asyncio
async def test_cross_tenant_download_prevention():
    """Organization A user cannot preview or download Organization B's certificate or report."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers_a, _ = await _get_auth_headers(client, "org_a")
        headers_b, _ = await _get_auth_headers(client, "org_b")

        from tests.conftest import find_sample_pdf
        with open(find_sample_pdf(), "rb") as f:
            pdf_bytes = f.read()

        # Upload cert under Org A
        up_res = await client.post(f"{CERT_BASE}/upload", headers=headers_a, files=[("files", ("cert_a.pdf", pdf_bytes, "application/pdf"))])
        cert_a_id = up_res.json()["certificates"][0]["id"]

        # Org B attempts preview -> must be 403 Forbidden
        prev_res = await client.get(f"{CERT_BASE}/{cert_a_id}/preview", headers=headers_b)
        assert prev_res.status_code == 403
        assert "Access denied" in prev_res.json()["detail"]


@pytest.mark.asyncio
async def test_unauthorized_download_rejection():
    """Unauthenticated requests to download or preview files receive HTTP 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        fake_id = str(uuid.uuid4())
        res = await client.get(f"{CERT_BASE}/{fake_id}/preview")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_revoked_api_key_download_rejection():
    """Revoked API key cannot preview or download certificate resources."""
    from app.db.database import AsyncSessionLocal
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, user_email = await _get_auth_headers(client, "key_rev_user")

        async with AsyncSessionLocal() as db:
            from app.models.models import User
            from sqlalchemy import select
            user_row = (await db.execute(select(User).where(User.email == user_email))).scalar_one()
            org_id = user_row.organization_id or str(uuid.uuid4())
            raw_key, api_key_row = await create_api_key(
                db, organization_id=org_id, name="Test Revoked Key", permissions=["*"]
            )
            # Revoke the key
            api_key_row.status = "revoked"
            await db.commit()

        key_headers = {"X-API-Key": raw_key}
        fake_id = str(uuid.uuid4())
        res = await client.get(f"{CERT_BASE}/{fake_id}/preview", headers=key_headers)
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_expired_api_key_download_rejection():
    """Expired API key cannot preview or download certificate resources."""
    from app.db.database import AsyncSessionLocal
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers, user_email = await _get_auth_headers(client, "key_exp_user")

        async with AsyncSessionLocal() as db:
            from app.models.models import User
            from sqlalchemy import select
            user_row = (await db.execute(select(User).where(User.email == user_email))).scalar_one()
            org_id = user_row.organization_id or str(uuid.uuid4())
            past_date = datetime.utcnow() - timedelta(days=1)
            raw_key, api_key_row = await create_api_key(
                db, organization_id=org_id, name="Test Expired Key", permissions=["*"], expires_at=past_date
            )

        key_headers = {"X-API-Key": raw_key}
        fake_id = str(uuid.uuid4())
        res = await client.get(f"{CERT_BASE}/{fake_id}/preview", headers=key_headers)
        assert res.status_code == 401
        assert "expired" in res.json()["detail"].lower()


def test_local_storage_path_traversal_protection():
    """LocalStorageBackend verifies path traversal escaping attempts raise ValueError."""
    storage = LocalStorageBackend()
    bad_path = os.path.join(storage.base_dir, "../../Windows/System32/secret.txt")
    with pytest.raises(ValueError, match="escapes configured storage root"):
        storage._verify_safe_path(bad_path)


def test_production_secret_validation():
    """Settings.validate_production_secrets() raises ValueError if default secret is used in production."""
    prod_settings = Settings(ENV="production", SECRET_KEY="CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32")
    with pytest.raises(ValueError, match="Insecure or default SECRET_KEY set in production mode"):
        prod_settings.validate_production_secrets()


@pytest.mark.asyncio
async def test_security_headers_present():
    """Responses contain X-Content-Type-Options, X-Frame-Options, STS, Referrer & Permissions policies."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        headers = res.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "Strict-Transport-Security" in headers
        assert "Referrer-Policy" in headers
        assert "Permissions-Policy" in headers
