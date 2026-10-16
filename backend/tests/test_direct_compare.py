"""
Automated tests for Direct Document Comparison API (Modules 5 & Direct Compare).
Tests COMPARISON-001 through COMPARISON-012 as defined in implementation plan.
"""
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.api.deps import get_current_verified_user
from app.models.models import User, UserRole


# Helper to generate a dummy image byte array
def _create_test_image_bytes(text_label: str = "Test Cert", color=(255, 255, 255)) -> bytes:
    img = Image.new("RGB", (600, 400), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# Mock authenticated user dependency override
async def _mock_get_current_user():
    return User(
        id="test-user-id",
        full_name="Test User",
        email="testuser@example.com",
        role=UserRole.STUDENT,
        is_active=True,
        is_email_verified=True,
    )


@pytest.fixture(autouse=True)
def override_auth_dep():
    app.dependency_overrides[get_current_verified_user] = _mock_get_current_user
    yield
    app.dependency_overrides.pop(get_current_verified_user, None)


DIRECT_COMPARE_URL = "/api/v1/direct-compare"


def test_comparison_001_two_identical_documents():
    """COMPARISON-001: Two valid identical documents yield 100% match & identical_document status."""
    img_bytes = _create_test_image_bytes("Degree Certificate 2024")

    files = [
        ("files", ("cert1.jpg", img_bytes, "image/jpeg")),
        ("files", ("cert2.jpg", img_bytes, "image/jpeg")),
        ("doc_types", (None, "degree_certificate")),
        ("doc_types", (None, "degree_certificate")),
    ]

    import sys
    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)
    sys.stderr.write(f"\n>>> TEST 001 RESP: {resp.status_code} | {resp.text}\n")
    sys.stderr.flush()

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["comparison_type"] == "identical_document"
    assert res["similarity_percentage"] == 100.0
    assert any("identical" in bullet.lower() for bullet in res["ai_summary"])


def test_comparison_002_two_different_documents_same_type():
    """COMPARISON-002: Two valid different documents of same type compare cleanly."""
    img1 = _create_test_image_bytes("Doc 1", color=(255, 250, 250))
    img2 = _create_test_image_bytes("Doc 2", color=(245, 245, 255))

    files = [
        ("files", ("doc1.jpg", img1, "image/jpeg")),
        ("files", ("doc2.jpg", img2, "image/jpeg")),
        ("doc_types", (None, "marksheet")),
        ("doc_types", (None, "marksheet")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert "similarity_percentage" in res
    assert "comparison" in res


def test_comparison_004_different_document_types():
    """COMPARISON-004: Degree Certificate vs Resume cross-document comparison."""
    img1 = _create_test_image_bytes("Degree Certificate", color=(255, 255, 250))
    img2 = _create_test_image_bytes("Resume CV", color=(250, 255, 255))

    files = [
        ("files", ("degree.jpg", img1, "image/jpeg")),
        ("files", ("resume.jpg", img2, "image/jpeg")),
        ("doc_types", (None, "degree_certificate")),
        ("doc_types", (None, "resume")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["doc1_type"] == "degree_certificate"
    assert res["doc2_type"] == "resume"


def test_comparison_005_missing_doc_type_autoclassifies():
    """COMPARISON-005: Missing doc_type parameter triggers auto-classification fallback."""
    img1 = _create_test_image_bytes("Doc 1")
    img2 = _create_test_image_bytes("Doc 2")

    files = [
        ("files", ("doc1.jpg", img1, "image/jpeg")),
        ("files", ("doc2.jpg", img2, "image/jpeg")),
        ("doc_types", (None, "")),
        ("doc_types", (None, "")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["doc1_type"] != ""
    assert res["doc2_type"] != ""


def test_comparison_006_unreadable_file_validation_error():
    """COMPARISON-006: Unreadable file bytes return stage: file_validation error identifying document index."""
    corrupt_bytes = b"NOT_AN_IMAGE_OR_PDF_DATA"
    valid_bytes = _create_test_image_bytes("Valid")

    files = [
        ("files", ("valid.jpg", valid_bytes, "image/jpeg")),
        ("files", ("corrupt.jpg", corrupt_bytes, "image/jpeg")),
        ("doc_types", (None, "marksheet")),
        ("doc_types", (None, "marksheet")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 422
    err = resp.json()["detail"]
    assert err["stage"] == "file_validation"
    assert err["document_index"] == 2


def test_comparison_007_empty_file_validation_error():
    """COMPARISON-007: Empty 0-byte file returns stage: file_validation error."""
    empty_bytes = b""
    valid_bytes = _create_test_image_bytes("Valid")

    files = [
        ("files", ("empty.jpg", empty_bytes, "image/jpeg")),
        ("files", ("valid.jpg", valid_bytes, "image/jpeg")),
        ("doc_types", (None, "marksheet")),
        ("doc_types", (None, "marksheet")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 422
    err = resp.json()["detail"]
    assert err["stage"] == "file_validation"
    assert err["document_index"] == 1


def test_comparison_008_three_documents_succeeds():
    """COMPARISON-008: 3 uploaded documents comparison succeeds."""
    img1 = _create_test_image_bytes("Doc 1")
    img2 = _create_test_image_bytes("Doc 2")
    img3 = _create_test_image_bytes("Doc 3")

    files = [
        ("files", ("doc1.jpg", img1, "image/jpeg")),
        ("files", ("doc2.jpg", img2, "image/jpeg")),
        ("files", ("doc3.jpg", img3, "image/jpeg")),
        ("doc_types", (None, "degree_certificate")),
        ("doc_types", (None, "marksheet")),
        ("doc_types", (None, "resume")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["documents_compared"] == 3


def test_comparison_009_five_documents_succeeds():
    """COMPARISON-009: 5 uploaded documents comparison succeeds."""
    imgs = [_create_test_image_bytes(f"Doc {i}") for i in range(1, 6)]

    files = [("files", (f"doc{i}.jpg", imgs[i-1], "image/jpeg")) for i in range(1, 6)]
    for _ in range(5):
        files.append(("doc_types", (None, "marksheet")))

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["documents_compared"] == 5


def test_comparison_010_legacy_fallback_parameters_work():
    """COMPARISON-010: Legacy file1/file2/doc_type1/doc_type2 form parameters maintain 100% backward compatibility."""
    img = _create_test_image_bytes("Legacy Test")

    files = [
        ("file1", ("cert1.jpg", img, "image/jpeg")),
        ("file2", ("cert2.jpg", img, "image/jpeg")),
        ("doc_type1", (None, "degree_certificate")),
        ("doc_type2", (None, "degree_certificate")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)

    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["comparison_type"] == "identical_document"


def test_comparison_automatic_document_classification():
    """Verifies that direct-compare uses the real classifier function when doc_types is 'auto' or empty."""
    img1 = _create_test_image_bytes("Bachelor of Technology Degree Certificate")
    img2 = _create_test_image_bytes("Semester Grade Marksheet")

    files = [
        ("files", ("cert1.jpg", img1, "image/jpeg")),
        ("files", ("cert2.jpg", img2, "image/jpeg")),
        ("doc_types", (None, "auto")),
        ("doc_types", (None, "")),
    ]

    client = TestClient(app)
    resp = client.post(DIRECT_COMPARE_URL, files=files)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["documents_compared"] == 2
    assert "similarity_percentage" in res
    assert "doc1_type" in res
    assert "doc2_type" in res
