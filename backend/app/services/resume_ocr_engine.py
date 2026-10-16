"""
RESUME OCR ENGINE
=================
Orchestrates the complete Resume/CV OCR pipeline.

  1. Convert PDF -> 300 DPI images (ALL pages)
  2. Apply preprocess_for_resume() per page
  3. EasyOCR first; Tesseract if EasyOCR conf < 0.85
  4. Merge per-page OCR texts (dedup + reading order)
  5. Clean merged text (OCR artifact repair, broken-word merge)
  6. Return ResumeOCRResult

ADDITIVE module — called only from api/ocr.py Stage 6d when
detected_doc_type == "resume". All other modules completely untouched.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger("certiverify.resume_ocr")

OCR_CONF_THRESHOLD = 0.85          # If EasyOCR below this, also run Tesseract


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------

@dataclass
class ResumeOCRResult:
    """Full output of the Resume OCR pipeline."""
    raw_text: str
    accuracy: float                 # 0.0 - 1.0
    engines_used: list
    page_count: int
    processing_time_ms: float
    per_page_texts: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1 - PDF -> 300 DPI images (all pages)
# ---------------------------------------------------------------------------

def _load_all_pages(file_bytes: bytes, file_type: str) -> list:
    """Return ALL pages from a PDF as 300-DPI BGR numpy arrays."""
    file_type = file_type.lower().lstrip(".")
    logger.info("[Resume] Loading | file_type=%s size=%d bytes", file_type, len(file_bytes))

    if file_type != "pdf":
        from PIL import Image as PILImage
        import io
        pil_img = PILImage.open(io.BytesIO(file_bytes)).convert("RGB")
        arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        logger.info("[Resume] Image loaded | shape=%s", arr.shape)
        return [arr]

    # PyMuPDF at 300 DPI (zoom = 300/72)
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        zoom = 300 / 72
        matrix = fitz.Matrix(zoom, zoom)
        pages = []
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=matrix)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
            pages.append(img)
            logger.info("[Resume] Page %d rendered | shape=%s", page_num, img.shape)
        doc.close()
        if pages:
            return pages
    except ImportError:
        logger.warning("[Resume] PyMuPDF not found, trying pdf2image")
    except Exception as exc:
        logger.warning("[Resume] PyMuPDF failed: %s", exc)

    # Fallback: pdf2image
    try:
        from pdf2image import convert_from_bytes
        pil_images = convert_from_bytes(file_bytes, dpi=300)
        pages = [cv2.cvtColor(np.array(p.convert("RGB")), cv2.COLOR_RGB2BGR)
                 for p in pil_images]
        logger.info("[Resume] Loaded %d pages via pdf2image", len(pages))
        return pages
    except Exception as exc:
        logger.error("[Resume] pdf2image failed: %s", exc)

    raise RuntimeError("Cannot render resume PDF. Install PyMuPDF: pip install pymupdf")


# ---------------------------------------------------------------------------
# Step 2 - Preprocess each page
# ---------------------------------------------------------------------------

def _preprocess_pages(pages: list) -> list:
    """Apply preprocess_for_resume() to every page; return (color, binary) pairs."""
    from app.services.image_preprocessing import preprocess_for_resume
    results = []
    for i, page in enumerate(pages):
        try:
            color, binary = preprocess_for_resume(page)
            results.append((color, binary))
            logger.info("[Resume] Image Preprocessed | page=%d", i)
        except Exception as exc:
            logger.warning("[Resume] Preprocessing failed page %d: %s — using raw", i, exc)
            gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
            results.append((page, gray))
    return results


# ---------------------------------------------------------------------------
# Step 3 - OCR per page (EasyOCR first; Tesseract if conf < threshold)
# ---------------------------------------------------------------------------

def _run_ocr_on_page(color: np.ndarray, binary: np.ndarray):
    """
    Run EasyOCR; if confidence < OCR_CONF_THRESHOLD also run Tesseract.
    Returns (merged_text, accuracy, engines_used).
    """
    from app.services.ocr_engine import _run_easyocr, _run_tesseract

    easy_result = _run_easyocr(color)
    easy_text, easy_conf = ("", 0.0) if easy_result is None else easy_result
    logger.info("[Resume] EasyOCR Confidence: %.4f", easy_conf)

    engines_used = []
    parts = []
    scores = []

    if easy_result is not None:
        parts.append(easy_text)
        scores.append(easy_conf)
        engines_used.append("easyocr")

    # Run Tesseract if EasyOCR is below confidence threshold
    if easy_conf < OCR_CONF_THRESHOLD:
        logger.info("[Resume] EasyOCR conf=%.4f < %.2f → running Tesseract",
                    easy_conf, OCR_CONF_THRESHOLD)
        tess_result = _run_tesseract(binary)
        if tess_result is not None:
            tess_text, tess_conf = tess_result
            parts.append(tess_text)
            scores.append(tess_conf)
            engines_used.append("tesseract")
            logger.info("[Resume] Tesseract Confidence: %.4f", tess_conf)

    if not engines_used:
        return "", 0.0, []

    raw = "\n".join(parts)
    acc = float(np.mean(scores)) if scores else 0.0
    if len(engines_used) == 2 and all(len(p) > 20 for p in parts):
        acc = min(1.0, acc + 0.03)

    logger.info("[Resume] Merged OCR | engines=%s accuracy=%.4f text_len=%d",
                engines_used, round(acc, 4), len(raw))
    return raw, round(acc, 4), engines_used


# ---------------------------------------------------------------------------
# Step 4 - Multi-page merge + dedup
# ---------------------------------------------------------------------------

def _merge_pages(page_texts: list) -> str:
    """Merge OCR text from all pages, removing duplicate lines."""
    if len(page_texts) == 1:
        return page_texts[0]
    seen = set()
    merged = []
    for page_text in page_texts:
        for line in page_text.splitlines():
            key = line.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(line.strip())
    return "\n".join(merged)


# ---------------------------------------------------------------------------
# Step 5 - OCR text cleaning + artifact repair
# ---------------------------------------------------------------------------

_ARTIFACT_FIXES = [
    # Email @ sign OCR breakage patterns
    (re.compile(r"\(a\)", re.IGNORECASE), "@"),
    (re.compile(r"\[at\]", re.IGNORECASE), "@"),
    (re.compile(r"\s+@\s+"), "@"),
    (re.compile(r"\[dot\]", re.IGNORECASE), "."),
    (re.compile(r"\(dot\)", re.IGNORECASE), "."),
    # Broken hyphen at line end (broken words across lines)
    (re.compile(r"(\w)-\n(\w)"), r"\1\2"),
    # Multiple spaces to single
    (re.compile(r" {2,}"), " "),
]

_NOISE_CHARS = re.compile(r"[|\\^~`]")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _clean_ocr_text(raw: str) -> str:
    """Apply OCR artifact repairs, normalise whitespace, remove pure-noise lines."""
    for pattern, replacement in _ARTIFACT_FIXES:
        raw = pattern.sub(replacement, raw)

    raw = _NOISE_CHARS.sub(" ", raw)

    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        line = re.sub(r" {2,}", " ", line).strip()
        # Drop lines that are just punctuation/noise
        if len(line) <= 1 and not any(c.isalpha() or c.isdigit() for c in line):
            continue
        cleaned.append(line)

    result = "\n".join(cleaned)
    result = _MULTI_BLANK.sub("\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_resume_ocr(file_bytes: bytes, file_type: str) -> ResumeOCRResult:
    """
    Full Resume OCR pipeline. Called from api/ocr.py when
    detected_doc_type == "resume".

    Parameters
    ----------
    file_bytes : raw bytes of the uploaded PDF or image
    file_type  : "pdf", "jpg", "jpeg", "png", etc.

    Returns
    -------
    ResumeOCRResult with raw_text, accuracy, page_count, processing_time_ms
    """
    t_start = time.time()
    logger.info("=" * 60)
    logger.info("[Resume] Pipeline START | file_type=%s size=%d bytes",
                file_type, len(file_bytes))

    # Step 1: PDF -> images
    pages = _load_all_pages(file_bytes, file_type)
    logger.info("[Resume] Total pages: %d", len(pages))

    # Step 2: Preprocess
    preprocessed = _preprocess_pages(pages)

    # Step 3: OCR per page
    page_texts = []
    all_accuracies = []
    all_engines = set()

    for i, (color, binary) in enumerate(preprocessed):
        logger.info("[Resume] OCR page %d/%d", i + 1, len(preprocessed))
        text, acc, engines = _run_ocr_on_page(color, binary)
        page_texts.append(text)
        all_accuracies.append(acc)
        all_engines.update(engines)

    # Step 4: Merge
    merged_raw = _merge_pages(page_texts)
    logger.info("[Resume] Merged OCR | total_chars=%d", len(merged_raw))

    # Step 5: Clean
    cleaned_text = _clean_ocr_text(merged_raw)
    logger.info("[Resume] Cleaned OCR | total_chars=%d", len(cleaned_text))

    accuracy = round(float(np.mean(all_accuracies)) if all_accuracies else 0.0, 4)
    if len(all_engines) == 2:
        accuracy = min(1.0, accuracy + 0.03)

    t_elapsed = (time.time() - t_start) * 1000
    logger.info(
        "[Resume] Pipeline COMPLETE | engines=%s accuracy=%.4f pages=%d time=%.1fms",
        sorted(all_engines), accuracy, len(pages), t_elapsed
    )
    logger.info("[Resume] Processing Time: %.1f ms", t_elapsed)
    logger.info("=" * 60)

    return ResumeOCRResult(
        raw_text=cleaned_text,
        accuracy=accuracy,
        engines_used=sorted(all_engines),
        page_count=len(pages),
        processing_time_ms=round(t_elapsed, 1),
        per_page_texts=page_texts,
    )
