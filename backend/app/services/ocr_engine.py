"""
MODULE 4 - OCR TEXT EXTRACTION (engine layer)

Runs EasyOCR (primary — better on stylized certificate fonts/seals) and
Tesseract (secondary — fast, good cross-check on cleanly printed text).
Whichever engine(s) are actually installed/loadable are used; the pipeline
degrades gracefully rather than hard-failing Module 4 if one is missing.

Speed optimizations:
- EasyOCR model is pre-loaded at startup via warmup_easyocr() — no cold-start
  on the first real request.
- Tesseract is SKIPPED when EasyOCR confidence >= CONFIDENCE_SKIP_TESSERACT
  AND all required fields for the detected document type are present. This
  saves 5-15s per request for clear, high-quality documents.
- Per-engine wall-clock timing is logged for performance tracking.
"""
import logging
import threading
import time
from functools import lru_cache

import numpy as np

logger = logging.getLogger("certiverify.ocr_engine")

# Thread safety lock for EasyOCR forward-pass inference to prevent PyTorch CRAFT segfaults
_easyocr_lock = threading.Lock()

try:
    import torch
    if torch.get_num_threads() > 4:
        torch.set_num_threads(4)
except Exception:
    pass

# ---------------------------------------------------------------------------
# Startup ready flag
# ---------------------------------------------------------------------------

# Set to True by warmup_easyocr() once the model is loaded and cached.
# Used to log a warning if a request arrives before warmup completes.
_easyocr_ready: bool = False

# ---------------------------------------------------------------------------
# Early-stop thresholds
# ---------------------------------------------------------------------------

# If EasyOCR confidence meets or exceeds this value, Tesseract is skipped
# (provided required fields are also found). 0.82 is chosen as the threshold
# because EasyOCR at >=82% confidence rarely benefits from Tesseract merging.
CONFIDENCE_SKIP_TESSERACT: float = 0.82

# Minimum words of extracted text before we trust the confidence score.
# Short texts (e.g. blank-ish pages) get low confidence correctly, but we
# also want at least some content before declaring early-stop.
MIN_WORDS_FOR_EARLY_STOP: int = 20

# Required field keywords per document type for early-stop field check.
# At least ONE keyword from each sub-list must appear in the OCR text.
_REQUIRED_FIELDS_BY_DOC_TYPE: dict[str, list[list[str]]] = {
    "aadhaar_card": [
        ["aadhaar", "aadhar", "uid", "unique identification"],
        ["dob", "date of birth", "birth"],
        ["male", "female", "gender"],
    ],
    "marksheet": [
        ["register", "reg no", "roll"],
        ["marks", "total", "grade", "score"],
        ["school", "board", "matriculation", "sslc", "hsc"],
    ],
    "sslc_marksheet": [
        ["register", "reg no", "roll"],
        ["marks", "total", "grade"],
        ["sslc", "secondary", "board"],
    ],
    "hsc_marksheet": [
        ["register", "reg no", "roll"],
        ["marks", "total", "grade"],
        ["hsc", "higher secondary", "board"],
    ],
    "degree_certificate": [
        ["university", "college", "institute"],
        ["degree", "bachelor", "master", "b.e", "b.tech", "m.e", "m.tech", "b.sc", "m.sc"],
        ["convocation", "awarded", "conferred", "passed"],
    ],
    "diploma": [
        ["diploma", "polytechnic", "technical"],
        ["register", "roll", "candidate"],
    ],
    "transfer_certificate": [
        ["transfer", "tc", "leaving"],
        ["school", "institution", "college"],
    ],
    "resume": [
        ["experience", "skills", "education", "projects", "work"],
        ["email", "phone", "mobile", "contact"],
    ],
}


def _has_required_fields(text: str, doc_type: str) -> bool:
    """
    Returns True if the OCR text contains at least one keyword from every
    required field group for the given document type.
    Used to decide whether to skip Tesseract after a high-confidence EasyOCR pass.
    """
    groups = _REQUIRED_FIELDS_BY_DOC_TYPE.get(doc_type)
    if not groups:
        # Unknown doc type — cannot confirm fields, so don’t skip Tesseract
        return False
    text_lower = text.lower()
    return all(
        any(kw in text_lower for kw in group)
        for group in groups
    )


