"""
MODULE 7 support - Image Quality scoring.

Produces a 0-100 "how much can we trust this scan" score from resolution,
sharpness, and contrast. This is deliberately about scan/capture quality,
not fraud per se — a low-quality phone photo of a genuine certificate
should lower our *confidence* in all the other signals rather than being
treated as fraud evidence on its own. That distinction is why it gets a
small weight in Module 7's fraud probability rather than a large one.
"""
import cv2
import numpy as np


def compute_image_quality_score(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    # Sharpness: Laplacian variance, capped and scaled to 0-100
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = min(sharpness / 500.0, 1.0) * 100

    # Resolution: relative to a reasonable minimum scan size (roughly A4 at 100dpi)
    pixel_count = h * w
    reference_pixels = 827 * 1169  # ~A4 at 100 DPI
    resolution_score = min(pixel_count / reference_pixels, 1.0) * 100

    # Contrast: standard deviation of pixel intensities — washed-out or overly
    # dark scans have low contrast and are harder to trust downstream OCR/CV on
    contrast = float(np.std(gray))
    contrast_score = min(contrast / 60.0, 1.0) * 100

    overall = (sharpness_score * 0.4) + (resolution_score * 0.3) + (contrast_score * 0.3)
    return round(min(max(overall, 0.0), 100.0), 2)
