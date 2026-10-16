"""
MODULE 6 - AI VERIFICATION: TAMPERING DETECTION (Enhanced — Priority 6)

Implements the full multi-signal tampering analysis workflow:

  PART A  — Image Quality Analysis (resolution, blur, noise, contrast,
             brightness)
  PART B  — ELA / Compression Analysis (resave + diff)
  PART C  — Copy-Paste / Clone Detection (ORB offset clustering + region boxes)
  PART D  — Font / Text Consistency (bbox-level deviation from median)
  PART F  — Signature Region Analysis
  PART G  — Seal / Stamp Analysis
  PART H  — Metadata Analysis (enhanced: PDF + EXIF)
  PART I  — Document Structure Awareness (field presence by doc type)
  PART J  — Multi-Signal Tampering Score (configurable weights)
  PART K  — Risk-level classification
  PART L  — Structured per-finding evidence with confidence
  PART M  — Final structured result in TamperingResult.detail

Design principles (unchanged from original):
  - No single weak signal auto-classifies as Fake
  - Results are labelled for human review, not hard verdicts
  - Resume documents use relaxed structural rules
  - Existing TamperingResult dataclass API preserved (score, flags,
    ela_heatmap_png) — new fields are additive only
"""
from __future__ import annotations

import io
import logging
import time
from collections import Counter
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

logger = logging.getLogger("certiverify.tampering")

# ---------------------------------------------------------------------------
# Configurable signal weights (PART J) — must sum to 1.0
# Aligned to Priority 6 spec:
#   Image manipulation  15%  (image_quality)
#   ELA/compression     15%  (ela)
#   Copy-paste          20%  (copy_paste)
#   Text/font           15%  (font_text)
#   Signature           10%  (signature)
#   Seal                10%  (seal)
#   Metadata             5%  (metadata)
#   Document structure  10%  (document_structure)
# ---------------------------------------------------------------------------
SIGNAL_WEIGHTS: dict[str, float] = {
    "image_quality":      0.15,
    "ela":                0.15,
    "copy_paste":         0.20,
    "font_text":          0.15,
    "signature":          0.10,
    "seal":               0.10,
    "metadata":           0.05,
    "document_structure": 0.10,
}

# Risk-level thresholds (PART K)
_RISK_LEVELS = [
    (20,  "LOW"),
    (40,  "MINOR_ANOMALIES"),
    (60,  "MODERATE_RISK"),
    (80,  "HIGH_RISK"),
    (101, "VERY_HIGH_RISK"),
]

# Editing software to flag in metadata (PART H)
_EDITING_TOOLS = [
    "photoshop", "gimp", "illustrator", "affinity",
    "canva", "paint.net", "pixelmator",
]

# Expected fields by document type (PART I)
_DOC_STRUCTURE: dict[str, list[str]] = {
    "degree_certificate":   ["student_name", "university_name", "course", "certificate_number"],
    "diploma":              ["student_name", "university_name", "course"],
    "marksheet":            ["student_name", "register_number"],
    "sslc":                 ["student_name", "register_number"],
    "hsc":                  ["student_name", "register_number"],
    "sslc_marksheet":       ["student_name", "register_number"],
    "hsc_marksheet":        ["student_name", "register_number"],
    "aadhaar_card":         ["student_name"],
    "transfer_certificate": ["student_name", "university_name"],
    "resume":               [],   # no strict rules — flexible layout
}


# ---------------------------------------------------------------------------
# Data classes (additive — new fields do not break existing callers)
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """PART L — structured finding with evidence, score, confidence, status."""
    type: str
    status: str          # DETECTED | WARNING | NORMAL | UNAVAILABLE
    score: float         # 0-100 contribution from this signal
    confidence: float    # 0-100
    reason: str
    regions: list | None = None   # [{x, y, w, h}] for copy-paste


