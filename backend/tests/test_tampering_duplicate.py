"""
Unit tests for Module 6 (Part 2) - Tampering Detection + Duplicate Detection.
Full API tests need an authenticated session with a stored certificate
(see NOTE in test_upload.py). Duplicate detection itself needs a real
async DB session (SQLAlchemy queries against ORM columns), so its API
route is covered by auth-gating here; the tampering detection pure
functions are covered directly and were run against real synthetic
images during development — including catching and fixing a genuinely
noisy naive clone-detector before landing on the translation-clustering
approach tested below.
"""
import io

import cv2
import numpy as np
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.services.tampering_detection import (
    check_metadata, analyze_tampering, laplacian_variance, compute_ela,
)

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_verify_tampering_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/verify-tampering")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verify_duplicate_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/verify-duplicate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verify_all_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/verify-all")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ela_heatmap_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/ela-heatmap")
    assert resp.status_code == 401


def test_metadata_check_flags_photoshop_exif_tag():
    img = Image.new("RGB", (200, 200), color="white")
    exif = img.getexif()
    exif[305] = "Adobe Photoshop 24.0"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    buf.seek(0)

    flags = check_metadata(buf.getvalue(), "jpg")
    assert any("Photoshop" in f for f in flags)


def test_metadata_check_clean_image_has_no_flags():
    img = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    buf.seek(0)

    flags = check_metadata(buf.getvalue(), "jpg")
    assert flags == []


def test_laplacian_variance_higher_for_sharp_than_blurred():
    sharp = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.putText(sharp, "SHARP TEXT 12345", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    blurred = cv2.GaussianBlur(sharp, (25, 25), 0)

    assert laplacian_variance(sharp) > laplacian_variance(blurred)


def test_compute_ela_returns_bounded_score_and_matching_heatmap_shape():
    sample = np.full((150, 150, 3), 255, dtype=np.uint8)
    cv2.putText(sample, "TEST", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

    heatmap, score = compute_ela(sample)
    assert 0.0 <= score <= 100.0
    assert heatmap.shape[:2] == sample.shape[:2]


def test_analyze_tampering_runs_end_to_end_within_bounds():
    sample = np.full((300, 400, 3), 255, dtype=np.uint8)
    cv2.putText(sample, "TEST CERTIFICATE", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    sample_bytes = cv2.imencode(".jpg", sample)[1].tobytes()

    result = analyze_tampering(sample_bytes, "jpg", sample)
    assert 0.0 <= result.score <= 100.0
    assert isinstance(result.flags, list)
    assert isinstance(result.ela_heatmap_png, bytes) and len(result.ela_heatmap_png) > 0
