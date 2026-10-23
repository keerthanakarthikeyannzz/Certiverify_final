"""
Image preprocessing for Modules 3, 4, and 6.
Converts uploaded bytes (PDF or image) into a normalized OpenCV BGR array,
and applies cleanup (deskew, denoise, contrast) that measurably improves
downstream OCR and classification accuracy.

Enhancements:
- All PDF pages are rendered and the best (highest text content) page is selected.
- Auto-orientation correction handles 90/180/270-degree rotations via Tesseract OSD.
- Detailed logging at every stage for full observability.
"""
import io
import logging
import traceback

import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger("certiverify.image_preprocessing")


def load_image_as_array(file_bytes: bytes, file_type: str) -> np.ndarray:
    """
    Returns an OpenCV BGR numpy array from PDF (all pages → best page) or image bytes.
    Logs every step; raises RuntimeError with descriptive message on failure.
    """
    file_type = file_type.lower().lstrip(".")
    logger.info("✔ load_image_as_array: file_type=%s size=%d bytes", file_type, len(file_bytes))

    if file_type == "pdf":
        pages = _pdf_pages_to_arrays(file_bytes)
        if not pages:
            raise RuntimeError("PDF file not found or could not be rendered into any page images.")
        # Select the page with the highest text density (best for OCR)
        best = _select_best_page(pages)
        arr = best["image"]
        logger.info("✔ Best page selected | page_index=%d | shape=%s", best["index"], arr.shape)
    else:
        # ── Non-PDF image ────────────────────────────────────────────────────────
        try:
            pil_image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            arr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            logger.info("✔ load_image_as_array: image loaded, shape=%s", arr.shape)
        except Exception as exc:
            logger.error("Failed to open image file: %s\n%s", exc, traceback.format_exc())
            raise RuntimeError(f"Failed to load image file: {exc}") from exc

    # Scale down excessively large images to 2200px max dimension to prevent CPU freeze / timeouts
    max_dim = max(arr.shape[0], arr.shape[1])
    if max_dim > 2200:
        scale = 2200.0 / max_dim
        new_w = int(arr.shape[1] * scale)
        new_h = int(arr.shape[0] * scale)
        arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        logger.info("✔ load_image_as_array: resized from max_dim=%d to shape=%s", max_dim, arr.shape)

    return arr