class OCREngineResult:
    def __init__(self, raw_text: str, accuracy: float, engines_used: list[str]):
        self.raw_text = raw_text
        self.accuracy = accuracy          # 0-1, weighted average confidence across engines used
        self.engines_used = engines_used


_last_easyocr_error: str | None = None

@lru_cache(maxsize=1)
def _load_easyocr_reader():
    global _last_easyocr_error
    t0 = time.time()
    try:
        import easyocr
        logger.info("Loading EasyOCR model (English, CPU)...")
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logger.info("✔ EasyOCR model loaded in %.1fs", time.time() - t0)
        return reader
    except ImportError:
        _last_easyocr_error = "EasyOCR not installed (pip install easyocr)"
        logger.warning(_last_easyocr_error)
        return None
    except Exception as e:
        _last_easyocr_error = f"EasyOCR model loading failed: {e}"
        logger.error(_last_easyocr_error, exc_info=True)
        return None


def _run_easyocr(image: np.ndarray) -> tuple[str, float, list] | None:
    """
    Run EasyOCR and return (text, avg_confidence, raw_bbox_results).
    Returns None if EasyOCR is unavailable or fails.
    Logs wall-clock time for performance tracking.
    """
    if not _easyocr_ready:
        logger.warning("EasyOCR model may still be warming up — request arrived before warmup completed")
    reader = _load_easyocr_reader()
    if reader is None:
        logger.warning("EasyOCR unavailable — skipping")
        return None
    try:
        t0 = time.time()
        with _easyocr_lock:
            results = reader.readtext(image)
        elapsed = time.time() - t0
        if not results:
            logger.info("✔ EasyOCR: no text detected (empty result) | %.1fs", elapsed)
            return "", 0.0, []
        texts = [text for _, text, _ in results]
        confidences = [conf for _, _, conf in results]
        raw = "\n".join(texts)
        avg_conf = float(np.mean(confidences))
        logger.info("✔ EasyOCR done | words=%d | avg_conf=%.3f | text_len=%d | %.1fs",
                    len(texts), avg_conf, len(raw), elapsed)
        return raw, avg_conf, results
    except Exception as e:
        logger.error("EasyOCR readtext failed: %s", e, exc_info=True)
        return None


def _run_tesseract(image: np.ndarray) -> tuple[str, float] | None:
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed (pip install pytesseract)")
        return None

    try:
        import cv2
        if isinstance(image, str):
            image = cv2.imread(image)
            if image is None:
                return None
        elif not hasattr(image, "ndim"):
            return None

        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        t0 = time.time()
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        elapsed = time.time() - t0
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract executable not found. Install: brew install tesseract (macOS) or apt-get install tesseract-ocr (Ubuntu)")
        return None
    except Exception as e:
        logger.error("Tesseract OCR failed: %s", e, exc_info=True)
        return None

    words, confs = [], []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        text = text.strip()
        try:
            conf_val = float(conf)
        except (TypeError, ValueError):
            continue
        if text and conf_val >= 0:
            words.append(text)
            confs.append(conf_val / 100.0)

    if not words:
        logger.info("✔ Tesseract: no text detected (empty result) | %.1fs", elapsed)
        return "", 0.0
    raw = " ".join(words)
    avg_conf = float(np.mean(confs))
    logger.info("✔ Tesseract done | words=%d | avg_conf=%.3f | text_len=%d | %.1fs",
                len(words), avg_conf, len(raw), elapsed)
    return raw, avg_conf


def _run_fitz_fallback(pdf_path: str | None = None) -> tuple[str, float] | None:
    try:
        import fitz
        import os
        if pdf_path and os.path.exists(pdf_path):
            doc = fitz.open(pdf_path)
            extracted_text = "\n".join(page.get_text() for page in doc)
            if len(extracted_text.strip()) > 10:
                logger.info("✔ PyMuPDF Fallback text extractor succeeded for %s | len=%d", pdf_path, len(extracted_text))
                return extracted_text, 0.88
    except Exception as e:
        logger.warning("PyMuPDF fallback failed: %s", e)
    return None


def extract_text(image: np.ndarray, binary_gray: np.ndarray | None = None) -> OCREngineResult:
    """
    Run dual-engine OCR and return combined text + accuracy.

    Parameters
    ----------
    image       : BGR numpy array (color or sharpened color from preprocess_for_ocr)
    binary_gray : optional grayscale/binary image for Tesseract. When provided,
                  Tesseract receives this cleaner image instead of converting
                  from `image`. Pass the second return value of preprocess_for_ocr().
    """
    result, _ = extract_text_and_bboxes(image, binary_gray=binary_gray)
    return result


