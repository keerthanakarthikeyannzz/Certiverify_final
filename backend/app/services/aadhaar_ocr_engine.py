"""
AADHAAR OCR ENGINE  —  Priority 1 Enhancement
===============================================

Orchestrates the complete Aadhaar-specific OCR pipeline:

  1. Convert PDF → high-resolution images (ALL pages, 300 DPI)
  2. Apply preprocess_for_aadhaar() (shadow removal, morph cleanup, tight threshold)
  3. Run dual OCR (EasyOCR + Tesseract) via existing extract_text()
     - If EasyOCR confidence < 0.85, Tesseract is always run
  4. Merge per-page OCR texts with deduplication + reading-order preservation
  5. Clean merged text (remove noise symbols, merge broken lines, normalise spaces)
  6. Detect QR code on binarised image (pyzbar → OpenCV QR fallback)
  7. Detect portrait photograph via contour area heuristic
  8. Return AadhaarOCRResult (raw_text, accuracy, qr_present, photo_present)

This module is ADDITIVE — it does NOT modify any existing function.
Called from api/ocr.py when detected_doc_type == "aadhaar_card".
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("certiverify.aadhaar_ocr")


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------

@dataclass
class AadhaarOCRResult:
    """Full output of the Aadhaar OCR pipeline."""
    raw_text: str
    accuracy: float                          # 0.0 – 1.0
    engines_used: list
    qr_present: bool
    photo_present: bool
    page_count: int
    processing_time_ms: float
    per_page_texts: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1 — PDF -> high-res images (300 DPI, all pages)
# ---------------------------------------------------------------------------

def _load_all_pages(file_bytes: bytes, file_type: str) -> list:
    """
    Return ALL pages from a PDF as 300-DPI BGR numpy arrays.
    For image files, returns a single-element list.
    Uses PyMuPDF (preferred) -> pdf2image fallback.
    """
    file_type = file_type.lower().lstrip(".")
    logger.info("[Aadhaar] PDF Loaded | file_type=%s size=%d bytes", file_type, len(file_bytes))

    if file_type != "pdf":
        from PIL import Image as PILImage
        import io
        pil_img = PILImage.open(io.BytesIO(file_bytes)).convert("RGB")
        arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        logger.info("[Aadhaar] Image loaded | shape=%s", arr.shape)
        return [arr]

    # Try PyMuPDF first (300 DPI)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        zoom = 300 / 72          # 300 DPI
        matrix = fitz.Matrix(zoom, zoom)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=matrix)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
            pages.append(img)
            logger.info("[Aadhaar] Page %d rendered via PyMuPDF | shape=%s", page_num, img.shape)
        doc.close()
        if pages:
            return pages
    except ImportError:
        logger.warning("[Aadhaar] PyMuPDF not available, trying pdf2image")
    except Exception as exc:
        logger.warning("[Aadhaar] PyMuPDF failed: %s — trying pdf2image", exc)

    # Fallback: pdf2image + Poppler at 300 DPI
    try:
        from pdf2image import convert_from_bytes
        pil_images = convert_from_bytes(file_bytes, dpi=300)
        pages = []
        for i, pil_img in enumerate(pil_images):
            arr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
            pages.append(arr)
            logger.info("[Aadhaar] Page %d rendered via pdf2image | shape=%s", i, arr.shape)
        if pages:
            return pages
    except Exception as exc:
        logger.error("[Aadhaar] pdf2image also failed: %s", exc)

    raise RuntimeError(
        "Cannot render Aadhaar PDF. Install PyMuPDF: pip install pymupdf  "
        "OR pdf2image + Poppler: pip install pdf2image && brew install poppler"
    )


# ---------------------------------------------------------------------------
# Step 2 — Per-page preprocessing
# ---------------------------------------------------------------------------

def _preprocess_pages(pages: list) -> list:
    """Apply preprocess_for_aadhaar() to every page; returns (color, binary) pairs."""
    from app.services.image_preprocessing import preprocess_for_aadhaar
    results = []
    for i, page in enumerate(pages):
        try:
            color, binary = preprocess_for_aadhaar(page)
            results.append((color, binary))
            logger.info("[Aadhaar] Image Preprocessed | page=%d | color=%s binary=%s",
                        i, color.shape, binary.shape)
        except Exception as exc:
            logger.warning("[Aadhaar] Preprocessing failed for page %d: %s — using raw", i, exc)
            gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
            results.append((page, gray))
    return results


# ---------------------------------------------------------------------------
# Step 3 — Dual OCR per page
# ---------------------------------------------------------------------------

def _run_ocr_on_page(color: np.ndarray, binary: np.ndarray):
    """
    Run EasyOCR (color) + Tesseract (binary) via the existing private helpers.
    For Aadhaar, Tesseract is ALWAYS run (not conditional on confidence).
    Returns (merged_text, accuracy, engines_used).
    """
    from app.services.ocr_engine import _run_easyocr, _run_tesseract

    logger.info("[Aadhaar] OCR Started")

    easy_result = _run_easyocr(color)
    easy_text, easy_conf = ("", 0.0) if easy_result is None else easy_result
    logger.info("[Aadhaar] EasyOCR Confidence: %.4f", easy_conf)

    # Always run Tesseract for Aadhaar (even when EasyOCR confidence >= 0.85)
    tess_result = _run_tesseract(binary)
    tess_text, tess_conf = ("", 0.0) if tess_result is None else tess_result
    logger.info("[Aadhaar] Tesseract Confidence: %.4f", tess_conf)

    engines_used = []
    parts = []
    scores = []

    if easy_result is not None:
        parts.append(easy_text)
        scores.append(easy_conf)
        engines_used.append("easyocr")

    if tess_result is not None:
        parts.append(tess_text)
        scores.append(tess_conf)
        engines_used.append("tesseract")

    if not engines_used:
        return "", 0.0, []

    raw = "\n".join(parts)
    acc = float(np.mean(scores)) if scores else 0.0
    # Agreement bonus when both engines produced text
    if len(engines_used) == 2 and all(len(p) > 20 for p in parts):
        acc = min(1.0, acc + 0.03)

    logger.info("[Aadhaar] Merged OCR | engines=%s accuracy=%.4f text_len=%d",
                engines_used, round(acc, 4), len(raw))
    return raw, round(acc, 4), engines_used


# ---------------------------------------------------------------------------
# Step 4 — Multi-page text merge + deduplication
# ---------------------------------------------------------------------------

def _merge_pages(page_texts: list) -> str:
    """
    Merge OCR text from multiple pages.
    Removes fully duplicate lines that appear across pages (common with watermarks),
    preserves reading order, and collapses excessive blank lines.
    """
    if len(page_texts) == 1:
        return page_texts[0]

    seen = set()
    merged_lines = []

    for page_text in page_texts:
        for line in page_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            key = stripped.lower()
            if key not in seen:
                seen.add(key)
                merged_lines.append(stripped)

    return "\n".join(merged_lines)


# ---------------------------------------------------------------------------
# Step 5 — Text cleaning
# ---------------------------------------------------------------------------

_NOISE_CHARS = re.compile(r"[|@#\$%\^&\*\(\)_=\[\]\{\}\\<>]")
_REPEATED_PUNCT = re.compile(r"[.\-_=~]{3,}")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _clean_ocr_text(raw: str) -> str:
    """
    Normalise merged OCR text for structured field extraction.

    - Remove obvious noise characters
    - Remove repeated punctuation lines (dividers)
    - Collapse multiple spaces to single space
    - Collapse 3+ blank lines to 1
    - Remove lines that are purely numeric noise (single digits, isolated symbols)
    - Preserve reading order
    """
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        line = _NOISE_CHARS.sub(" ", line)
        line = _REPEATED_PUNCT.sub(" ", line)
        line = re.sub(r" {2,}", " ", line).strip()
        # Drop lines that are just 1-2 isolated characters (OCR noise)
        if len(line) <= 2 and not any(c.isalpha() for c in line):
            continue
        cleaned.append(line)

    result = "\n".join(cleaned)
    result = _MULTI_BLANK.sub("\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Step 6 — QR Code detection (binarised -> pyzbar -> OpenCV QR fallback)
# ---------------------------------------------------------------------------

def _detect_qr(images_binary: list, images_color: list) -> bool:
    """
    Attempt QR detection on every page using:
    1. pyzbar on the binarised image (most reliable on clean binary)
    2. OpenCV QRCodeDetector on the colour image
    Returns True as soon as a QR is found on any page.
    """
    try:
        from pyzbar.pyzbar import decode
        for binary in images_binary:
            if decode(binary):
                logger.info("[Aadhaar] QR detected via pyzbar on binarised image")
                return True
        for color in images_color:
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            if decode(gray):
                logger.info("[Aadhaar] QR detected via pyzbar on grayscale")
                return True
    except Exception as exc:
        logger.debug("[Aadhaar] pyzbar QR check: %s", exc)

    try:
        qr_detector = cv2.QRCodeDetector()
        for color in images_color:
            data, _, _ = qr_detector.detectAndDecode(color)
            if data:
                logger.info("[Aadhaar] QR detected via OpenCV QRCodeDetector")
                return True
        for binary in images_binary:
            data, _, _ = qr_detector.detectAndDecode(binary)
            if data:
                logger.info("[Aadhaar] QR detected via OpenCV QRCodeDetector (binary)")
                return True
    except Exception as exc:
        logger.debug("[Aadhaar] OpenCV QR detector: %s", exc)

    logger.info("[Aadhaar] No QR code detected on any page")
    return False


# ---------------------------------------------------------------------------
# Step 7 — Photograph / portrait detection
# ---------------------------------------------------------------------------

def _detect_photo(images_color: list) -> bool:
    """
    Detect a portrait photograph on the Aadhaar card using OpenCV contour analysis.

    Aadhaar photos appear as a rectangular region with:
    - Aspect ratio close to portrait (0.5 - 1.6)
    - Located in the top 70% of the card
    - Area 0.8% - 30% of card area
    - Moderate edge density inside the contour (photo texture, not blank, not all text)

    Returns True if a probable portrait region is found on any page.
    """
    for page_idx, color in enumerate(images_color):
        try:
            h, w = color.shape[:2]
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 30, 100)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            min_photo_area = (h * w) * 0.008
            max_photo_area = (h * w) * 0.30

            for c in contours:
                area = cv2.contourArea(c)
                if not (min_photo_area < area < max_photo_area):
                    continue
                x, y, cw, ch = cv2.boundingRect(c)
                aspect = cw / ch if ch > 0 else 0
                if not (0.5 < aspect < 1.6):
                    continue
                if y > h * 0.7:
                    continue
                roi = gray[y: y + ch, x: x + cw]
                roi_edges = cv2.Canny(roi, 30, 100)
                edge_density = np.count_nonzero(roi_edges) / (cw * ch + 1)
                if 0.01 < edge_density < 0.35:
                    logger.info(
                        "[Aadhaar] Portrait detected | page=%d bbox=[%d,%d,%d,%d] "
                        "area=%.0f aspect=%.2f edge_density=%.4f",
                        page_idx, x, y, cw, ch, area, aspect, edge_density
                    )
                    return True
        except Exception as exc:
            logger.debug("[Aadhaar] Photo detection error on page %d: %s", page_idx, exc)

    logger.info("[Aadhaar] No portrait photo region detected")
    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_aadhaar_ocr(file_bytes: bytes, file_type: str) -> AadhaarOCRResult:
    """
    Full Aadhaar OCR pipeline.  Call this from api/ocr.py when
    detected_doc_type == "aadhaar_card".

    Parameters
    ----------
    file_bytes : raw bytes of the uploaded PDF or image
    file_type  : "pdf", "jpg", "jpeg", "png", etc.

    Returns
    -------
    AadhaarOCRResult with raw_text, accuracy, qr_present, photo_present
    """
    t_start = time.time()
    logger.info("=" * 60)
    logger.info("[Aadhaar] Pipeline START | file_type=%s size=%d bytes", file_type, len(file_bytes))

    # Step 1: PDF -> images (all pages, 300 DPI)
    pages = _load_all_pages(file_bytes, file_type)
    logger.info("[Aadhaar] Total pages loaded: %d", len(pages))

    # Step 2: Preprocess each page
    preprocessed = _preprocess_pages(pages)
    colors = [c for c, _ in preprocessed]
    binaries = [b for _, b in preprocessed]

    # Step 3: OCR each page
    page_texts = []
    all_accuracies = []
    all_engines = set()

    for i, (color, binary) in enumerate(preprocessed):
        logger.info("[Aadhaar] OCR page %d/%d", i + 1, len(preprocessed))
        text, acc, engines = _run_ocr_on_page(color, binary)
        page_texts.append(text)
        all_accuracies.append(acc)
        all_engines.update(engines)

    # Step 4: Merge pages
    merged_raw = _merge_pages(page_texts)
    logger.info("[Aadhaar] Merged OCR | total_chars=%d", len(merged_raw))

    # Step 5: Clean text
    cleaned_text = _clean_ocr_text(merged_raw)
    logger.info("[Aadhaar] Cleaned OCR | total_chars=%d", len(cleaned_text))

    # Step 6: QR detection
    qr_present = _detect_qr(binaries, colors)

    # Step 7: Photo detection
    photo_present = _detect_photo(colors)

    # Final accuracy
    accuracy = round(float(np.mean(all_accuracies)) if all_accuracies else 0.0, 4)
    if len(all_engines) == 2:
        accuracy = min(1.0, accuracy + 0.03)

    t_elapsed = (time.time() - t_start) * 1000
    logger.info(
        "[Aadhaar] Pipeline COMPLETE | engines=%s accuracy=%.4f "
        "qr=%s photo=%s pages=%d time=%.1fms",
        sorted(all_engines), accuracy, qr_present, photo_present, len(pages), t_elapsed
    )
    logger.info("[Aadhaar] Processing Time: %.1f ms", t_elapsed)
    logger.info("=" * 60)

    return AadhaarOCRResult(
        raw_text=cleaned_text,
        accuracy=accuracy,
        engines_used=sorted(all_engines),
        qr_present=qr_present,
        photo_present=photo_present,
        page_count=len(pages),
        processing_time_ms=round(t_elapsed, 1),
        per_page_texts=page_texts,
    )