def _pdf_pages_to_arrays(pdf_bytes: bytes, dpi: int = 200) -> list[dict]:
    """
    Renders ALL pages of a PDF to BGR numpy arrays.

    Strategy (in priority order):
    1. PyMuPDF  (pip install pymupdf)   — no external binary needed
    2. pdf2image (pip install pdf2image) — needs Poppler system package
    3. Raises a clear, descriptive RuntimeError naming exactly what is missing.

    Returns a list of dicts: [{"index": 0, "image": np.ndarray}, ...]
    """
    # ── Strategy 1: PyMuPDF ─────────────────────────────────────────────────
    try:
        import fitz  # PyMuPDF
        logger.info("PDF rendering: using PyMuPDF")
        try:
            pages: list[dict] = []
            zoom = dpi / 72
            matrix = fitz.Matrix(zoom, zoom)
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                page_count = doc.page_count
                logger.info("✔ PDF loaded via PyMuPDF: %d page(s)", page_count)
                for page_num in range(page_count):
                    try:
                        page = doc.load_page(page_num)
                        pix = page.get_pixmap(matrix=matrix)
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                        if pix.n == 4:
                            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                        else:
                            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                        pages.append({"index": page_num, "image": img})
                        logger.info("✔ PDF page %d rendered via PyMuPDF: shape=%s", page_num, img.shape)
                    except Exception as exc:
                        logger.warning("PDF page %d failed to render: %s", page_num, exc)
            if pages:
                return pages
            raise RuntimeError("PyMuPDF rendered 0 usable pages from the PDF.")
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("PyMuPDF failed to open PDF stream: %s\n%s", exc, traceback.format_exc())
            raise RuntimeError(f"PyMuPDF could not open the PDF: {exc}") from exc

    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed, trying pdf2image fallback")
    except RuntimeError:
        raise  # propagate descriptive errors
    except Exception as exc:
        logger.error("PyMuPDF failed: %s\n%s", exc, traceback.format_exc())
        raise RuntimeError(f"PyMuPDF could not render the PDF: {exc}") from exc

    # ── Strategy 2: pdf2image / Poppler ─────────────────────────────────────
    try:
        from pdf2image import convert_from_bytes
        logger.info("PDF rendering: using pdf2image (Poppler)")
        try:
            pil_images = convert_from_bytes(pdf_bytes, dpi=dpi)
        except Exception as exc:
            err_msg = str(exc)
            if "poppler" in err_msg.lower() or "pdfinfo" in err_msg.lower() or "pdftoppm" in err_msg.lower():
                logger.error("Poppler not found: %s", exc)
                raise RuntimeError(
                    "Poppler is not installed. Install it with: "
                    "  macOS: brew install poppler  |  Ubuntu: sudo apt-get install poppler-utils"
                ) from exc
            logger.error("pdf2image failed: %s\n%s", exc, traceback.format_exc())
            raise RuntimeError(f"Failed to convert PDF to image via pdf2image: {exc}") from exc

        if not pil_images:
            raise RuntimeError("pdf2image returned no pages from the PDF.")

        pages = []
        for i, pil_img in enumerate(pil_images):
            try:
                arr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
                pages.append({"index": i, "image": arr})
                logger.info("✔ PDF page %d rendered via pdf2image: shape=%s", i, arr.shape)
            except Exception as exc:
                logger.warning("pdf2image page %d conversion failed: %s", i, exc)
        if pages:
            return pages
        raise RuntimeError("pdf2image rendered 0 usable pages.")

    except ImportError:
        logger.warning("pdf2image not installed")
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("pdf2image unexpected failure: %s\n%s", exc, traceback.format_exc())
        raise RuntimeError(f"Failed to convert PDF to image: {exc}") from exc

    # ── Neither engine available ─────────────────────────────────────────────
    raise RuntimeError(
        "No PDF rendering engine is available. "
        "Install PyMuPDF (recommended — no system deps):  pip install pymupdf  "
        "OR install pdf2image + Poppler:  pip install pdf2image  AND  brew install poppler"
    )


