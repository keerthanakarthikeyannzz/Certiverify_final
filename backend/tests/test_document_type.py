"""
Unit tests for Module 3 - AI Document Type Identification.
Full classify() tests need an authenticated session + a real stored file
(see NOTE in test_upload.py re: the OTP-capture fixture needed for that).
These tests cover auth-gating and the classifier's pure-function pieces,
which don't require the API/DB at all.
"""
import numpy as np
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.document_classifier import _classify_with_heuristics, _apply_layout_boost
from app.models.models import DocTypeEnum

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_classify_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/classify")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_document_type_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/document-type")
    assert resp.status_code == 401


def test_heuristic_classifier_detects_degree_with_seal_and_qr():
    signals = {"aspect_ratio": 1.4, "has_circular_seal": True, "has_qr_code": True, "edge_density": 0.05}
    predicted, confidence = _classify_with_heuristics(signals)
    assert predicted == DocTypeEnum.DEGREE_CERTIFICATE
    assert 0.0 < confidence <= 1.0


def test_heuristic_classifier_detects_marksheet_from_dense_edges():
    signals = {"aspect_ratio": 1.2, "has_circular_seal": False, "has_qr_code": False, "edge_density": 0.2}
    predicted, _ = _classify_with_heuristics(signals)
    assert predicted == DocTypeEnum.MARKSHEET


def test_heuristic_classifier_falls_back_to_unknown():
    signals = {"aspect_ratio": 1.0, "has_circular_seal": False, "has_qr_code": False, "edge_density": 0.02}
    predicted, confidence = _classify_with_heuristics(signals)
    assert predicted == DocTypeEnum.UNKNOWN
    assert confidence < 0.5


def test_layout_boost_increases_confidence_for_corroborating_seal():
    signals = {"aspect_ratio": 1.4, "has_circular_seal": True, "has_qr_code": True, "edge_density": 0.05}
    predicted, boosted = _apply_layout_boost(DocTypeEnum.DEGREE_CERTIFICATE, 0.7, signals)
    assert predicted == DocTypeEnum.DEGREE_CERTIFICATE
    assert boosted > 0.7
    assert boosted <= 1.0


def test_layout_boost_penalizes_id_card_with_wrong_aspect_ratio():
    signals = {"aspect_ratio": 1.4, "has_circular_seal": False, "has_qr_code": False, "edge_density": 0.05}
    predicted, boosted = _apply_layout_boost(DocTypeEnum.IDENTITY_CARD, 0.5, signals)
    assert boosted < 0.5
