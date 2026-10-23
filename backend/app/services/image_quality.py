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


def compute_image_quality_details(image: np.ndarray) -> dict:
    """
    Measure blur (Laplacian variance), resolution, and contrast from rendered page.
    Returns comprehensive metrics and a 0-1 risk score.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return {
            "overall_score": 50.0,
            "sharpness_score": 50.0,
            "resolution_score": 50.0,
            "contrast_score": 50.0,
            "blur_variance": 0.0,
            "width": 0,
            "height": 0,
            "contrast_std": 0.0,
            "risk": 0.50,
            "is_blurry": False,
            "is_low_res": False,
            "is_low_contrast": False,
        }

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    h, w = gray.shape[:2]

    # Sharpness / Blur: Laplacian variance
    sharpness_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = round(min(sharpness_var / 500.0, 1.0) * 100, 2)
    is_blurry = sharpness_var < 100.0

    # Resolution: relative to standard scan resolution (~827x1169)
    pixel_count = h * w
    ref_pixels = 827 * 1169
    resolution_score = round(min(pixel_count / ref_pixels, 1.0) * 100, 2)
    is_low_res = (w < 600 or h < 800)

    # Contrast: standard deviation of pixel intensities
    contrast_std = float(np.std(gray))
    contrast_score = round(min(contrast_std / 60.0, 1.0) * 100, 2)
    is_low_contrast = contrast_std < 25.0

    overall = round((sharpness_score * 0.4) + (resolution_score * 0.3) + (contrast_score * 0.3), 2)
    overall = min(max(overall, 0.0), 100.0)
    risk = round(max(0.0, min(1.0 - (overall / 100.0), 1.0)), 4)

    return {
        "overall_score": overall,
        "sharpness_score": sharpness_score,
        "resolution_score": resolution_score,
        "contrast_score": contrast_score,
        "blur_variance": round(sharpness_var, 2),
        "width": w,
        "height": h,
        "contrast_std": round(contrast_std, 2),
        "risk": risk,
        "is_blurry": is_blurry,
        "is_low_res": is_low_res,
        "is_low_contrast": is_low_contrast,
    }


def compute_image_quality_score(image: np.ndarray) -> float:
    details = compute_image_quality_details(image)
    return details["overall_score"]

