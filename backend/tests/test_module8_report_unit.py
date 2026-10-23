"""
Unit tests for MODULE 8: PDF Report Generation Stage (report).
Tests:
1. Verification ID format (human-readable, non-guessable CV-YYYY-XXXXXXXX).
2. QR Code flowable generation.
3. PDF generation from stored results (including missing stages handled as 'Not evaluated').
4. Detached HMAC-SHA256 digital signature computation.
5. Verification of untampered PDF -> True.
6. Altered PDF byte tamper detection -> False.
7. Production refusal when REPORT_SIGNING_KEY is missing in production mode.
8. Development warning & fallback when REPORT_SIGNING_KEY is missing in development.
"""
import io
import os
import tempfile
import pytest
from unittest.mock import patch

from app.core.config import settings
from app.services.report_service import (
    make_verification_id,
    generate_verification_qr_flowable,
    generate_report_pdf,
    compute_report_signature,
    verify_report_signature,
    get_report_signing_key,
)


def test_verification_id_format():
    vid1 = make_verification_id()
    vid2 = make_verification_id()
    assert vid1.startswith("CV-")
    assert len(vid1) >= 15  # CV-YYYY-XXXXXXXX
    assert vid1 != vid2  # non-guessable, unique


def test_qr_flowable_generation():
    flowable = generate_verification_qr_flowable("CV-2026-TEST1234")
    assert flowable is not None
    assert flowable.drawWidth > 0
    assert flowable.drawHeight > 0


def test_pdf_generation_full_and_not_evaluated():
    cert = {
        "id": "cert-1234",
        "original_filename": "diploma_test.pdf",
        "file_type": "pdf",
        "file_size_bytes": 102400,
        "sha256_hash": "a" * 64,
        "uploaded_at": "2026-10-17 12:00 UTC",
    }
    report_meta = {
        "verification_id": "CV-2026-ABCD1234",
        "generated_at": "2026-10-17 12:05 UTC",
        "verifier_name": "Auditor Test",
        "verifier_email": "auditor@certiverify.ai",
        "organization_name": "CertiVerify Enterprise",
        "digital_signature": "simulated_sig_hex",
    }

    # Case 1: Minimal/Empty stages -> must render 'Not evaluated' with reasons without failing
    pdf_bytes_empty = generate_report_pdf(
        cert=cert,
        doc_type_row=None,
        ocr_row=None,
        comparison_row=None,
        verification_row=None,
        fraud_row=None,
        trust_row=None,
        prediction_row=None,
        report_row=report_meta,
    )
    assert pdf_bytes_empty.startswith(b"%PDF-")
    assert len(pdf_bytes_empty) > 2000

    # Case 2: Full stored stages
    doc_type = {
        "predicted_type": "degree_certificate",
        "confidence_score": 0.95,
        "model_used": "Pattern Classifier",
    }
    ocr = {
        "student_name": "Alice Doe",
        "university_name": "State University",
        "register_number": "REG-9999",
        "roll_number": "12345",
        "certificate_number": "CERT-8888",
        "department": "Computer Science",
        "course": "B.Tech",
        "cgpa": "9.2",
        "percentage": None,
        "date_of_issue": "2025-05-20",
        "has_signature": True,
        "has_seal": True,
        "ocr_accuracy": 0.98,
        "ocr_engine": "Tesseract OCR",
        "raw_text": "This is to certify that Alice Doe has conferred the degree of B.Tech...",
    }
    verification = {
        "qr_present": True,
        "qr_valid": True,
        "qr_warning": "Trusted domain verified",
        "cross_validation_status": "MATCH",
        "cross_validation_mismatches": [],
        "blockchain_status": "verified",
        "hash_match_status": "MATCH",
        "blockchain_hash_submitted": "a" * 64,
        "blockchain_hash_onchain": "a" * 64,
        "blockchain_tx_hash": "0x" + "b" * 64,
        "tampering_score": 12.5,
        "tampering_risk_level": "LOW_RISK",
        "tampering_confidence": 92.0,
        "tampering_detail": {
            "image_quality": {"score": 95.0, "status": "EXCELLENT"},
            "ela": {"score": 10.0, "status": "CLEAN"},
            "copy_paste": {"detected": False},
            "font_consistency": {"score": 90.0, "status": "CONSISTENT"},
            "signature": {"detected": True, "anomaly_score": 5.0},
            "seal": {"detected": True, "anomaly_score": 5.0},
            "metadata": {"status": "INTEGRITY_VERIFIED"},
        },
        "tampering_flags": [],
        "is_duplicate": False,
        "duplicate_match_reason": "Unique document in institutional database",
        "duplicate_of_certificate_id": None,
    }
    fraud = {
        "fraud_probability": 0.08,
        "ocr_accuracy_weight": 0.15,
        "comparison_weight": 0.10,
        "qr_weight": 0.15,
        "blockchain_weight": 0.15,
        "tampering_weight": 0.15,
        "duplicate_weight": 0.10,
        "metadata_integrity_weight": 0.05,
        "image_quality_weight": 0.10,
    }
    trust = {
        "score": 94.5,
        "breakdown": {
            "coverage": 1.0,
            "components": {
                "ocr_accuracy": {"value": 98.0, "weight": 0.15, "contribution": 14.7, "status": "EVALUATED", "reason": "High OCR confidence"},
                "comparison": {"value": None, "weight": 0.10, "contribution": 0.0, "status": "NOT_EVALUATED", "reason": "Requires group upload"},
                "qr_verification": {"value": 100.0, "weight": 0.15, "contribution": 15.0, "status": "EVALUATED", "reason": "QR verified"},
                "blockchain": {"value": 100.0, "weight": 0.15, "contribution": 15.0, "status": "EVALUATED", "reason": "Blockchain verified"},
                "tampering": {"value": 87.5, "weight": 0.15, "contribution": 13.1, "status": "EVALUATED", "reason": "Clean forensic signals"},
                "duplicate": {"value": 100.0, "weight": 0.10, "contribution": 10.0, "status": "EVALUATED", "reason": "Unique document"},
                "fraud_probability": {"value": 92.0, "weight": 0.10, "contribution": 9.2, "status": "EVALUATED", "reason": "Low fraud risk"},
                "image_quality": {"value": 95.0, "weight": 0.10, "contribution": 9.5, "status": "EVALUATED", "reason": "High resolution scan"},
            },
        },
    }
    prediction = {
        "label": "genuine",
        "confidence_score": 0.96,
        "explanation": "All critical forensic checks passed: QR verified, blockchain hash matched, no duplicate collision, clean tampering score.",
        "recommended_action": "Accept certificate — credential verified against institutional standards.",
    }

    pdf_bytes_full = generate_report_pdf(
        cert=cert,
        doc_type_row=doc_type,
        ocr_row=ocr,
        comparison_row=None,
        verification_row=verification,
        fraud_row=fraud,
        trust_row=trust,
        prediction_row=prediction,
        report_row=report_meta,
    )
    assert pdf_bytes_full.startswith(b"%PDF-")
    assert len(pdf_bytes_full) > len(pdf_bytes_empty)