def _select_best_page(pages: list[dict]) -> dict:
    """
    From a list of rendered PDF pages, select the page with the most
    detectable text content (highest non-white pixel density after
    Otsu thresholding). Falls back to page 0 if scoring fails.
    """
    if len(pages) == 1:
        return pages[0]

    best_page = pages[0]
    best_score = -1

    for p in pages:
        try:
            gray = cv2.cvtColor(p["image"], cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            score = int(np.sum(thresh > 0))
            logger.debug("Page %d text pixel score: %d", p["index"], score)
            if score > best_score:
                best_score = score
                best_page = p
        except Exception as exc:
            logger.warning("Page %d scoring failed: %s", p["index"], exc)

    logger.info("Best page: index=%d score=%d (out of %d pages)", best_page["index"], best_score, len(pages))
    return best_page



def deskew(image: np.ndarray, skip_osd: bool = False) -> np.ndarray:
    """
    Two-stage rotation correction:
    1. Coarse: detect and correct 90°/180°/270° rotations via Tesseract OSD.
       SKIPPED when skip_osd=True (digital PDFs rendered by PyMuPDF are always
       upright — OSD adds 5-15s with zero benefit).
    2. Fine:   correct residual minor skew (< 45°) using minAreaRect (< 0.3s).
    Degradation-safe: any exception falls back to returning the original image.
    """
    result = image

    # ── Stage 1: coarse rotation via Tesseract OSD ───────────────────────
    if skip_osd:
        logger.debug("deskew: OSD skipped (digital PDF — always upright)")
    else:
        try:
            import pytesseract
            gray_osd = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            osd = pytesseract.image_to_osd(gray_osd, output_type=pytesseract.Output.DICT, config='--psm 0')
            rotation = int(osd.get("rotate", 0))
            if rotation != 0:
                logger.info("OSD detected rotation: %d° — correcting", rotation)
                if rotation == 90:
                    result = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
                elif rotation == 180:
                    result = cv2.rotate(image, cv2.ROTATE_180)
                elif rotation == 270:
                    result = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
                logger.info("✔ Coarse rotation corrected: %d° | new shape=%s", rotation, result.shape)
            else:
                logger.debug("OSD: no coarse rotation needed")
        except Exception as exc:
            logger.debug("Tesseract OSD skipped (non-fatal): %s", exc)
            result = image

    # ── Stage 2: fine skew via minAreaRect (< 0.3s even on large images) ─
    try:
        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        coords = np.column_stack(np.where(thresh > 0))
        if coords.shape[0] < 20:
            return result

        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) < 0.3:
            return result

        logger.info("Fine skew correction: %.2f°", angle)
        (h, w) = result.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        result = cv2.warpAffine(result, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        logger.info("✔ Fine deskew applied: %.2f°", angle)
    except Exception as exc:
        logger.debug("Fine deskew skipped (non-fatal): %s", exc)

    return result


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """CLAHE contrast enhancement on the L channel — helps faded/scanned certificates."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    merged = cv2.merge((l, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def denoise(image: np.ndarray) -> np.ndarray:
    """
    Fast denoising pipeline:
    - Skips entirely for large high-DPI scans (>= 2000px tall) — PyMuPDF at 200 DPI
      produces clean rasters that don't need heavy denoising. Running
      fastNlMeansDenoisingColored on a 2339x1654 image takes 60-120 seconds.
    - For smaller/lower-res images: a bilateral filter preserves sharp text
      edges while smoothing uniform noise, completing in < 0.5 seconds.
    """
    h, w = image.shape[:2]
    if h >= 2000:
        # High-res scan — no denoising needed, just return as-is
        logger.debug("denoise: skipped (image is %dx%d, already high-res)", h, w)
        return image
    # Bilateral filter: preserves text edges, much faster than NLM
    logger.debug("denoise: applying bilateral filter (h=%d w=%d)", h, w)
    return cv2.bilateralFilter(image, d=5, sigmaColor=30, sigmaSpace=30)


def preprocess_pipeline(image: np.ndarray) -> np.ndarray:
    """Standard cleanup chain applied before classification/OCR."""
    image = deskew(image)
    image = denoise(image)
    image = enhance_contrast(image)
    return image


# ---------------------------------------------------------------------------
# Enhanced OCR preprocessing pipeline (added for improved field extraction)
# ---------------------------------------------------------------------------

def _resize_for_ocr(image: np.ndarray, target_dpi_scale: float = 2.0) -> np.ndarray:
    """
    Upscale small documents so that characters are at least 30px tall —
    the sweet spot for both EasyOCR and Tesseract accuracy.
    Only upscales; never downscales (large scans are already fine).
    """
    h, w = image.shape[:2]
    if h < 1000:  # likely a small/low-res scan
        new_h = int(h * target_dpi_scale)
        new_w = int(w * target_dpi_scale)
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return image


def _sharpen(image: np.ndarray) -> np.ndarray:
    """Unsharp mask — makes character edges crisper without adding noise."""
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=2.0)
    return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)


def _adaptive_threshold_gray(gray: np.ndarray) -> np.ndarray:
    """
    Adaptive (Gaussian) thresholding on a grayscale image.
    Better than global Otsu for documents with uneven lighting (stamps, shadows).
    Returns a binary (0/255) image.
    """
    # Mild Gaussian blur before threshold removes sensor noise
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15, C=8,
    )


def preprocess_for_ocr(
    image: np.ndarray,
    skip_osd: bool = False,
    is_digital: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Enhanced OCR preprocessing pipeline.

    Parameters
    ----------
    image      : BGR numpy array from load_image_as_array
    skip_osd   : when True, skips the expensive Tesseract OSD rotation check.
    is_digital : when True, clean digital PDF render — skips destructive scan preprocessing.

    Returns
    -------
    color_processed : BGR image for EasyOCR
    binary_gray     : adaptive-threshold grayscale image for Tesseract
    """
    if is_digital or skip_osd:
        # Digital PDFs rendered by PyMuPDF are already crisp and clean at 200 DPI.
        # Do not apply CLAHE or unsharp sharpening which corrupts clean vector fonts.
        color_processed = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary_gray = _adaptive_threshold_gray(gray)
        logger.info("preprocess_for_ocr: digital mode -> clean image shape=%s", color_processed.shape)
        return color_processed, binary_gray

    # 1. Deskew — skip OSD for digital PDFs (saves 5-15s)
    img = deskew(image, skip_osd=skip_osd)

    # 2. Denoise — fast bilateral for large images, skipped for very large
    img = denoise(img)

    # 3. CLAHE contrast enhancement
    img = enhance_contrast(img)

    # 4. Resize to OCR-optimal resolution
    img = _resize_for_ocr(img)

    # 5. Sharpen
    img = _sharpen(img)

    color_processed = img

    # 6. Grayscale + adaptive threshold for Tesseract
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary_gray = _adaptive_threshold_gray(gray)

    return color_processed, binary_gray


# ---------------------------------------------------------------------------
# Aadhaar-specific preprocessing pipeline (Priority 1 enhancement)
# ---------------------------------------------------------------------------

def _remove_shadows(image: np.ndarray, is_digital: bool = False) -> np.ndarray:
    """
    Background shadow removal via morphological dilation + divide normalisation.
    Works well on Aadhaar/Marksheet scans with uneven lighting or phone-camera shadows.

    SKIPPED when is_digital=True (digital PDFs rendered by PyMuPDF have uniform
    white backgrounds — shadow removal adds 3-8s with zero benefit and can
    slightly degrade clean text edges).
    """
    if is_digital:
        logger.debug("_remove_shadows: skipped (digital PDF — no camera shadows)")
        return image
    try:
        rgb_planes = cv2.split(image)
        result_planes = []
        for plane in rgb_planes:
            dilated = cv2.dilate(plane, np.ones((7, 7), np.uint8))
            bg = cv2.medianBlur(dilated, 21)
            diff = 255 - cv2.absdiff(plane, bg)
            norm = cv2.normalize(diff, None, alpha=0, beta=255,
                                 norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)
            result_planes.append(norm)
        shadow_free = cv2.merge(result_planes)
        logger.debug("Shadow removal applied")
        return shadow_free
    except Exception as exc:
        logger.debug("Shadow removal skipped (non-fatal): %s", exc)
        return image


def _morphological_cleanup(gray: np.ndarray) -> np.ndarray:
    """
    Morphological opening (removes small noise dots) followed by closing
    (fills small gaps in character strokes). Applied on binary image.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel, iterations=1)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=1)
    return closed


def _remove_border_artifacts(image: np.ndarray, margin_pct: float = 0.01) -> np.ndarray:
    """
    Crop a small border margin to remove scanner/camera edge artifacts
    that can confuse OCR (dark bands, vignetting).
    """
    h, w = image.shape[:2]
    m_h = max(1, int(h * margin_pct))
    m_w = max(1, int(w * margin_pct))
    return image[m_h: h - m_h, m_w: w - m_w]


def _fast_denoise_gray(gray: np.ndarray) -> np.ndarray:
    """
    Fast denoising on a grayscale image using bilateral filter.

    Replaces the previous fastNlMeansDenoising (which took 10-30s on large
    images). Bilateral filter achieves similar noise reduction while preserving
    text edges and completes in < 0.5s even on 3000px-wide images.
    """
    try:
        return cv2.bilateralFilter(gray, d=5, sigmaColor=25, sigmaSpace=25)
    except Exception as exc:
        logger.debug("_fast_denoise_gray bilateral filter skipped: %s", exc)
        return gray


def preprocess_for_aadhaar(
    image: np.ndarray,
    skip_osd: bool = False,
    is_digital: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Priority-1 Aadhaar-specific preprocessing pipeline.

    Applies a stronger sequence than the generic preprocess_for_ocr() to handle
    real-world scanned Aadhaar cards: phone-camera photos, low-light scans,
    compressed PDFs, and cards with shadows or skew.

    Steps
    -----
    1.  Border artifact removal (crop 1% edge)
    2.  Auto-deskew (OSD coarse + minAreaRect fine)
    3.  Shadow removal (morphological background subtraction)
    4.  Bilateral denoise on colour image
    5.  CLAHE contrast enhancement
    6.  Resize to minimum 2400px wide (≈ 300 DPI equivalent)
    7.  Unsharp mask sharpening
    8.  Grayscale conversion
    9.  Fast NL-means denoising on gray
    10. Adaptive Gaussian thresholding (tight blockSize=11, C=6)
    11. Morphological opening + closing

    Returns
    -------
    color_processed : BGR image for EasyOCR
    binary_gray     : binarised grayscale image for Tesseract
    """
    logger.info("[Aadhaar] Starting preprocess_for_aadhaar | input_shape=%s", image.shape)

    # Step 1: Remove border artifacts
    img = _remove_border_artifacts(image)
    logger.info("[Aadhaar] Step 1 border removal done | shape=%s", img.shape)

    # Step 2: Deskew (skip OSD for digital PDFs — saves 5-15s)
    img = deskew(img, skip_osd=skip_osd)
    logger.info("[Aadhaar] Step 2 deskew done | shape=%s skip_osd=%s", img.shape, skip_osd)

    # Step 3: Shadow removal (skip for digital PDFs — saves 3-8s)
    img = _remove_shadows(img, is_digital=is_digital)
    logger.info("[Aadhaar] Step 3 shadow removal done | skipped=%s", is_digital)

    # Step 4: Bilateral denoise (preserve text edges)
    h_img, w_img = img.shape[:2]
    if h_img < 2000:
        img = cv2.bilateralFilter(img, d=7, sigmaColor=40, sigmaSpace=40)
    logger.info("[Aadhaar] Step 4 bilateral denoise done")

    # Step 5: CLAHE contrast enhancement
    img = enhance_contrast(img)
    logger.info("[Aadhaar] Step 5 CLAHE done")

    # Step 6: Resize — ensure at least 2400px wide for 300 DPI equivalent
    h2, w2 = img.shape[:2]
    if w2 < 2400:
        scale = 2400 / w2
        img = cv2.resize(img, (2400, int(h2 * scale)), interpolation=cv2.INTER_CUBIC)
        logger.info("[Aadhaar] Step 6 resize: %.2fx scale → %s", scale, img.shape)
    else:
        logger.info("[Aadhaar] Step 6 resize: skipped (already %dx%d)", w2, h2)

    # Step 7: Sharpening
    img = _sharpen(img)
    logger.info("[Aadhaar] Step 7 sharpen done")

    color_processed = img

    # Step 8: Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    logger.info("[Aadhaar] Step 8 grayscale done")

    # Step 9: NL-means denoising on gray
    gray = _fast_denoise_gray(gray)
    logger.info("[Aadhaar] Step 9 NL-means denoise done")

    # Step 10: Adaptive threshold (tighter than generic: blockSize=11, C=6)
    blurred_g = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred_g, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11, C=6,
    )
    logger.info("[Aadhaar] Step 10 adaptive threshold done")

    # Step 11: Morphological cleanup
    binary = _morphological_cleanup(binary)
    logger.info("[Aadhaar] Step 11 morphological cleanup done")

    logger.info("[Aadhaar] preprocess_for_aadhaar complete | color=%s binary=%s",
                color_processed.shape, binary.shape)
    return color_processed, binary


