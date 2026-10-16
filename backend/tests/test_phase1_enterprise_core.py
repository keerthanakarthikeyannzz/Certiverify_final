import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User, UserRole, Certificate, Organization, AuditLog
from app.core.security import hash_password, create_access_token
from app.core.permissions import has_permission, Permission


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_permission_matrix():
    assert has_permission("admin", Permission.CERTIFICATE_UPLOAD) is True
    assert has_permission("admin", Permission.ORG_MANAGE) is True
    assert has_permission("university", Permission.USER_MANAGE) is True
    assert has_permission("employer", Permission.CERTIFICATE_VERIFY) is True
    assert has_permission("employer", Permission.ORG_MANAGE) is False
    assert has_permission("student", Permission.ORG_MANAGE) is False


@pytest.mark.asyncio
async def test_auto_organization_provisioning(async_client):
    async with AsyncSessionLocal() as db:
        rnd = uuid.uuid4().hex[:8]
        user = User(
            full_name=f"Legacy Test User {rnd}",
            email=f"legacy_user_{rnd}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
            organization_id=None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    token = create_access_token(subject=user_id, extra_claims={"role": "student"})

    response = await async_client.get(
        "/api/v1/organizations/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "Organization" in data["name"]
    assert data["status"] == "active"

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.id == user_id))
        updated_user = res.scalar_one()
        assert updated_user.organization_id is not None
        assert updated_user.organization_id == data["id"]


@pytest.mark.asyncio
async def test_create_organization(async_client):
    async with AsyncSessionLocal() as db:
        rnd = uuid.uuid4().hex[:8]
        user = User(
            full_name=f"Org Admin User {rnd}",
            email=f"org_admin_{rnd}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.ADMIN,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    token = create_access_token(subject=user_id, extra_claims={"role": "admin"})
    slug_val = f"acme-univ-{rnd}"

    response = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Acme University", "slug": slug_val},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    org_data = response.json()
    assert org_data["name"] == "Acme University"
    assert org_data["slug"] == slug_val

    audit_resp = await async_client.get(
        "/api/v1/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) > 0


@pytest.mark.asyncio
async def test_tenant_isolation_rejection(async_client):
    async with AsyncSessionLocal() as db:
        rnd = uuid.uuid4().hex[:8]
        org_a = Organization(name=f"Org A {rnd}", slug=f"org-a-{rnd}", status="active")
        db.add(org_a)
        await db.flush()

        user_a = User(
            full_name=f"User A {rnd}",
            email=f"usera_{rnd}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.STUDENT,
            organization_id=org_a.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user_a)
        await db.flush()

        cert = Certificate(
            organization_id=org_a.id,
            owner_id=user_a.id,
            original_filename="secret_doc.pdf",
            storage_path="uploads/secret_doc.pdf",
            file_type="pdf",
            file_size_bytes=1024,
            sha256_hash=f"hash_{uuid.uuid4().hex}",
        )
        db.add(cert)

        org_b = Organization(name=f"Org B {rnd}", slug=f"org-b-{rnd}", status="active")
        db.add(org_b)
        await db.flush()

        user_b = User(
            full_name=f"User B {rnd}",
            email=f"userb_{rnd}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.STUDENT,
            organization_id=org_b.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user_b)
        await db.commit()

        cert_id = cert.id
        user_b_id = user_b.id

    token_b = create_access_token(subject=user_b_id, extra_claims={"role": "student"})

    response = await async_client.get(
        f"/api/v1/certificates/{cert_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    assert "Access denied" in response.json()["detail"]