@dataclass
class TamperingResult:
    """Preserved public API + additive new fields (PART M)."""
    score: float                                         # 0-100 composite score
    flags: list[str] = field(default_factory=list)
    ela_heatmap_png: bytes | None = None

    # Additive new fields
    risk_level: str = "UNKNOWN"
    confidence: float = 0.0
    status: str = "analyzed"                             # analyzed | not_applicable_for_pdf_text_layer | failed: <reason>
    image_quality: dict = field(default_factory=dict)
    ela: dict = field(default_factory=dict)
    copy_paste: dict = field(default_factory=dict)
    font_consistency: dict = field(default_factory=dict)
    text_analysis: dict = field(default_factory=dict)   # PART E — text layout / alignment
    signature: dict = field(default_factory=dict)
    seal: dict = field(default_factory=dict)
    metadata_detail: dict = field(default_factory=dict)
    document_structure: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point — backward-compatible signature, new optional params
# ---------------------------------------------------------------------------

def is_pdf_pure_text_layer(file_bytes: bytes, file_type: str) -> bool:
    """Detect if a PDF is a native vector text document with no raster images to manipulate."""
    ft = file_type.lower().lstrip(".")
    if ft != "pdf" or not file_bytes:
        return False
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        has_text = any(len(p.get_text().strip()) > 30 for p in doc)
        has_images = any(len(p.get_images()) > 0 for p in doc)
        doc.close()
        return has_text and not has_images
    except Exception:
        return False


