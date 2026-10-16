"""
Unit tests for Module 4 - OCR Text Extraction.
Full extract-ocr tests need an authenticated session + real stored file
(see NOTE in test_upload.py). These cover auth-gating and the field
extractor's pure regex logic, which needs no API/DB/image at all.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.ocr_field_extractor import extract_fields

CERT_BASE = "/api/v1/certificates"

SAMPLE_OCR_TEXT = """
ABC INSTITUTE OF TECHNOLOGY University
This is to certify that JOHN DOE SMITH
has successfully completed the course
Bachelor of Computer Science
Department of Computer Science
Reg No: 21CS1045
CGPA: 8.75
Percentage: 82.5%
Date of Issue: 15/06/2024
Certificate No: CERT-2024-00981
"""


@pytest.mark.asyncio
async def test_extract_ocr_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/extract-ocr")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_ocr_data_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/ocr-data")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_ocr_data_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(
            f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/ocr-data",
            json={"student_name": "Corrected Name"},
        )
    assert resp.status_code == 401


def test_extract_fields_finds_register_number():
    fields = extract_fields(SAMPLE_OCR_TEXT)
    assert fields["register_number"][0] == "21CS1045"
    assert fields["register_number"][1] > 0


def test_extract_fields_finds_cgpa_as_float():
    fields = extract_fields(SAMPLE_OCR_TEXT)
    assert fields["cgpa"][0] == 8.75
    assert isinstance(fields["cgpa"][0], float)


def test_extract_fields_finds_percentage():
    fields = extract_fields(SAMPLE_OCR_TEXT)
    assert fields["percentage"][0] == 82.5


def test_extract_fields_finds_date_of_issue():
    fields = extract_fields(SAMPLE_OCR_TEXT)
    assert fields["date_of_issue"][0] == "15/06/2024"


def test_extract_fields_finds_certificate_number():
    fields = extract_fields(SAMPLE_OCR_TEXT)
    assert fields["certificate_number"][0] == "CERT-2024-00981"


def test_extract_fields_finds_course():
    fields = extract_fields(SAMPLE_OCR_TEXT)
    assert fields["course"][0] is not None
    assert "computer science" in fields["course"][0].lower()


def test_extract_fields_missing_field_returns_none_with_zero_confidence():
    fields = extract_fields("Some unrelated text with no structured fields at all.")
    assert fields["register_number"] == (None, 0.0)
    assert fields["cgpa"] == (None, 0.0)


# ── Step 4 Regression Tests: OCR Fusion ───────────────────────────────────────

from app.services.ocr_engine import _fuse_ocr_results


def test_ocr_fusion_deduplicates_overlapping_lines():
    """Test A — Fusion: Verifies deduplication of overlapping EasyOCR and Tesseract text."""
    easy_text = "ABC INSTITUTE OF TECHNOLOGY\nJohn Doe\nReg No: 21CS1045\nCGPA: 8.75"
    tess_text = "ABC INSTITUTE OF TECHNOLOGY\nJohn Doe\nReg No: 21CS1045\nDate of Issue: 15/06/2024"

    fused_text, accuracy = _fuse_ocr_results(easy_text, 0.85, tess_text, 0.80)

    # Count line occurrences of duplicate lines
    lines = fused_text.splitlines()
    assert lines.count("ABC INSTITUTE OF TECHNOLOGY") == 1
    assert lines.count("John Doe") == 1
    assert lines.count("Reg No: 21CS1045") == 1
    # Unique Tesseract line preserved
    assert "Date of Issue: 15/06/2024" in lines

    # Field extraction works on fused text
    fields = extract_fields(fused_text)
    assert fields["register_number"][0] == "21CS1045"
    assert fields["cgpa"][0] == 8.75
    assert fields["date_of_issue"][0] == "15/06/2024"


def test_ocr_fusion_single_engine_fallback():
    """Test B — EasyOCR-only or single engine fallback."""
    easy_text = "ABC INSTITUTE OF TECHNOLOGY\nReg No: 21CS1045"

    fused_text, accuracy = _fuse_ocr_results(easy_text, 0.90, "", 0.0)
    assert fused_text == easy_text
    assert accuracy == 0.90


def test_ocr_fusion_fuzzy_duplicate_resolution():
    """Test C — Tesseract fallback & fuzzy duplicate resolution."""
    easy_text = "ABC INSTITUTE OF TECHNOLOGY\nReg No: 21CS1045"
    tess_text = "abc institute of technology\nReg No: 21CS1045\nExtra Line: 123"

    fused_text, accuracy = _fuse_ocr_results(easy_text, 0.88, tess_text, 0.75)
    lines = fused_text.splitlines()

    # Higher confidence EasyOCR line chosen for fuzzy match
    assert "ABC INSTITUTE OF TECHNOLOGY" in lines
    assert "abc institute of technology" not in lines
    assert "Extra Line: 123" in lines


def test_ocr_fusion_repeated_execution_consistency():
    """Test D — Repeated execution produces 100% deterministic output."""
    easy_text = SAMPLE_OCR_TEXT
    tess_text = SAMPLE_OCR_TEXT

    results = [_fuse_ocr_results(easy_text, 0.85, tess_text, 0.80) for _ in range(10)]

    first_text, first_acc = results[0]
    for text, acc in results[1:]:
        assert text == first_text
        assert acc == first_acc


def test_marksheet_student_name_multiline_and_singleline():
    """Unit test: verifies student name extraction when name is split across multiple lines vs single line."""
    from app.services.marksheet_field_extractor import extract_marksheet_fields

    # Case A: Split across two lines ("ROHITH" / "A")
    split_text = """
    HIGHER SECONDARY EXAMINATION
    STATEMENT OF MARKS
    NAME OF THE CANDIDATE
    ROHITH
    A
    PERMANENT REGISTER NUMBER
    2212258607
    DATE OF BIRTH
    24/01/2004
    """
    res_split = extract_marksheet_fields(split_text)
    assert res_split["fields"]["student_name"] == "ROHITH A"

    # Case B: Standard single-line name ("PRIYA SHARMA")
    single_text = """
    HIGHER SECONDARY EXAMINATION
    STATEMENT OF MARKS
    NAME OF THE CANDIDATE
    PRIYA SHARMA
    PERMANENT REGISTER NUMBER
    2212258607
    DATE OF BIRTH
    15/08/2003
    """
    res_single = extract_marksheet_fields(single_text)
    assert res_single["fields"]["student_name"] == "PRIYA SHARMA"

    # Case C: Single-line title-case name ("Johnathan Edwards")
    title_text = """
    HIGHER SECONDARY EXAMINATION
    STATEMENT OF MARKS
    NAME OF THE CANDIDATE
    Johnathan Edwards
    PERMANENT REGISTER NUMBER
    2212258607
    DATE OF BIRTH
    10/10/2002
    """
    res_title = extract_marksheet_fields(title_text)
    assert res_title["fields"]["student_name"] == "Johnathan Edwards"


