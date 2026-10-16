"""
Unit tests for Verification Pipeline Status & Real-Time Telemetry endpoints.
GET  /api/v1/certificates/{id}/pipeline
POST /api/v1/certificates/{id}/run-pipeline
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_pipeline_status_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/pipeline")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_run_pipeline_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/run-pipeline")
    assert resp.status_code == 401