def analyze_tampering(
    file_bytes: bytes,
    file_type: str,
    image: np.ndarray,
    doc_type: str | None = None,
    ocr_fields: dict | None = None,
    bbox_results: list | None = None,
    allow_pdf_text_layer_check: bool = True,
) -> TamperingResult:
    """
    Full multi-signal tampering analysis.

    Parameters
    ----------
    file_bytes   : Raw file bytes (metadata + ELA)
    file_type    : 'pdf' | 'jpg' | 'jpeg' | 'png'
    image        : Preprocessed BGR numpy array
    doc_type     : Optional document type (for structure check, PART I)
    ocr_fields   : Optional OCR-extracted fields dict (for structure check)
    bbox_results : Optional OCR bounding boxes (for font consistency, PART D)
    allow_pdf_text_layer_check : If True, pure digital PDF with no raster images returns 'not_applicable_for_pdf_text_layer'
    """
    if allow_pdf_text_layer_check and is_pdf_pure_text_layer(file_bytes, file_type):
        meta = _check_metadata_full(file_bytes, file_type)
        return TamperingResult(
            score=0.0,
            flags=["Image forensics not applicable: digital PDF vector text layer with no raster images"],
            ela_heatmap_png=None,
            risk_level="NOT_APPLICABLE",
            confidence=95.0,
            status="not_applicable_for_pdf_text_layer",
            metadata_detail=meta,
            findings=[Finding("metadata", meta["status"], meta["score"], 95, "Digital vector PDF text layer")],
        )

    t_start = time.time()
    flags: list[str] = []
    findings: list[Finding] = []
    signal_scores: dict[str, float] = {}

    # ── PART A: Image Quality ────────────────────────────────────────────────
    iq = _analyze_image_quality(image)
    signal_scores["image_quality"] = max(0.0, 100.0 - iq["score"])
    if iq["score"] < 40:
        flags.append(
            f"Low image quality (score {iq['score']:.0f}/100) — "
            f"{iq['detail']} (low quality alone does NOT indicate forgery)"
        )
        findings.append(Finding("image_quality", "WARNING", iq["score"], 90, iq["detail"]))
    else:
        findings.append(Finding("image_quality", "NORMAL", iq["score"], 90,
                                "Image quality acceptable for analysis"))

    # ── PART H: Metadata (cheap — run before expensive CV ops) ──────────────
    meta = _check_metadata_full(file_bytes, file_type)
    signal_scores["metadata"] = meta["score"]
    if meta["anomalies"]:
        flags.extend(meta["anomalies"])
        findings.append(Finding("metadata", meta["status"], meta["score"], 95,
                                "; ".join(meta["anomalies"])))
    else:
        findings.append(Finding("metadata", "NORMAL", 0, 90,
                                "No metadata anomalies detected"))

    # ── PART B: ELA ──────────────────────────────────────────────────────────
    ela_array, ela_score = compute_ela(image)
    ela_risk = _ela_risk(ela_score)
    signal_scores["ela"] = ela_risk
    if ela_risk > 30:
        msg = (f"Elevated ELA score ({ela_score:.1f}) — possible recompression "
               "or localized editing artifacts")
        flags.append(msg)
        findings.append(Finding("ela", "POSSIBLE_MANIPULATION", ela_score, 70, msg))
    else:
        findings.append(Finding("ela", "NORMAL", ela_score, 80,
                                "ELA shows normal compression distribution"))

    # ── PART C: Copy-Paste / Clone ───────────────────────────────────────────
    clone_count, clone_regions = _detect_clone_regions_with_boxes(image)
    cp_risk = _clone_risk(clone_count)
    signal_scores["copy_paste"] = cp_risk
    if clone_count >= 15:
        msg = (f"Copy-paste anomaly: {clone_count} keypoint pairs share a "
               "consistent spatial offset — possible duplicated region")
        flags.append(msg)
        findings.append(Finding("copy_paste", "DETECTED", cp_risk, 65, msg,
                                regions=clone_regions))
    else:
        findings.append(Finding("copy_paste", "NORMAL", cp_risk, 70,
                                "No significant copy-paste clusters detected"))

    # ── PART D: Font / Text Consistency ─────────────────────────────────────
    font_result = _analyze_font_consistency(image, bbox_results)
    font_risk = max(0.0, 100.0 - font_result["score"])
    signal_scores["font_text"] = font_risk
    if font_result["status"] == "POSSIBLE_EDIT":
        msg = (f"Font/text inconsistency (score {font_result['score']:.0f}/100) — "
               "text regions differ in apparent size or spacing")
        flags.append(msg)
        findings.append(Finding("font_consistency", "POSSIBLE_EDIT", font_result["score"],
                                60, msg))
    else:
        findings.append(Finding("font_consistency", "CONSISTENT", font_result["score"],
                                75, "Text regions appear visually consistent"))

    # ── PART E: Text Layout / Alignment Analysis ─────────────────────────────
    text_result = _analyze_text_layout(image)
    if text_result["status"] == "ANOMALOUS":
        msg = (f"Text layout anomaly (score {text_result['score']:.0f}/100) — "
               "irregular baseline spacing or unusual text density distribution")
        flags.append(msg)
        findings.append(Finding("text_analysis", "ANOMALOUS", text_result["score"], 55, msg))
    else:
        findings.append(Finding("text_analysis", "NORMAL", text_result["score"], 70,
                                "Text alignment and density appear normal"))
    # Blend text layout into the font_text signal (they share weight)
    text_anomaly = max(0.0, 100.0 - text_result["score"])
    signal_scores["font_text"] = min(
        (signal_scores.get("font_text", 0) + text_anomaly) / 2.0, 100.0
    )

    # ── PART F: Signature Analysis ───────────────────────────────────────────
    sig_result = _analyze_signature(image)
    signal_scores["signature"] = sig_result["anomaly_score"]
    if sig_result["anomaly_score"] > 30:
        flags.append(
            f"Signature anomaly (score {sig_result['anomaly_score']:.0f}) — "
            "visual inconsistency in signature region"
        )
    findings.append(Finding(
        "signature",
        "DETECTED" if sig_result["detected"] else "NOT_FOUND",
        sig_result["anomaly_score"], 55, sig_result["reason"],
    ))

    # ── PART G: Seal / Stamp Analysis ────────────────────────────────────────
    seal_result = _analyze_seal(image)
    signal_scores["seal"] = seal_result["anomaly_score"]
    if seal_result["anomaly_score"] > 30:
        flags.append(
            f"Seal/stamp anomaly (score {seal_result['anomaly_score']:.0f}) — "
            "visual inconsistency in seal region"
        )
    findings.append(Finding(
        "seal",
        "DETECTED" if seal_result["detected"] else "NOT_FOUND",
        seal_result["anomaly_score"], 50, seal_result["reason"],
    ))

    # ── PART I: Document Structure ────────────────────────────────────────────
    struct_result = _check_document_structure(doc_type, ocr_fields)
    # Document structure now has its own weight slot — add directly
    doc_struct_risk = struct_result["anomaly_score"]
    signal_scores["document_structure"] = doc_struct_risk
    if struct_result["anomaly_score"] > 0:
        if struct_result["missing_fields"]:
            flags.append(
                f"Document structure anomaly ({doc_type}): "
                f"missing expected fields: {', '.join(struct_result['missing_fields'])}"
            )
    findings.append(Finding(
        "document_structure",
        "ANOMALY" if struct_result["anomaly_score"] > 20 else "NORMAL",
        struct_result["anomaly_score"], 70, struct_result["reason"],
    ))

    # ── PART J: Weighted composite score ────────────────────────────────────
    available = {k: v for k, v in signal_scores.items() if k in SIGNAL_WEIGHTS}
    if available:
        total_w = sum(SIGNAL_WEIGHTS[k] for k in available)
        composite = sum(SIGNAL_WEIGHTS[k] * available[k] for k in available) / total_w
    else:
        composite = 0.0
    composite = round(min(max(composite, 0.0), 100.0), 2)

    # ── PART K: Risk Level ────────────────────────────────────────────────────
    risk_level = "UNKNOWN"
    for threshold, label in _RISK_LEVELS:
        if composite <= threshold:
            risk_level = label
            break

    all_confidences = [f.confidence for f in findings]
    overall_confidence = round(
        sum(all_confidences) / len(all_confidences), 1
    ) if all_confidences else 50.0

    elapsed = round(time.time() - t_start, 2)
    logger.info(
        "Tampering | doc_type=%s | score=%.1f | risk=%s | signals=%s | "
        "iq=%.0f | ela=%.1f | cp=%d | font=%.0f | text=%.0f | "
        "sig=%.0f | seal=%.0f | meta=%s | struct=%.0f | "
        "flags=%d | findings=%d | time=%.2fs",
        doc_type, composite, risk_level,
        {k: round(v, 1) for k, v in signal_scores.items()},
        iq["score"], ela_score, clone_count,
        font_result["score"], text_result["score"],
        sig_result["anomaly_score"], seal_result["anomaly_score"],
        meta["status"], struct_result["anomaly_score"],
        len(flags), len(findings), elapsed,
    )

    ela_png = _array_to_png_bytes(ela_array)
    return TamperingResult(
        score=composite,
        flags=flags,
        ela_heatmap_png=ela_png,
        risk_level=risk_level,
        confidence=overall_confidence,
        status="analyzed",
        image_quality=iq,
        ela={
            "score": round(ela_score, 2),
            "risk": round(ela_risk, 2),
            "status": "POSSIBLE_MANIPULATION" if ela_risk > 30 else "NORMAL",
        },
        copy_paste={
            "detected": clone_count >= 15,
            "score": round(cp_risk, 2),
            "cluster_size": clone_count,
            "regions": clone_regions,
        },
        font_consistency=font_result,
        text_analysis=text_result,
        signature=sig_result,
        seal=seal_result,
        metadata_detail=meta,
        document_structure=struct_result,
        findings=[
            {
                "type": f.type, "status": f.status, "score": f.score,
                "confidence": f.confidence, "reason": f.reason,
                **({"regions": f.regions} if f.regions else {}),
            }
            for f in findings
        ],
    )