# ---------------------------------------------------------------------------
# Marksheet-specific preprocessing pipeline (SSLC/HSC Priority enhancement)
# ---------------------------------------------------------------------------

def preprocess_for_marksheet(
    image: np.ndarray,
    skip_osd: bool = False,
    is_digital: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Priority marksheet-specific preprocessing pipeline.

    Applies a tuned sequence for real-world scanned SSLC/HSC marksheets:
    dense subject-mark tables, school letterheads, government stamps,
    low-contrast scans, and multi-column layouts.
    """
    logger.info("[Marksheet] Starting preprocess_for_marksheet | input_shape=%s is_digital=%s", image.shape, is_digital)

    if is_digital:
        # Digital PDFs rendered by PyMuPDF are already crisp and clean at 200 DPI.
        # Heavy CLAHE and aggressive unsharp masking amplify anti-counterfeiting guilloche/watermarks into noise.
        color_processed = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        logger.info("[Marksheet] Digital PDF mode: using crisp raw render | color=%s binary=%s",
                    color_processed.shape, binary.shape)
        return color_processed, binary

    # Step 1: Border artifact removal (0.5% — tighter than Aadhaar)
    margin_pct = 0.005
    h, w = image.shape[:2]
    m_h = max(1, int(h * margin_pct))
    m_w = max(1, int(w * margin_pct))
    img = image[m_h: h - m_h, m_w: w - m_w]
    logger.info("[Marksheet] Step 1 border removal done | shape=%s", img.shape)

    # Step 2: Deskew (skip OSD for digital PDFs — saves 5-15s)
    img = deskew(img, skip_osd=skip_osd)
    logger.info("[Marksheet] Step 2 deskew done | shape=%s skip_osd=%s", img.shape, skip_osd)

    # Step 3: Shadow removal (skip for digital PDFs — saves 3-8s)
    img = _remove_shadows(img, is_digital=is_digital)
    logger.info("[Marksheet] Step 3 shadow removal done | skipped=%s", is_digital)

    # Step 4: CLAHE contrast enhancement
    img = enhance_contrast(img)
    logger.info("[Marksheet] Step 4 CLAHE done")

    # Step 5: Resize — ensure at least 2400px wide
    h2, w2 = img.shape[:2]
    if w2 < 2400:
        scale = 2400 / w2
        img = cv2.resize(img, (2400, int(h2 * scale)), interpolation=cv2.INTER_CUBIC)
        logger.info("[Marksheet] Step 5 resize: %.2fx scale -> %s", scale, img.shape)
    else:
        logger.info("[Marksheet] Step 5 resize: skipped (already %dx%d)", w2, h2)

    # Step 6: Sharpening
    img = _sharpen(img)
    logger.info("[Marksheet] Step 6 sharpen done")

    color_processed = img

    # Step 7: Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    logger.info("[Marksheet] Step 7 grayscale done")

    # Step 8: NL-means denoising on gray
    gray = _fast_denoise_gray(gray)
    logger.info("[Marksheet] Step 8 NL-means denoise done")

    # Step 9: Adaptive threshold (blockSize=15, C=8 — wider blocks for table cells)
    blurred_g = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred_g, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15, C=8,
    )
    logger.info("[Marksheet] Step 9 adaptive threshold done")

    # Step 10: Morphological cleanup
    binary = _morphological_cleanup(binary)
    logger.info("[Marksheet] Step 10 morphological cleanup done")

    logger.info("[Marksheet] preprocess_for_marksheet complete | color=%s binary=%s",
                color_processed.shape, binary.shape)
    return color_processed, binary


# ---------------------------------------------------------------------------
# Resume-specific preprocessing pipeline
# ---------------------------------------------------------------------------

def preprocess_for_resume(
    image: np.ndarray,
    skip_osd: bool = False,
    is_digital: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Resume-specific preprocessing pipeline.

    Tuned for digitally-printed or scanned resume PDFs:
    dense single-column text, consistent fonts, no tables,
    no stamps — but sometimes low DPI / compression artifacts.

    Key differences vs preprocess_for_marksheet():
    - No shadow removal  (resumes are not camera-photographed)
    - No bilateral filter (dense text benefits from crisp edges)
    - Adaptive threshold blockSize=21, C=10 (wider for paragraph text)

    Steps
    -----
    1.  Border artifact removal (0.5%)
    2.  Auto-deskew
    3.  CLAHE contrast enhancement
    4.  Resize to minimum 2400px wide
    5.  Unsharp mask sharpening
    6.  Grayscale conversion
    7.  Adaptive Gaussian thresholding (blockSize=21, C=10)
    8.  Morphological open + close

    Returns
    -------
    color_processed : BGR image for EasyOCR
    binary_gray     : binarised grayscale image for Tesseract
    """
    logger.info("[Resume] Starting preprocess_for_resume | input_shape=%s is_digital=%s", image.shape, is_digital)

    if is_digital or skip_osd:
        color_processed = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary_gray = _adaptive_threshold_gray(gray)
        logger.info("[Resume] Digital mode -> clean image shape=%s", color_processed.shape)
        return color_processed, binary_gray

    # Step 1: Border artifact removal
    margin_pct = 0.005
    h, w = image.shape[:2]
    m_h = max(1, int(h * margin_pct))
    m_w = max(1, int(w * margin_pct))
    img = image[m_h: h - m_h, m_w: w - m_w]
    logger.info("[Resume] Step 1 border removal done | shape=%s", img.shape)

    # Step 2: Deskew (skip OSD for digital PDFs — saves 5-15s)
    img = deskew(img, skip_osd=skip_osd)
    logger.info("[Resume] Step 2 deskew done | shape=%s skip_osd=%s", img.shape, skip_osd)

    # Step 3: CLAHE contrast (no shadow removal needed for resume)
    img = enhance_contrast(img)
    logger.info("[Resume] Step 3 CLAHE done")

    # Step 4: Resize — at least 2400px wide
    h2, w2 = img.shape[:2]
    if w2 < 2400:
        scale = 2400 / w2
        img = cv2.resize(img, (2400, int(h2 * scale)), interpolation=cv2.INTER_CUBIC)
        logger.info("[Resume] Step 4 resize: %.2fx -> %s", scale, img.shape)
    else:
        logger.info("[Resume] Step 4 resize: skipped (already %dx%d)", w2, h2)

    # Step 5: Sharpening
    img = _sharpen(img)
    logger.info("[Resume] Step 5 sharpen done")

    color_processed = img

    # Step 6: Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    logger.info("[Resume] Step 6 grayscale done")

    # Step 7: Adaptive threshold (blockSize=21, C=10 — wider for paragraph text)
    blurred_g = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred_g, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=21, C=10,
    )
    logger.info("[Resume] Step 7 adaptive threshold done")

    # Step 8: Morphological cleanup
    binary = _morphological_cleanup(binary)
    logger.info("[Resume] Step 8 morphological cleanup done")

    logger.info("[Resume] preprocess_for_resume complete | color=%s binary=%s",
                color_processed.shape, binary.shape)
    return color_processed, binary


