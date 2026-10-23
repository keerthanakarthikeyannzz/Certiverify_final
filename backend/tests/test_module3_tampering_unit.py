"""
Unit tests for MODULE 3: Tampering & Forgery Detection.
"""
import io
import json
import pytest
import numpy as np
import cv2
from PIL import Image

from app.core.config import settings
from app.services.tampering_detection import (
    analyze_tampering,
    TamperingContext,
    ELACheck,
    PDFStructureMetadataCheck,
    CopyMoveCheck,
    NoiseInconsistencyCheck,
    get_default_tampering_checks,
    TamperingResult,
)


def test_pluggable_checks_registered_and_executed():
    """Verify all default tampering checks are registered and executable."""
    checks = get_default_tampering_checks()
    names = [c.name for c in checks]
    expected = [
        "ela",
        "pdf_metadata_structure",
        "copy_move",
        "noise_inconsistency",
        "font_layout",
        "image_quality",
        "signature_seal",
        "document_structure",
    ]
    for exp in expected:
        assert exp in names, f"Expected check {exp} not found in default checks list"


def test_ela_check_fair_compression_normalization():
    """Verify that a uniform noisy scan has low anomaly disparity compared to a localized edit."""
    # 1. Uniform baseline noise (simulating a scan)
    np.random.seed(42)
    uniform_scan = np.full((300, 300, 3), 220, dtype=np.uint8)
    noise = np.random.normal(0, 10, (300, 300, 3)).astype(np.int16)
    uniform_scan = np.clip(uniform_scan.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    ctx_uniform = TamperingContext(b"fake_bytes", "jpg", uniform_scan)
    res_uniform = ELACheck().run(ctx_uniform)
    assert res_uniform.score < 25.0, f"Uniform scan should have low normalized score, got {res_uniform.score}"

    # 2. Localized spliced patch (simulating tampering)
    tampered_scan = uniform_scan.copy()
    cv2.rectangle(tampered_scan, (100, 100), (180, 180), (255, 255, 255), -1)
    cv2.putText(tampered_scan, "ALTERED", (105, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    ctx_tampered = TamperingContext(b"fake_bytes", "jpg", tampered_scan)
    res_tampered = ELACheck().run(ctx_tampered)
    assert res_tampered.score > res_uniform.score, "Tampered scan should yield higher ELA anomaly score"
    assert "_heatmap_png" in res_tampered.detail


def test_pdf_metadata_producer_flagged_as_signal():
    """Verify editing tools in metadata are flagged as signals."""
    # Create fake image bytes with EXIF Software: Adobe Photoshop
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    exif = img.getexif()
    exif[305] = "Adobe Photoshop 2024"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    img_bytes = buf.getvalue()

    ctx = TamperingContext(img_bytes, "jpg", np.zeros((100, 100, 3), dtype=np.uint8))
    res = PDFStructureMetadataCheck().run(ctx)
    assert res.score >= 50.0
    assert any("photoshop" in f.lower() for f in res.flags)
    assert res.detail["status"] in ("WARNING", "MINOR_WARNING")


def test_false_positive_mitigation_metadata_only_caps_confidence():
    """
    When only metadata signals are detected but no localized image tampering
    (ELA, copy_move, noise) is present, confidence should be capped at
    TAMPERING_METADATA_ONLY_CONFIDENCE_CAP.
    """
    # Create image with Photoshop EXIF but clean uniform image content
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    exif = img.getexif()
    exif[305] = "Adobe Photoshop 2024"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    img_bytes = buf.getvalue()

    clean_img_array = np.full((200, 200, 3), 255, dtype=np.uint8)

    result = analyze_tampering(img_bytes, "jpg", clean_img_array, allow_pdf_text_layer_check=False)

    assert result.confidence <= settings.TAMPERING_METADATA_ONLY_CONFIDENCE_CAP
    assert any("typical for re-saved scans" in f.lower() or "metadata indicates" in f.lower() for f in result.flags)


def test_optional_noise_inconsistency_check():
    """Verify noise inconsistency check analyzes tiles and detects discrepancies."""
    # Clean image with uniform noise
    clean_img = np.full((300, 300, 3), 200, dtype=np.uint8)
    ctx_clean = TamperingContext(b"fake", "png", clean_img)
    res_clean = NoiseInconsistencyCheck().run(ctx_clean)
    assert res_clean.score == 0.0 or res_clean.status == "NORMAL"

    # Image with spliced patch of high noise
    noisy_patch_img = clean_img.copy()
    noisy_patch = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    noisy_patch_img[100:200, 100:200] = noisy_patch
    ctx_noisy = TamperingContext(b"fake", "png", noisy_patch_img)
    res_noisy = NoiseInconsistencyCheck().run(ctx_noisy)
    assert res_noisy.score > res_clean.score


def test_risk_level_bands_classification():
    """Verify composite score correctly maps to risk levels LOW / MEDIUM / HIGH."""
    from app.services.tampering_detection import _parse_risk_bands
    bands = _parse_risk_bands('{"LOW": 25.0, "MEDIUM": 60.0, "HIGH": 100.0}')
    assert bands[0] == (25.0, "LOW")
    assert bands[1] == (60.0, "MEDIUM")
    assert bands[2] == (100.0, "HIGH")