# ---------------------------------------------------------------------------
# PART A — Image Quality
# ---------------------------------------------------------------------------

def _analyze_image_quality(image: np.ndarray) -> dict:
    h, w = image.shape[:2]

    megapixels = (h * w) / 1_000_000
    res_score = min(megapixels / 2.0, 1.0) * 100

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score = min(lap_var / 400.0, 1.0) * 100

    contrast = float(np.std(gray))
    contrast_score = min(contrast / 50.0, 1.0) * 100

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    noise = float(np.std(gray.astype(float) - blurred.astype(float)))
    noise_score = max(0.0, 100.0 - noise * 5)

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    mean_L = float(np.mean(lab[:, :, 0]))
    brightness_score = max(0.0, 100.0 - abs(mean_L - 128) * 2)

    quality = (
        res_score       * 0.30 +
        blur_score      * 0.30 +
        contrast_score  * 0.20 +
        noise_score     * 0.10 +
        brightness_score * 0.10
    )
    quality = round(min(max(quality, 0.0), 100.0), 2)

    issues = []
    if blur_score < 40:        issues.append("high blur")
    if res_score < 30:         issues.append("very low resolution")
    if contrast_score < 30:    issues.append("low contrast")
    if noise_score < 40:       issues.append("high noise")
    if brightness_score < 40:  issues.append("poor brightness")

    detail = "Good image quality" if not issues else f"Issues: {', '.join(issues)}"
    status = "GOOD" if quality >= 70 else ("MODERATE" if quality >= 40 else "POOR")

    return {
        "score": quality,
        "status": status,
        "detail": detail,
        "breakdown": {
            "resolution": round(res_score, 1),
            "sharpness":  round(blur_score, 1),
            "contrast":   round(contrast_score, 1),
            "noise":      round(noise_score, 1),
            "brightness": round(brightness_score, 1),
        },
    }