# ---------------------------------------------------------------------------
# Multi-page support (new — does NOT modify any existing function)
# ---------------------------------------------------------------------------

def load_all_pages(file_bytes: bytes, file_type: str, dpi: int = 200) -> list[dict]:
    """
    Load ALL pages from a PDF or a single page from an image.

    Returns a list of dicts:
        [{"index": 0, "image": np.ndarray (BGR)}, ...]

    For images (JPG/PNG), returns a single-element list.
    For PDFs, returns every renderable page at the given DPI.
    """
    file_type = file_type.lower().lstrip(".")
    logger.info("load_all_pages: file_type=%s size=%d bytes dpi=%d", file_type, len(file_bytes), dpi)

    if file_type == "pdf":
        pages = _pdf_pages_to_arrays(file_bytes, dpi=dpi)
        if not pages:
            raise RuntimeError("PDF file could not be rendered into any page images.")
        logger.info("load_all_pages: %d page(s) rendered from PDF", len(pages))
        return pages

    # Non-PDF image — wrap in single-element list
    try:
        pil_image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        arr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        logger.info("load_all_pages: single image loaded, shape=%s", arr.shape)
        return [{"index": 0, "image": arr}]
    except Exception as exc:
        logger.error("load_all_pages failed to open image: %s", exc)
        raise RuntimeError(f"Failed to load image file: {exc}") from exc


