"""
Unit tests for Module 5 - Document Comparison.
Full run-comparison API tests need an authenticated session with two OCR'd
documents in a group (see NOTE in test_upload.py re: the OTP-capture
fixture needed for that). These cover auth-gating plus the comparison
engine's pure logic — all assertions here were validated against real
output during development, not just guessed.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.document_comparison import compare_documents


class FakeOCR:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _doc(**overrides) -> FakeOCR:
    base = dict(
        student_name=None, register_number=None, university_name=None,
        course=None, department=None, cgpa=None, percentage=None, date_of_issue=None,
    )
    base.update(overrides)
    return FakeOCR(**base)


COMPARISON_BASE = "/api/v1/comparisons"


@pytest.mark.asyncio
async def test_run_comparison_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{COMPARISON_BASE}/some-group-id/run")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_comparison_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{COMPARISON_BASE}/some-group-id")
    assert resp.status_code == 401


def test_compare_documents_requires_at_least_two():
    with pytest.raises(ValueError):
        compare_documents([_doc(student_name="Solo Document")])


def test_compare_documents_fuzzy_matches_minor_ocr_noise():
    doc1 = _doc(student_name="John Doe Smith", register_number="21CS1045",
                university_name="ABC University", course="Bachelor of Computer Science",
                department="Computer Science", cgpa=8.75, percentage=82.5, date_of_issue="15/06/2024")
    doc2 = _doc(student_name="Jon Doe Smith", register_number="21CS1045",  # OCR noise
                university_name="ABC University", course="Bachelor of Computer Science",
                department=None, cgpa=8.70, percentage=90.0, date_of_issue="2024")

    result = compare_documents([doc1, doc2])
    assert "student_name" in result.matching_fields  # fuzzy match tolerates "Jon" vs "John"
    assert "register_number" in result.matching_fields
    assert "course" in result.matching_fields
    assert "graduation_year" in result.matching_fields
    assert "percentage" in result.mismatched_fields  # 82.5 vs 90.0 is a real mismatch
    assert "department" in result.missing_fields     # only present on one document
    assert 0.0 <= result.consistency_percentage <= 100.0


def test_compare_documents_flags_clearly_different_identities():
    doc1 = _doc(student_name="John Smith", register_number="X1")
    doc2 = _doc(student_name="Alice Johnson", register_number="X2")

    result = compare_documents([doc1, doc2])
    assert "student_name" in result.mismatched_fields
    assert "register_number" in result.mismatched_fields
    assert result.consistency_percentage == 0.0


def test_compare_documents_all_missing_yields_zero_consistency():
    doc1 = _doc()
    doc2 = _doc()
    result = compare_documents([doc1, doc2])
    assert result.consistency_percentage == 0.0
    assert len(result.matching_fields) == 0
    assert len(result.mismatched_fields) == 0