# ---------------------------------------------------------------------------
# PART B — ELA (algorithm preserved, helper added)
# ---------------------------------------------------------------------------

def compute_ela(image: np.ndarray, quality: int = 90) -> tuple[np.ndarray, float]:
    """Error Level Analysis — original algorithm preserved."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    original = Image.fromarray(rgb)

    buffer = io.BytesIO()
    original.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer)

    ela_image = ImageChops.difference(original, resaved)
    extrema = ela_image.getextrema()
    max_diff = max((channel[1] for channel in extrema), default=1) or 1
    scale = 255.0 / max_diff
    ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)

    ela_array = np.array(ela_image)
    score = round(float(np.mean(ela_array)) / 255 * 100, 2)
    return ela_array, score


def _ela_risk(ela_score: float) -> float:
    if ela_score <= 10:
        return 0.0
    if ela_score >= 30:
        return 100.0
    return round((ela_score - 10) / 20.0 * 100.0, 2)


# ---------------------------------------------------------------------------
# PART C — Copy-Paste / Clone Detection
# ---------------------------------------------------------------------------

def _detect_clone_regions_with_boxes(
    image: np.ndarray,
    hamming_threshold: int = 25,
    min_spatial_distance: float = 25.0,
    offset_bucket_size: float = 6.0,
) -> tuple[int, list]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    scale = 1.0
    if max(h, w) > 1200:
        scale = 1200.0 / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    orb = cv2.ORB_create(nfeatures=800)
    keypoints, descriptors = orb.detectAndCompute(gray, None)

    if descriptors is None or len(keypoints) < 10:
        return 0, []

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(descriptors, descriptors, k=3)

    offset_buckets: list[tuple] = []
    match_details: list[tuple] = []

    for match_group in matches:
        for m in match_group:
            if m.queryIdx == m.trainIdx or m.distance == 0 or m.distance > hamming_threshold:
                continue
            p1 = np.array(keypoints[m.queryIdx].pt)
            p2 = np.array(keypoints[m.trainIdx].pt)
            if np.linalg.norm(p1 - p2) < min_spatial_distance:
                continue
            dx, dy = p2 - p1
            bucket = (
                round(dx / offset_bucket_size) * offset_bucket_size,
                round(dy / offset_bucket_size) * offset_bucket_size,
            )
            offset_buckets.append(bucket)
            match_details.append((bucket, keypoints[m.queryIdx], keypoints[m.trainIdx]))

    if not offset_buckets:
        return 0, []

    bucket_counts = Counter(offset_buckets)
    top_bucket, top_count = bucket_counts.most_common(1)[0]

    region_boxes: list[dict] = []
    if top_count >= 15:
        sz = int(20 / scale)
        for bucket, kp1, kp2 in match_details:
            if bucket == top_bucket:
                x, y = int(kp1.pt[0] / scale), int(kp1.pt[1] / scale)
                region_boxes.append({"x": max(x - sz, 0), "y": max(y - sz, 0),
                                     "w": sz * 2, "h": sz * 2})

    return top_count, region_boxes[:20]


def _clone_risk(cluster_size: int) -> float:
    if cluster_size < 15:
        return 0.0
    if cluster_size >= 40:
        return 100.0
    return round((cluster_size - 15) / 25.0 * 100.0, 2)


# Backward-compatible wrapper (original name)
def detect_clone_regions(image: np.ndarray, **kwargs) -> int:
    count, _ = _detect_clone_regions_with_boxes(image)
    return count


# ---------------------------------------------------------------------------
# PART D — Font / Text Consistency
# ---------------------------------------------------------------------------

def _analyze_font_consistency(image: np.ndarray, bbox_results: list | None = None) -> dict:
    score = 100.0
    status = "CONSISTENT"

    if bbox_results and len(bbox_results) > 3:
        heights = []
        for bbox in bbox_results:
            try:
                pts = bbox[0]
                h = abs(pts[2][1] - pts[0][1])
                if h > 5:
                    heights.append(h)
            except (IndexError, TypeError):
                continue

        if heights:
            median_h = float(np.median(heights))
            deviations = [abs(h - median_h) / max(median_h, 1) for h in heights]
            mean_dev = float(np.mean(deviations))
            if mean_dev > 0.4:
                score = round(max(0.0, 100.0 - mean_dev * 150), 2)
                status = "POSSIBLE_EDIT"
            else:
                score = round(max(0.0, 100.0 - mean_dev * 100), 2)
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        sobel = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        h = image.shape[0]
        strip_height = max(h // 20, 10)
        strip_means = []
        for i in range(0, h - strip_height, strip_height):
            strip = sobel[i:i + strip_height, :]
            strip_means.append(float(np.mean(np.abs(strip))))
        if strip_means:
            std_ratio = float(np.std(strip_means)) / (float(np.mean(strip_means)) + 1e-6)
            if std_ratio > 1.5:
                score = round(max(0.0, 100.0 - std_ratio * 20), 2)
                status = "POSSIBLE_EDIT"
            else:
                score = round(max(0.0, 100.0 - std_ratio * 10), 2)

    return {"score": round(min(max(score, 0.0), 100.0), 2), "status": status}


# ---------------------------------------------------------------------------
# PART E — Text Layout / Alignment Analysis
# ---------------------------------------------------------------------------

def _analyze_text_layout(image: np.ndarray) -> dict:
    """
    Analyzes text alignment, baseline consistency, and density distribution
    using horizontal projection profile of the document image.

    Algorithm:
      1. Convert BGR → grayscale → Otsu threshold (text = white)
      2. Compute row-wise white pixel density (horizontal projection)
      3. Detect text-line peaks (rows with density > 5% of width)
      4. Measure line-spacing standard deviation → baseline consistency
      5. Measure density distribution evenness across document thirds
         (top/middle/bottom should be roughly balanced for most certificates)

    Returns score 0-100 (high = consistent layout) and status NORMAL | ANOMALOUS.
    No additional file I/O. Runs on the already-loaded BGR image.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

        h, w = thresh.shape[:2]
        # Horizontal projection: count ink pixels per row
        projection = np.sum(thresh == 255, axis=1).astype(float)  # shape (H,)
        min_text_density = w * 0.03   # row must have ≥3% ink to count as text

        # Detect text-line peaks
        text_rows = np.where(projection > min_text_density)[0]
        score = 100.0
        issues: list[str] = []

        if len(text_rows) < 3:
            # Very few text rows — could be image/scan or near-blank
            return {
                "score": 75.0,
                "status": "NORMAL",
                "detail": "Insufficient text rows for layout analysis",
                "line_count": int(len(text_rows)),
            }

        # ── Baseline consistency: line spacing std dev ────────────────────────
        # Group consecutive rows into line blobs
        line_centers: list[int] = []
        block_start = text_rows[0]
        prev = text_rows[0]
        for r in text_rows[1:]:
            if r - prev > 4:   # gap = new line
                line_centers.append((block_start + prev) // 2)
                block_start = r
            prev = r
        line_centers.append((block_start + prev) // 2)

        spacing_penalty = 0.0
        if len(line_centers) >= 3:
            spacings = [line_centers[i + 1] - line_centers[i]
                        for i in range(len(line_centers) - 1)]
            mean_sp = float(np.mean(spacings))
            std_sp  = float(np.std(spacings))
            cv_sp   = std_sp / max(mean_sp, 1.0)   # coefficient of variation
            if cv_sp > 0.6:
                spacing_penalty = min(cv_sp * 30, 40)
                issues.append(f"Irregular line spacing (CV={cv_sp:.2f})")

        # ── Density distribution evenness ────────────────────────────────────
        # Divide document into thirds; density should be reasonably balanced
        third = h // 3
        thirds_density = [
            float(np.mean(projection[:third])),
            float(np.mean(projection[third:2 * third])),
            float(np.mean(projection[2 * third:])),
        ]
        density_std = float(np.std(thirds_density))
        density_mean = float(np.mean(thirds_density)) + 1e-6
        density_cv = density_std / density_mean
        density_penalty = 0.0
        if density_cv > 1.2:
            density_penalty = min(density_cv * 20, 30)
            issues.append(f"Uneven text density distribution (CV={density_cv:.2f})")

        total_penalty = spacing_penalty + density_penalty
        score = round(max(0.0, 100.0 - total_penalty), 2)
        status = "ANOMALOUS" if total_penalty > 25 else "NORMAL"
        detail = "; ".join(issues) if issues else "Text layout and baseline spacing appear normal"

        return {
            "score": score,
            "status": status,
            "detail": detail,
            "line_count": len(line_centers),
            "spacing_cv": round(cv_sp, 3) if len(line_centers) >= 3 else None,
            "density_cv": round(density_cv, 3),
        }

    except Exception as exc:
        logger.debug("Text layout analysis failed (non-fatal): %s", exc)
        return {
            "score": 80.0,
            "status": "NORMAL",
            "detail": "Text layout analysis unavailable",
            "line_count": None,
        }



# ---------------------------------------------------------------------------
# PART F — Signature Analysis
# ---------------------------------------------------------------------------

def _analyze_signature(image: np.ndarray) -> dict:
    h, w = image.shape[:2]
    bottom = image[int(h * 0.7):, :]
    gray_b = cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray_b, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    sig_contours = [
        c for c in contours
        if (cv2.boundingRect(c)[2] >= 10 and cv2.boundingRect(c)[3] >= 5
            and 1.5 <= cv2.boundingRect(c)[2] / cv2.boundingRect(c)[3] <= 8
            and cv2.contourArea(c) > 150)
    ]

    detected = len(sig_contours) >= 2
    anomaly_score = 0.0
    reason = "No signature-like region detected"

    if detected:
        if len(sig_contours) > 6:
            anomaly_score = 40.0
            reason = (f"Multiple ({len(sig_contours)}) signature-like contours — "
                      "possible duplication")
        else:
            full_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            full_sharp = float(cv2.Laplacian(full_gray, cv2.CV_64F).var())
            sig_sharp = float(cv2.Laplacian(gray_b, cv2.CV_64F).var())
            ratio = sig_sharp / max(full_sharp, 1.0)
            if ratio < 0.3:
                anomaly_score = 25.0
                reason = ("Signature region significantly blurrier than document — "
                          "possible pasted signature")
            else:
                anomaly_score = 5.0
                reason = "Signature detected and consistent with document quality"

    return {
        "detected": detected,
        "anomaly_score": round(anomaly_score, 2),
        "contour_count": len(sig_contours),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# PART G — Seal / Stamp Analysis
# ---------------------------------------------------------------------------

def _analyze_seal(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.medianBlur(gray, 5)
    h, w = gray.shape[:2]

    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
        param1=100, param2=40, minRadius=25, maxRadius=min(h, w) // 3,
    )

    detected = circles is not None and len(circles[0]) > 0
    anomaly_score = 0.0
    reason = "No circular seal detected"

    if detected:
        n = len(circles[0])
        if n > 3:
            anomaly_score = 35.0
            reason = f"Multiple seals detected ({n}) — unusually high count"
        else:
            mask = np.zeros(gray.shape, dtype=np.uint8)
            for cx, cy, r in circles[0]:
                cv2.circle(mask, (int(cx), int(cy)), int(r), 255, -1)
            inside = gray[mask == 255]
            outside = gray[mask == 0]
            if len(inside) > 100 and len(outside) > 100:
                ratio = float(np.std(inside)) / max(float(np.std(outside)), 1.0)
                if ratio < 0.3:
                    anomaly_score = 20.0
                    reason = "Seal region unusually uniform (possible printed/pasted seal)"
                else:
                    anomaly_score = 5.0
                    reason = f"Seal detected ({n}) — consistent with document"
            else:
                anomaly_score = 5.0
                reason = f"Seal detected ({n})"

    return {"detected": detected, "anomaly_score": round(anomaly_score, 2), "reason": reason}


# ---------------------------------------------------------------------------
# PART H — Metadata Analysis (enhanced)
# ---------------------------------------------------------------------------

def _check_metadata_full(file_bytes: bytes, file_type: str) -> dict:
    file_type = file_type.lower().lstrip(".")
    anomalies: list[str] = []
    score = 0.0

    if file_type == "pdf":
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            meta = doc.metadata or {}
            doc.close()

            producer = (meta.get("producer") or "").lower()
            creator = (meta.get("creator") or "").lower()
            for tool in _EDITING_TOOLS:
                if tool in producer or tool in creator:
                    anomalies.append(
                        f"PDF produced/edited with {tool.title()} — "
                        "document editor metadata detected"
                    )
                    score = max(score, 50.0)

            create_date = meta.get("creationDate")
            mod_date = meta.get("modDate")
            if create_date and mod_date and create_date != mod_date:
                anomalies.append(
                    "PDF modification date differs from creation date"
                )
                score = max(score, 30.0)

            subject = (meta.get("subject") or "").lower()
            if "untitled" in subject:
                anomalies.append(
                    "PDF metadata contains placeholder 'Untitled' — "
                    "possible template document"
                )
                score = max(score, 15.0)

        except Exception:
            pass
    else:
        try:
            pil_img = Image.open(io.BytesIO(file_bytes))
            exif = pil_img.getexif()
            software = exif.get(305)
            if software:
                sw_lower = str(software).lower()
                for tool in _EDITING_TOOLS:
                    if tool in sw_lower:
                        anomalies.append(
                            f"Image EXIF Software tag indicates editing with '{software}'"
                        )
                        score = max(score, 55.0)
        except Exception:
            pass

    status = "NORMAL"
    if score >= 50:
        status = "WARNING"
    elif score >= 20:
        status = "MINOR_WARNING"

    return {"status": status, "anomalies": anomalies, "score": round(score, 2)}


# Backward-compatible wrapper (original name)
def check_metadata(file_bytes: bytes, file_type: str) -> list[str]:
    return _check_metadata_full(file_bytes, file_type)["anomalies"]


# ---------------------------------------------------------------------------
# PART I — Document Structure
# ---------------------------------------------------------------------------

def _check_document_structure(doc_type: str | None, ocr_fields: dict | None) -> dict:
    if not doc_type or doc_type == "resume" or not ocr_fields:
        return {
            "anomaly_score": 0.0,
            "missing_fields": [],
            "reason": "Document structure check skipped",
        }

    required = _DOC_STRUCTURE.get(doc_type, [])
    if not required:
        return {
            "anomaly_score": 0.0,
            "missing_fields": [],
            "reason": f"No structural requirements defined for '{doc_type}'",
        }

    missing = []
    for f in required:
        val = ocr_fields.get(f)
        if not val or (isinstance(val, tuple) and not val[0]):
            missing.append(f)

    anomaly_score = round((len(missing) / len(required)) * 60.0, 2)
    reason = (
        f"Expected fields missing for {doc_type}: {', '.join(missing)}"
        if missing else
        f"All expected fields present for {doc_type}"
    )
    return {"anomaly_score": anomaly_score, "missing_fields": missing, "reason": reason}


# ---------------------------------------------------------------------------
# Shared helpers (preserve original names for compatibility)
# ---------------------------------------------------------------------------

def laplacian_variance(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def detect_signature(image: np.ndarray) -> bool:
    """Backward-compatible wrapper."""
    return _analyze_signature(image)["detected"]


def detect_seal(image: np.ndarray) -> bool:
    """Backward-compatible wrapper."""
    return _analyze_seal(image)["detected"]


def _array_to_png_bytes(array: np.ndarray) -> bytes:
    image = Image.fromarray(array)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()