def extract_text_and_bboxes(
    image: np.ndarray,
    binary_gray: np.ndarray | None = None,
    doc_type: str | None = None,
) -> tuple["OCREngineResult", list]:
    """
    Run dual-engine OCR and return BOTH the OCREngineResult AND the raw EasyOCR
    bbox list [(bbox, text, conf), ...] in a single EasyOCR inference pass.

    Speed optimization: Tesseract is SKIPPED when:
      - EasyOCR confidence >= CONFIDENCE_SKIP_TESSERACT (default 0.82)
      - The extracted text contains at least MIN_WORDS_FOR_EARLY_STOP words
      - All required fields for `doc_type` are found in the EasyOCR text
    This saves 5-15s per request for clear, high-quality documents.

    Parameters
    ----------
    image       : BGR colour image for EasyOCR
    binary_gray : adaptive-threshold grayscale image for Tesseract (optional)
    doc_type    : document type string for required-field early-stop check

    Returns
    -------
    (OCREngineResult, bbox_list)
    bbox_list is [] when EasyOCR is unavailable or fails.
    """
    t_total = time.time()
    engines_used: list[str] = []
    combined_text_parts: list[str] = []
    weighted_scores: list[float] = []
    bbox_list: list = []

    # ── EasyOCR (primary) ─────────────────────────────────────────────────
    easy_result = _run_easyocr(image)
    if easy_result is not None:
        text, conf, bboxes = easy_result
        combined_text_parts.append(text)
        weighted_scores.append(conf)
        engines_used.append("easyocr")
        bbox_list = bboxes

    # ── Early-stop check: skip Tesseract if EasyOCR is confident enough ───
    easyocr_text = combined_text_parts[0] if combined_text_parts else ""
    easyocr_conf = weighted_scores[0] if weighted_scores else 0.0
    easyocr_word_count = len(easyocr_text.split())

    skip_tesseract = False
    if (
        "easyocr" in engines_used
        and easyocr_conf >= CONFIDENCE_SKIP_TESSERACT
        and easyocr_word_count >= MIN_WORDS_FOR_EARLY_STOP
        and _has_required_fields(easyocr_text, doc_type or "")
    ):
        skip_tesseract = True
        logger.info(
            "⚡ Tesseract SKIPPED — EasyOCR conf=%.3f >= %.2f, words=%d, required fields found for '%s'",
            easyocr_conf, CONFIDENCE_SKIP_TESSERACT, easyocr_word_count, doc_type or "unknown",
        )
    elif "easyocr" in engines_used:
        logger.info(
            "Tesseract will run — EasyOCR conf=%.3f (threshold=%.2f), words=%d, fields_ok=%s",
            easyocr_conf, CONFIDENCE_SKIP_TESSERACT, easyocr_word_count,
            _has_required_fields(easyocr_text, doc_type or ""),
        )

    # ── Tesseract (secondary / fallback) ────────────────────────────────
    if not skip_tesseract:
        tess_input = binary_gray if binary_gray is not None else image
        tess_result = _run_tesseract(tess_input)
        if tess_result is not None:
            text, conf = tess_result
            combined_text_parts.append(text)
            weighted_scores.append(conf)
            engines_used.append("tesseract")
    else:
        logger.info("Tesseract: SKIPPED (EasyOCR early-stop)")

    if not engines_used:
        fitz_res = _run_fitz_fallback()
        if fitz_res is not None:
            text, conf = fitz_res
            combined_text_parts.append(text)
            weighted_scores.append(conf)
            engines_used.append("fitz_pdf_extractor")

    if not engines_used:
        detail_reason = _last_easyocr_error or (
            "No OCR engine is available (EasyOCR and Tesseract both failed to load). "
            "Install at least one: `pip install easyocr` or system package `tesseract-ocr`."
        )
        logger.error("OCR execution failed: %s", detail_reason)
        raise RuntimeError(detail_reason)

    raw_text = "\n".join(combined_text_parts)
    accuracy = float(np.mean(weighted_scores)) if weighted_scores else 0.0

    # Agreement bonus: if both engines ran and produced substantial text
    if len(engines_used) == 2 and all(len(p) > 20 for p in combined_text_parts):
        accuracy = min(1.0, accuracy + 0.03)

    logger.info(
        "✔ OCR merged | engines=%s | accuracy=%.4f | total_text_len=%d | total_time=%.1fs",
        engines_used, round(accuracy, 4), len(raw_text), time.time() - t_total,
    )
    ocr_result = OCREngineResult(raw_text=raw_text, accuracy=round(accuracy, 4), engines_used=engines_used)
    return ocr_result, bbox_list