def generate_preprocessing_variants(
    image: np.ndarray,
    skip_osd: bool = False,
) -> list[dict]:
    """
    Generate a small number of preprocessing variants for staged OCR.

    Variants (ordered by expected quality — best first):
        A: Original + contrast enhancement + sharpen
        B: Grayscale + bilateral denoise
        C: Adaptive threshold (binary)
        D: Sharpened grayscale

    Returns list of dicts:
        [{"name": str, "color": np.ndarray, "gray": np.ndarray}, ...]

    The first variant (A) is the primary; run OCR on it first.
    Only try subsequent variants if OCR confidence is low.
    """
    variants = []

    # --- Variant A: Enhanced color (best general-purpose) ---
    try:
        img_a = deskew(image, skip_osd=skip_osd)
        img_a = denoise(img_a)
        img_a = enhance_contrast(img_a)
        img_a = _resize_for_ocr(img_a)
        img_a = _sharpen(img_a)
        gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
        bin_a = _adaptive_threshold_gray(gray_a)
        variants.append({"name": "enhanced_color", "color": img_a, "gray": bin_a})
    except Exception as exc:
        logger.warning("Variant A (enhanced_color) failed: %s", exc)

    # --- Variant B: Grayscale + bilateral denoise ---
    try:
        img_b = deskew(image, skip_osd=skip_osd)
        gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.bilateralFilter(gray_b, d=7, sigmaColor=35, sigmaSpace=35)
        color_b = cv2.cvtColor(gray_b, cv2.COLOR_GRAY2BGR)
        color_b = _resize_for_ocr(color_b)
        gray_b_resized = cv2.cvtColor(color_b, cv2.COLOR_BGR2GRAY)
        variants.append({"name": "grayscale_denoised", "color": color_b, "gray": gray_b_resized})
    except Exception as exc:
        logger.warning("Variant B (grayscale_denoised) failed: %s", exc)

    # --- Variant C: Adaptive threshold ---
    try:
        img_c = deskew(image, skip_osd=skip_osd)
        img_c = _resize_for_ocr(img_c)
        gray_c = cv2.cvtColor(img_c, cv2.COLOR_BGR2GRAY)
        bin_c = _adaptive_threshold_gray(gray_c)
        color_c = cv2.cvtColor(bin_c, cv2.COLOR_GRAY2BGR)
        variants.append({"name": "adaptive_threshold", "color": color_c, "gray": bin_c})
    except Exception as exc:
        logger.warning("Variant C (adaptive_threshold) failed: %s", exc)

    # --- Variant D: Sharpened grayscale ---
    try:
        img_d = deskew(image, skip_osd=skip_osd)
        img_d = enhance_contrast(img_d)
        img_d = _resize_for_ocr(img_d)
        img_d = _sharpen(img_d)
        gray_d = cv2.cvtColor(img_d, cv2.COLOR_BGR2GRAY)
        gray_d_sharp = _sharpen(cv2.cvtColor(gray_d, cv2.COLOR_GRAY2BGR))
        gray_d = cv2.cvtColor(gray_d_sharp, cv2.COLOR_BGR2GRAY)
        color_d = cv2.cvtColor(gray_d, cv2.COLOR_GRAY2BGR)
        variants.append({"name": "sharpened_grayscale", "color": color_d, "gray": gray_d})
    except Exception as exc:
        logger.warning("Variant D (sharpened_grayscale) failed: %s", exc)

    if not variants:
        # Ultimate fallback: just use the raw image
        gray_fallback = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variants.append({"name": "raw_fallback", "color": image, "gray": gray_fallback})

    logger.info("generate_preprocessing_variants: %d variants generated: %s",
                len(variants), [v["name"] for v in variants])
    return variants
