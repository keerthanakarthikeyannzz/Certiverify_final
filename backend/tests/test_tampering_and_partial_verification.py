"""
Tests for Tampering Analysis & Partial Verification Requirements (TASK 4).

1. Tampering runs on a PDF and an image and returns analyzed status and scores.
2. Missing or failed checks yield "Partial verification: N of M checks completed"
   and exclude the check from trust score weighting.
3. A missing critical check (e.g. tampering unavailable/unrun) prevents a confident "genuine"
   verdict and yields "inconclusive / needs review".
"""
import os
import pytest
import fitz

from app.services.tampering_detection import analyze_tampering, TamperingResult
from app.services.image_preprocessing import load_image_as_array, preprocess_pipeline
from app.services.trust_score import compute_trust_score, TrustScoreInputs
from app.services.final_prediction import predict, PredictionInputs


PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "sample_certificate.pdf")


def test_tampering_runs_on_pdf_and_image():
    """Verify tampering analysis executes on real PDF and rendered image."""
    assert os.path.exists(PDF_PATH), f"sample_certificate.pdf not found at {PDF_PATH}"
    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

    # 1. Run on PDF
    pdf_img = load_image_as_array(pdf_bytes, "pdf")
    pdf_processed = preprocess_pipeline(pdf_img)
    pdf_result = analyze_tampering(pdf_bytes, "pdf", pdf_processed)

    assert isinstance(pdf_result, TamperingResult)
    assert pdf_result.status in ("analyzed", "not_applicable_for_pdf_text_layer")
    assert pdf_result.score is not None
    assert 0.0 <= pdf_result.score <= 100.0
    assert pdf_result.risk_level in ("LOW", "MEDIUM", "HIGH")

    # 2. Render Page 1 as PNG at 200 dpi and run
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    zoom = 200 / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()

    png_img = load_image_as_array(png_bytes, "png")
    png_processed = preprocess_pipeline(png_img)
    png_result = analyze_tampering(png_bytes, "png", png_processed)

    assert isinstance(png_result, TamperingResult)
    assert png_result.status == "analyzed"
    assert png_result.score is not None
    assert 0.0 <= png_result.score <= 100.0
    assert png_result.risk_level in ("LOW", "MEDIUM", "HIGH")


def test_tampering_pure_text_layer_status():
    """Verify a purely vector digital PDF without images returns specific status."""
    # Create an in-memory PDF with only text and vector drawings (no raster images)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Official Degree Certificate\nName: John Doe\nDegree: Bachelor of Science")
    page.draw_rect(fitz.Rect(50, 50, 500, 700), color=(0, 0, 1), width=2)
    pure_pdf_bytes = doc.tobytes()
    doc.close()

    pure_img = load_image_as_array(pure_pdf_bytes, "pdf")
    pure_processed = preprocess_pipeline(pure_img)
    result = analyze_tampering(pure_pdf_bytes, "pdf", pure_processed)

    assert result.status == "not_applicable_for_pdf_text_layer"
    assert result.score in (0.0, None)
    assert result.risk_level in ("NOT_APPLICABLE", "LOW")


def test_unavailable_or_failed_check_excluded_from_weighting():
    """When a check is unavailable or failed, do not count as pass, exclude from weighting."""
    # Inputs with tampering unavailable
    inputs_unavail = TrustScoreInputs(
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_status="unavailable",
        tampering_score=None,
    )
    result_unavail = compute_trust_score(inputs_unavail)
    assert result_unavail.breakdown["tampering"] == 0.0
    assert result_unavail.evidence_breakdown["tampering"]["display_status"] == "UNAVAILABLE"
    assert "Partial verification:" in result_unavail.partial_verification_note
    assert result_unavail.checks_completed < result_unavail.checks_total

    # Inputs with tampering failed
    inputs_failed = TrustScoreInputs(
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_status="failed: OpenCV out of memory",
        tampering_score=None,
    )
    result_failed = compute_trust_score(inputs_failed)
    assert result_failed.breakdown["tampering"] == 0.0
    assert result_failed.evidence_breakdown["tampering"]["display_status"] == "FAILED"
    assert "Partial verification:" in result_failed.partial_verification_note


def test_missing_critical_check_yields_inconclusive_verdict_instead_of_genuine():
    """
    A verdict can be 'genuine' only if critical checks ran.
    When a critical check is missing/unavailable, high trust score must NOT yield
    a confident 'genuine', but 'inconclusive / needs review'.
    """
    # High score (95.0), low fraud (0.02), but tampering is unrun / unavailable
    incomplete_inputs = PredictionInputs(
        trust_score=95.0,
        data_completeness=0.6,
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_score=None,
        tampering_status="unavailable",
        fraud_probability=0.02,
    )
    incomplete_result = predict(incomplete_inputs)

    assert incomplete_result.label in ("inconclusive", "inconclusive / needs review")
    assert "Partial verification:" in incomplete_result.explanation or any(
        "Partial verification:" in r for r in incomplete_result.reasons
    )
    assert "inconclusive" in incomplete_result.recommended_action.lower()

    # Once tampering check is provided and passed, it can be genuine
    complete_inputs = PredictionInputs(
        trust_score=95.0,
        data_completeness=1.0,
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_score=5.0,
        tampering_status="analyzed",
        fraud_probability=0.02,
    )
    complete_result = predict(complete_inputs)
    assert complete_result.label == "genuine"


def test_text_only_pdf_requires_verified_qr_or_blockchain_for_genuine():
    """
    For text-only PDFs (status not_applicable_for_pdf_text_layer):
    require a verified QR on a trusted domain or a blockchain match to allow 'genuine';
    otherwise return 'inconclusive'.
    """
    # 1. Text-only PDF without verified QR or blockchain match -> must return inconclusive
    no_anchor_inputs = PredictionInputs(
        trust_score=95.0,
        data_completeness=0.9,
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_score=None,
        tampering_status="not_applicable_for_pdf_text_layer",
        blockchain_status="not_found",
        qr_present=False,
        fraud_probability=0.02,
    )
    res_no_anchor = predict(no_anchor_inputs)
    assert res_no_anchor.label in ("inconclusive", "inconclusive / needs review")

    # 2. Text-only PDF with verified QR on trusted domain -> allows genuine
    qr_anchor_inputs = PredictionInputs(
        trust_score=95.0,
        data_completeness=1.0,
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_score=None,
        tampering_status="not_applicable_for_pdf_text_layer",
        qr_present=True,
        qr_valid=True,
        fraud_probability=0.02,
    )
    res_qr = predict(qr_anchor_inputs)
    assert res_qr.label == "genuine"

    # 3. Text-only PDF with blockchain match -> allows genuine
    bc_anchor_inputs = PredictionInputs(
        trust_score=95.0,
        data_completeness=1.0,
        ocr_accuracy=0.95,
        is_duplicate=False,
        tampering_score=None,
        tampering_status="not_applicable_for_pdf_text_layer",
        blockchain_status="verified",
        qr_present=False,
        fraud_probability=0.02,
    )
    res_bc = predict(bc_anchor_inputs)
    assert res_bc.label == "genuine"