def warmup_easyocr() -> bool:
    """
    Pre-load the EasyOCR model so the first real request doesn't pay
    the 45-60s cold-start cost. Safe to call from an asyncio startup event
    via asyncio.to_thread(warmup_easyocr).
    Sets _easyocr_ready = True when the model is successfully cached.
    Returns True if model loaded successfully.
    """
    global _easyocr_ready
    logger.info("EasyOCR warmup: pre-loading model...")
    reader = _load_easyocr_reader()
    if reader is not None:
        _easyocr_ready = True
        logger.info("✔ EasyOCR warmup complete — model is ready")
        return True
    logger.warning("EasyOCR warmup: model unavailable")
    return False


def extract_with_bboxes(image: np.ndarray) -> list[tuple]:
    """
    Return raw EasyOCR results as a list of (bbox, text, confidence) tuples.

    PERFORMANCE NOTE: Prefer extract_text_and_bboxes() which runs EasyOCR
    exactly once and returns both the OCREngineResult and the bbox list together.
    This function is kept for backward compatibility with callers that only need
    bboxes and already have the text from elsewhere.

    Returns an empty list if EasyOCR is unavailable.
    """
    reader = _load_easyocr_reader()
    if reader is None:
        logger.warning("extract_with_bboxes: EasyOCR not available, returning []")
        return []
    try:
        with _easyocr_lock:
            results = reader.readtext(image)
        return results
    except Exception as exc:
        logger.warning("extract_with_bboxes failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Structured bounding box data (new — preserves spatial info per word)
# ---------------------------------------------------------------------------

def _easyocr_bboxes_to_structured(
    raw_bboxes: list,
    page_index: int = 0,
) -> list[dict]:
    """
    Convert raw EasyOCR bboxes [(bbox, text, conf), ...] to structured dicts
    with (text, confidence, x, y, width, height, page) per word/line.

    This spatial data enables layout-aware field extraction downstream.
    """
    structured = []
    for bbox, text, conf in raw_bboxes:
        try:
            # bbox is a list of 4 (x, y) corner points
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            structured.append({
                "text": text,
                "confidence": float(conf),
                "x": float(x_min),
                "y": float(y_min),
                "width": float(x_max - x_min),
                "height": float(y_max - y_min),
                "page": page_index,
            })
        except Exception:
            # Malformed bbox — skip this entry
            continue
    return structured


# ---------------------------------------------------------------------------
# Intelligent OCR result fusion (new — deduplicates, selects best)
# ---------------------------------------------------------------------------

def _fuse_ocr_results(
    easyocr_text: str,
    easyocr_conf: float,
    tesseract_text: str,
    tesseract_conf: float,
) -> tuple[str, float]:
    """
    Intelligently merge EasyOCR and Tesseract results.

    Instead of naive concatenation, this function:
    1. Splits both texts into lines
    2. Deduplicates near-identical lines (fuzzy match ratio > 80%)
    3. Keeps the version with higher confidence when lines are similar
    4. Preserves unique lines from both engines
    5. Maintains line order from the primary engine (EasyOCR)

    Returns (merged_text, weighted_accuracy).
    """
    if not easyocr_text.strip() and not tesseract_text.strip():
        return "", 0.0

    if not tesseract_text.strip():
        return easyocr_text, easyocr_conf

    if not easyocr_text.strip():
        return tesseract_text, tesseract_conf

    # Try to use rapidfuzz for fuzzy matching
    try:
        from rapidfuzz import fuzz
        has_fuzz = True
    except ImportError:
        has_fuzz = False

    easy_lines = [ln.strip() for ln in easyocr_text.splitlines() if ln.strip()]
    tess_lines = [ln.strip() for ln in tesseract_text.splitlines() if ln.strip()]

    merged_lines: list[str] = []
    tess_used: set[int] = set()

    for e_line in easy_lines:
        best_match_idx = -1
        best_match_ratio = 0.0

        for t_idx, t_line in enumerate(tess_lines):
            if t_idx in tess_used:
                continue
            if has_fuzz:
                ratio = fuzz.ratio(e_line.lower(), t_line.lower()) / 100.0
            else:
                # Simple exact match fallback
                ratio = 1.0 if e_line.lower() == t_line.lower() else 0.0

            if ratio > best_match_ratio:
                best_match_ratio = ratio
                best_match_idx = t_idx

        if best_match_ratio >= 0.80 and best_match_idx >= 0:
            # Lines are similar — pick the one from the engine with higher confidence
            tess_used.add(best_match_idx)
            if easyocr_conf >= tesseract_conf:
                merged_lines.append(e_line)
            else:
                merged_lines.append(tess_lines[best_match_idx])
        else:
            # Unique EasyOCR line — keep it
            merged_lines.append(e_line)

    # Add unique Tesseract lines (not matched to any EasyOCR line)
    for t_idx, t_line in enumerate(tess_lines):
        if t_idx not in tess_used:
            # Only add if it's not a near-duplicate of an already-merged line
            is_dup = False
            for m_line in merged_lines:
                if has_fuzz:
                    if fuzz.ratio(t_line.lower(), m_line.lower()) >= 80:
                        is_dup = True
                        break
                else:
                    if t_line.lower() == m_line.lower():
                        is_dup = True
                        break
            if not is_dup:
                merged_lines.append(t_line)

    merged_text = "\n".join(merged_lines)

    # Weighted accuracy: favor the engine that contributed more content
    easy_weight = len(easy_lines) / max(1, len(easy_lines) + len(tess_lines))
    tess_weight = 1.0 - easy_weight
    accuracy = (easyocr_conf * easy_weight) + (tesseract_conf * tess_weight)

    # Agreement bonus: if both engines produced similar text, boost confidence
    if has_fuzz and easy_lines and tess_lines:
        # Check overall text similarity
        overall_sim = fuzz.ratio(easyocr_text.lower(), tesseract_text.lower()) / 100.0
        if overall_sim > 0.70:
            accuracy = min(1.0, accuracy + 0.05)

    logger.info(
        "OCR fusion | easy_lines=%d tess_lines=%d merged_lines=%d | "
        "easy_conf=%.3f tess_conf=%.3f merged_conf=%.3f",
        len(easy_lines), len(tess_lines), len(merged_lines),
        easyocr_conf, tesseract_conf, accuracy,
    )

    return merged_text, accuracy


def extract_text_and_bboxes_fused(
    image: np.ndarray,
    binary_gray: np.ndarray | None = None,
    doc_type: str | None = None,
    page_index: int = 0,
) -> tuple["OCREngineResult", list[dict]]:
    """
    Enhanced OCR extraction with intelligent fusion.

    Same interface as extract_text_and_bboxes() but uses _fuse_ocr_results()
    instead of naive concatenation when both engines run.

    Returns (OCREngineResult, structured_bbox_list) where structured_bbox_list
    has spatial info (x, y, width, height, page) per detected word.
    """
    t_total = time.time()
    engines_used: list[str] = []
    structured_bboxes: list[dict] = []

    # ── EasyOCR (primary) ─────────────────────────────────────────────────
    easyocr_text = ""
    easyocr_conf = 0.0
    easy_result = _run_easyocr(image)
    if easy_result is not None:
        easyocr_text, easyocr_conf, raw_bboxes = easy_result
        engines_used.append("easyocr")
        structured_bboxes = _easyocr_bboxes_to_structured(raw_bboxes, page_index)

    # ── Early-stop check ────────────────────────────────────────────────
    easyocr_word_count = len(easyocr_text.split())
    skip_tesseract = False
    if (
        "easyocr" in engines_used
        and easyocr_conf >= CONFIDENCE_SKIP_TESSERACT
        and easyocr_word_count >= MIN_WORDS_FOR_EARLY_STOP
        and _has_required_fields(easyocr_text, doc_type or "")
    ):
        skip_tesseract = True
        logger.info(
            "⚡ Tesseract SKIPPED — EasyOCR conf=%.3f >= %.2f, words=%d",
            easyocr_conf, CONFIDENCE_SKIP_TESSERACT, easyocr_word_count,
        )

    # ── Tesseract (secondary / fallback) ────────────────────────────────
    tesseract_text = ""
    tesseract_conf = 0.0
    if not skip_tesseract:
        tess_input = binary_gray if binary_gray is not None else image
        tess_result = _run_tesseract(tess_input)
        if tess_result is not None:
            tesseract_text, tesseract_conf = tess_result
            engines_used.append("tesseract")

    if not engines_used:
        fitz_res = _run_fitz_fallback()
        if fitz_res is not None:
            text, conf = fitz_res
            easyocr_text = text
            easyocr_conf = conf
            engines_used.append("fitz_pdf_extractor")

    if not engines_used:
        detail_reason = _last_easyocr_error or (
            "No OCR engine is available (EasyOCR and Tesseract both failed to load). "
            "Install at least one: `pip install easyocr` or system package `tesseract-ocr`."
        )
        logger.error("OCR execution failed: %s", detail_reason)
        raise RuntimeError(detail_reason)

    # ── Intelligent fusion ──────────────────────────────────────────────
    if len(engines_used) == 2 and easyocr_text.strip() and tesseract_text.strip():
        raw_text, accuracy = _fuse_ocr_results(
            easyocr_text, easyocr_conf,
            tesseract_text, tesseract_conf,
        )
    elif easyocr_text.strip():
        raw_text = easyocr_text
        accuracy = easyocr_conf
    elif tesseract_text.strip():
        raw_text = tesseract_text
        accuracy = tesseract_conf
    else:
        raw_text = ""
        accuracy = 0.0

    logger.info(
        "✔ OCR fused | engines=%s | accuracy=%.4f | text_len=%d | bboxes=%d | %.1fs",
        engines_used, accuracy, len(raw_text), len(structured_bboxes), time.time() - t_total,
    )

    result = OCREngineResult(
        raw_text=raw_text,
        accuracy=round(accuracy, 4),
        engines_used=engines_used,
    )
    return result, structured_bboxes


def extract_text_multipage(
    pages: list[dict],
    preprocess_fn,
    doc_type: str | None = None,
    is_digital: bool = False,
) -> tuple["OCREngineResult", list[dict]]:
    """
    Process multiple page images through OCR and merge results.

    Parameters
    ----------
    pages          : list of {"index": int, "image": np.ndarray}
    preprocess_fn  : callable(image) -> (color, binary)  — doc_type/is_digital bound via partial
    doc_type       : document type string for engine skip logic
    is_digital     : True for digital PDFs (skip OSD)

    Returns
    -------
    (merged_OCREngineResult, merged_structured_bboxes)
    """
    all_texts: list[str] = []
    all_bboxes: list[dict] = []
    all_confidences: list[float] = []
    all_engines: set[str] = set()

    for page in pages:
        page_idx = page["index"]
        raw_image = page["image"]
        logger.info("OCR multipage: processing page %d | shape=%s", page_idx, raw_image.shape)

        try:
            color_processed, binary_gray = preprocess_fn(raw_image)
        except Exception as exc:
            logger.warning("Page %d preprocessing failed: %s — skipping", page_idx, exc)
            continue

        try:
            page_result, page_bboxes = extract_text_and_bboxes_fused(
                color_processed, binary_gray,
                doc_type=doc_type,
                page_index=page_idx,
            )
        except Exception as exc:
            logger.warning("Page %d OCR failed: %s — skipping", page_idx, exc)
            continue

        if page_result.raw_text.strip():
            all_texts.append(page_result.raw_text)
            all_confidences.append(page_result.accuracy)
            all_engines.update(page_result.engines_used)
        all_bboxes.extend(page_bboxes)

    if not all_texts:
        logger.warning("OCR multipage: no text extracted from any page")
        return OCREngineResult(raw_text="", accuracy=0.0, engines_used=list(all_engines) or ["none"]), []

    merged_text = "\n\n--- PAGE BREAK ---\n\n".join(all_texts)
    avg_accuracy = float(np.mean(all_confidences)) if all_confidences else 0.0

    logger.info(
        "OCR multipage: %d pages produced text | total_len=%d | avg_accuracy=%.3f | engines=%s",
        len(all_texts), len(merged_text), avg_accuracy, list(all_engines),
    )

    result = OCREngineResult(
        raw_text=merged_text,
        accuracy=round(avg_accuracy, 4),
        engines_used=sorted(all_engines),
    )
    return result, all_bboxes