def test_signature_and_tamper_detection():
    data = b"%PDF-1.4 simulated pdf document content with cryptographic seal"
    sig = compute_report_signature(data, key="test-signing-key-1234")
    assert isinstance(sig, str)
    assert len(sig) == 64  # HMAC-SHA256 hex string

    # 1. Untampered verification succeeds
    assert verify_report_signature(data, sig, key="test-signing-key-1234") is True

    # 2. File verification succeeds
    with tempfile.NamedTemporaryFile("wb", delete=False) as f:
        f.write(data)
        temp_path = f.name

    try:
        assert verify_report_signature(temp_path, sig, key="test-signing-key-1234") is True

        # 3. Alter 1 byte of the PDF
        with open(temp_path, "wb") as f:
            f.write(data[:-1] + b"X")  # change last byte

        # 4. Tampered PDF MUST fail verification
        assert verify_report_signature(temp_path, sig, key="test-signing-key-1234") is False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_production_refusal_when_key_missing():
    with patch.object(settings, "ENV", "production"):
        with patch.object(settings, "REPORT_SIGNING_KEY", None):
            with pytest.raises(RuntimeError) as exc_info:
                get_report_signing_key()
            assert "REPORT_SIGNING_KEY is not configured in production" in str(exc_info.value)


def test_development_warning_and_fallback():
    with patch.object(settings, "ENV", "development"):
        with patch.object(settings, "REPORT_SIGNING_KEY", None):
            key = get_report_signing_key()
            assert key == settings.SECRET_KEY
