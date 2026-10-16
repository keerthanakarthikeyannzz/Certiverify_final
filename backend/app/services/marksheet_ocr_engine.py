"""
MARKSHEET OCR ENGINE  —  SSLC/HSC Priority Enhancement
=======================================================

Orchestrates the complete SSLC/HSC Marksheet OCR pipeline:

  1. Convert PDF -> high-resolution images (ALL pages, 300 DPI)
  2. Apply preprocess_for_marksheet() per page
  3. Dual OCR (EasyOCR + Tesseract) - always both for marksheets
  4. Merge per-page OCR texts (dedup + reading order)
  5. Clean merged text (noise, broken lines, symbols)
  6. Detect QR code (pyzbar -> OpenCV fallback)
  7. Detect signature (contour heuristic on bottom third)
  8. Return MarksheetOCRResult

This module is ADDITIVE. Called from api/ocr.py when doc_type is marksheet/sslc/hsc.
All existing functions are completely untouched.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("certiverify.marksheet_ocr")


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------

@dataclass
class MarksheetOCRResult:
    """Full output of the Marksheet OCR pipeline."""
    raw_text: str
    accuracy: float                     # 0.0 - 1.0
    engines_used: list
    qr_present: bool
    signature_present: bool
    page_count: int
    processing_time_ms: float
    per_page_texts: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1 - PDF -> high-res images (300 DPI, all pages)
# ---------------------------------------------------------------------------

def _load_all_pages(file_bytes: bytes, file_type: str) -> list:
    """
    Return ALL pages from a PDF as 300-DPI BGR numpy arrays.
    For image files, returns single-element list.
    Uses PyMuPDF -> pdf2image fallback.
    """
    file_type = file_type.lower().lstrip(".")
    logger.info("[Marksheet] PDF Loaded | file_type=%s size=%d bytes", file_type, len(file_bytes))

    if file_type != "pdf":
        from PIL import Image as PILImage
        import io
        pil_img = PILImage.open(io.BytesIO(file_bytes)).convert("RGB")
        arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        logger.info("[Marksheet] Image loaded | shape=%s", arr.shape)
        return [arr]

    # PyMuPDF at 300 DPI
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        zoom = 300 / 72
        matrix = fitz.Matrix(zoom, zoom)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=matrix)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
            pages.append(img)
            logger.info("[Marksheet] Page %d rendered via PyMuPDF | shape=%s", page_num, img.shape)
        doc.close()
        if pages:
            return pages
    except ImportError:
        logger.warning("[Marksheet] PyMuPDF not available, trying pdf2image")
    except Exception as exc:
        logger.warning("[Marksheet] PyMuPDF failed: %s", exc)

    # Fallback: pdf2image
    try:
        from pdf2image import convert_from_bytes
        pil_images = convert_from_bytes(file_bytes, dpi=300)
        pages = []
        for i, pil_img in enumerate(pil_images):
            arr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
            pages.append(arr)
            logger.info("[Marksheet] Page %d rendered via pdf2image | shape=%s", i, arr.shape)
        if pages:
            return pages
    except Exception as exc:
        logger.error("[Marksheet] pdf2image failed: %s", exc)

    raise RuntimeError(
        "Cannot render marksheet PDF. Install PyMuPDF: pip install pymupdf"
    )


# ---------------------------------------------------------------------------
# Step 2 - Per-page preprocessing
# ---------------------------------------------------------------------------

def _preprocess_pages(pages: list) -> list:
    """Apply preprocess_for_marksheet() to every page; return (color, binary) pairs."""
    from app.services.image_preprocessing import preprocess_for_marksheet
    results = []
    for i, page in enumerate(pages):
        try:
            color, binary = preprocess_for_marksheet(page)
            results.append((color, binary))
            logger.info("[Marksheet] Image Preprocessed | page=%d | color=%s binary=%s",
                        i, color.shape, binary.shape)
        except Exception as exc:
            logger.warning("[Marksheet] Preprocessing failed page %d: %s — using raw", i, exc)
            gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
            results.append((page, gray))
    return results


# ---------------------------------------------------------------------------
# Step 3 - Dual OCR per page (always both engines for marksheets)
# ---------------------------------------------------------------------------

def _run_ocr_on_page(color: np.ndarray, binary: np.ndarray):
    """
    Run EasyOCR (color) + Tesseract (binary).
    For marksheets, BOTH engines ALWAYS run regardless of confidence —
    cross-engine agreement helps on dense table text.
    Returns (merged_text, accuracy, engines_used).
    """
    from app.services.ocr_engine import _run_easyocr, _run_tesseract

    logger.info("[Marksheet] OCR Started")

    easy_result = _run_easyocr(color)
    easy_text, easy_conf = ("", 0.0) if easy_result is None else easy_result
    logger.info("[Marksheet] EasyOCR Confidence: %.4f", easy_conf)

    # Always run Tesseract for marksheets (table text benefits from both)
    tess_result = _run_tesseract(binary)
    tess_text, tess_conf = ("", 0.0) if tess_result is None else tess_result
    logger.info("[Marksheet] Tesseract Confidence: %.4f", tess_conf)

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
    if len(engines_used) == 2 and all(len(p) > 20 for p in parts):
        acc = min(1.0, acc + 0.03)

    logger.info("[Marksheet] Merged OCR | engines=%s accuracy=%.4f text_len=%d",
                engines_used, round(acc, 4), len(raw))
    return raw, round(acc, 4), engines_used


# ---------------------------------------------------------------------------
# Step 4 - Multi-page text merge + deduplication
# ---------------------------------------------------------------------------

def _merge_pages(page_texts: list) -> str:
    """Merge OCR text from multiple pages, removing duplicate lines."""
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
# Step 5 - Text cleaning
# ---------------------------------------------------------------------------

_NOISE_CHARS = re.compile(r"[|@#\$%\^&\*_=\[\]\{\}\\<>]")
_REPEATED_PUNCT = re.compile(r"[.\-_=~]{4,}")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _clean_ocr_text(raw: str) -> str:
    """
    Normalise merged OCR text for structured field extraction.
    Preserves table structure (numbers, colons, slashes needed).
    """
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        line = _NOISE_CHARS.sub(" ", line)
        line = _REPEATED_PUNCT.sub(" ", line)
        line = re.sub(r" {2,}", " ", line).strip()
        # Drop lines that are just 1 isolated non-alpha char
        if len(line) <= 1 and not any(c.isalpha() or c.isdigit() for c in line):
            continue
        cleaned.append(line)

    result = "\n".join(cleaned)
    result = _MULTI_BLANK.sub("\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Step 6 - QR Code detection
# ---------------------------------------------------------------------------

def _detect_qr(images_binary: list, images_color: list) -> bool:
    """Detect QR code on any page using pyzbar -> OpenCV fallback."""
    try:
        from pyzbar.pyzbar import decode
        for binary in images_binary:
            if decode(binary):
                logger.info("[Marksheet] QR detected via pyzbar (binary)")
                return True
        for color in images_color:
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            if decode(gray):
                logger.info("[Marksheet] QR detected via pyzbar (gray)")
                return True
    except Exception as exc:
        logger.debug("[Marksheet] pyzbar: %s", exc)

    try:
        qr_detector = cv2.QRCodeDetector()
        for color in images_color:
            data, _, _ = qr_detector.detectAndDecode(color)
            if data:
                logger.info("[Marksheet] QR detected via OpenCV")
                return True
        for binary in images_binary:
            data, _, _ = qr_detector.detectAndDecode(binary)
            if data:
                logger.info("[Marksheet] QR detected via OpenCV (binary)")
                return True
    except Exception as exc:
        logger.debug("[Marksheet] OpenCV QR: %s", exc)

    logger.info("[Marksheet] No QR code detected")
    return False


# ---------------------------------------------------------------------------
# Step 7 - Signature detection
# ---------------------------------------------------------------------------

def _detect_signature(images_color: list) -> bool:
    """
    Detect a signature on any page using contour analysis on the bottom third.

    Signatures appear as irregular, horizontal ink strokes in the bottom 30%
    of the marksheet. We look for contours with:
    - High aspect ratio (wide, not tall)
    - Low area density (not solid filled — unlike text blocks)
    - Located in the bottom 30% of the page
    """
    for page_idx, color in enumerate(images_color):
        try:
            h, w = color.shape[:2]
            # Focus on bottom third
            bottom = color[int(h * 0.70):, :]
            gray = cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            irregular_count = 0
            for c in contours:
                x, y, cw, ch = cv2.boundingRect(c)
                if cw < 15 or ch < 4:
                    continue
                aspect = cw / max(ch, 1)
                area = cv2.contourArea(c)
                # Signature strokes: wide, not tall, medium area
                if 2.0 <= aspect <= 15.0 and 80 < area < 15000:
                    irregular_count += 1

            if irregular_count >= 2:
                logger.info("[Marksheet] Signature detected | page=%d contours=%d",
                            page_idx, irregular_count)
                return True
        except Exception as exc:
            logger.debug("[Marksheet] Signature detection error page %d: %s", page_idx, exc)

    logger.info("[Marksheet] No signature detected")
    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_marksheet_ocr(file_bytes: bytes, file_type: str) -> MarksheetOCRResult:
    """
    Full SSLC/HSC Marksheet OCR pipeline. Call from api/ocr.py when
    detected_doc_type in {"marksheet", "sslc", "hsc"}.

    Parameters
    ----------
    file_bytes : raw bytes of the uploaded PDF or image
    file_type  : "pdf", "jpg", "jpeg", "png", etc.

    Returns
    -------
    MarksheetOCRResult with raw_text, accuracy, qr_present, signature_present
    """
    t_start = time.time()
    logger.info("=" * 60)
    logger.info("[Marksheet] Pipeline START | file_type=%s size=%d bytes",
                file_type, len(file_bytes))

    # Step 1: PDF -> images (300 DPI, all pages)
    pages = _load_all_pages(file_bytes, file_type)
    logger.info("[Marksheet] Total pages loaded: %d", len(pages))

    # Step 2: Preprocess each page
    preprocessed = _preprocess_pages(pages)
    colors = [c for c, _ in preprocessed]
    binaries = [b for _, b in preprocessed]

    # Step 3: OCR each page
    page_texts = []
    all_accuracies = []
    all_engines = set()

    for i, (color, binary) in enumerate(preprocessed):
        logger.info("[Marksheet] OCR page %d/%d", i + 1, len(preprocessed))
        text, acc, engines = _run_ocr_on_page(color, binary)
        page_texts.append(text)
        all_accuracies.append(acc)
        all_engines.update(engines)

    # Step 4: Merge pages
    merged_raw = _merge_pages(page_texts)
    logger.info("[Marksheet] Merged OCR | total_chars=%d", len(merged_raw))

    # Step 5: Clean text
    cleaned_text = _clean_ocr_text(merged_raw)
    logger.info("[Marksheet] Cleaned OCR | total_chars=%d", len(cleaned_text))

    # Step 6: QR detection
    qr_present = _detect_qr(binaries, colors)

    # Step 7: Signature detection
    signature_present = _detect_signature(colors)

    # Final accuracy
    accuracy = round(float(np.mean(all_accuracies)) if all_accuracies else 0.0, 4)
    if len(all_engines) == 2:
        accuracy = min(1.0, accuracy + 0.03)

    t_elapsed = (time.time() - t_start) * 1000
    logger.info(
        "[Marksheet] Pipeline COMPLETE | engines=%s accuracy=%.4f "
        "qr=%s signature=%s pages=%d time=%.1fms",
        sorted(all_engines), accuracy, qr_present, signature_present,
        len(pages), t_elapsed
    )
    logger.info("[Marksheet] Processing Time: %.1f ms", t_elapsed)
    logger.info("=" * 60)

    return MarksheetOCRResult(
        raw_text=cleaned_text,
        accuracy=accuracy,
        engines_used=sorted(all_engines),
        qr_present=qr_present,
        signature_present=signature_present,
        page_count=len(pages),
        processing_time_ms=round(t_elapsed, 1),
        per_page_texts=page_texts,
    )
