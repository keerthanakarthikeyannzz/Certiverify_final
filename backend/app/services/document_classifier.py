"""
MODULE 3 - AI DOCUMENT TYPE IDENTIFICATION

Strategy:
  1. Primary: zero-shot classification with a Vision Transformer (CLIP ViT-B/32).
     We don't have a labeled certificate dataset to fine-tune a supervised model,
     so zero-shot is the honest, production-viable way to get a real ViT model
     making the call rather than faking a "trained" classifier.
  2. Ensemble boost: OpenCV layout heuristics (seal/circular-stamp detection via
     Hough circles, QR-code presence, aspect ratio, text density) nudge confidence
     up or down — e.g. a circular seal strongly supports "degree_certificate"/"diploma".
  3. Fallback: if torch/transformers aren't installed or the model can't be loaded
     (e.g. offline dev environment), a pure OpenCV+heuristic rule-based classifier
     keeps the pipeline functional end-to-end rather than hard-failing Module 3.

Swap in a fine-tuned YOLO/ViT checkpoint later by replacing `_classify_with_clip`
once a labeled dataset (see /dataset) is available — the interface (`classify`)
and downstream API/DB contract do not need to change.
"""
import logging
import threading
from functools import lru_cache

import cv2
import numpy as np

from app.models.models import DocTypeEnum
from app.services.image_preprocessing import preprocess_pipeline

logger = logging.getLogger("certiverify.document_classifier")
_clip_lock = threading.Lock()

CANDIDATE_LABELS: dict[DocTypeEnum, str] = {
    DocTypeEnum.DEGREE_CERTIFICATE: "a university degree certificate with a seal and signature",
    DocTypeEnum.MARKSHEET: "an academic marksheet or grade transcript with a table of subjects and marks",
    DocTypeEnum.DIPLOMA: "a diploma certificate from a technical or vocational institute",
    DocTypeEnum.RESUME: "a resume or curriculum vitae document",
    DocTypeEnum.TRANSFER_CERTIFICATE: "a school transfer certificate",
    DocTypeEnum.EXPERIENCE_CERTIFICATE: "a work experience certificate from an employer",
    DocTypeEnum.IDENTITY_CARD: "a government identity card or student ID card",
    DocTypeEnum.UNKNOWN: "an unrelated or unidentifiable scanned document",
}


class ClassificationResult:
    def __init__(self, predicted_type: DocTypeEnum, confidence: float, model_used: str, signals: dict):
        self.predicted_type = predicted_type
        self.confidence = confidence
        self.model_used = model_used
        self.signals = signals


@lru_cache(maxsize=1)
def _load_clip_pipeline():
    """Lazily loads the CLIP zero-shot pipeline once per process. Returns None if unavailable."""
    with _clip_lock:
        try:
            from transformers import pipeline
            return pipeline("zero-shot-image-classification", model="openai/clip-vit-base-patch32", local_files_only=True)
        except Exception:
            try:
                from transformers import pipeline
                return pipeline("zero-shot-image-classification", model="openai/clip-vit-base-patch32")
            except Exception as e:
                logger.warning(f"CLIP ViT pipeline unavailable, falling back to heuristic classifier: {e}")
                return None


def classify(file_bytes: bytes, file_type: str) -> ClassificationResult:
    image = _bytes_to_cv2(file_bytes, file_type)
    processed = preprocess_pipeline(image)
    signals = _extract_layout_signals(processed)

    clip_pipe = _load_clip_pipeline()
    if clip_pipe is not None:
        with _clip_lock:
            predicted_type, confidence = _classify_with_clip(clip_pipe, processed)
        model_used = "clip-vit-base-patch32 (zero-shot)"
    else:
        predicted_type, confidence = _classify_with_heuristics(signals)
        model_used = "opencv-heuristic-fallback"

    predicted_type, confidence = _apply_layout_boost(predicted_type, confidence, signals)
    return ClassificationResult(predicted_type, round(confidence, 4), model_used, signals)


def _bytes_to_cv2(file_bytes: bytes, file_type: str) -> np.ndarray:
    from app.services.image_preprocessing import load_image_as_array
    return load_image_as_array(file_bytes, file_type)


def _classify_with_clip(clip_pipe, image: np.ndarray) -> tuple[DocTypeEnum, float]:
    from PIL import Image as PILImage

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = PILImage.fromarray(rgb)

    labels = list(CANDIDATE_LABELS.values())
    results = clip_pipe(pil_image, candidate_labels=labels)
    # results: [{"label": ..., "score": ...}, ...] sorted descending by score
    top = results[0]
    label_to_type = {v: k for k, v in CANDIDATE_LABELS.items()}
    predicted_type = label_to_type[top["label"]]
    return predicted_type, float(top["score"])


def _extract_layout_signals(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    aspect_ratio = round(w / h, 3) if h else 0.0

    # Seal / stamp detection via Hough circle transform (certificates commonly have a round seal)
    blurred = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
        param1=100, param2=40, minRadius=25, maxRadius=min(h, w) // 3,
    )
    has_circular_seal = circles is not None and len(circles[0]) > 0

    # QR code presence (strong signal for degree_certificate per spec's Module 6 dependency)
    has_qr = _detect_qr_presence(image)

    # Text density via edge density as a cheap proxy (tables in marksheets are edge-dense)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.count_nonzero(edges)) / (h * w)

    return {
        "aspect_ratio": aspect_ratio,
        "has_circular_seal": has_circular_seal,
        "has_qr_code": has_qr,
        "edge_density": round(edge_density, 4),
    }


def _detect_qr_presence(image: np.ndarray) -> bool:
    try:
        from pyzbar.pyzbar import decode
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return len(decode(gray)) > 0
    except Exception:
        return False


def _classify_with_heuristics(signals: dict) -> tuple[DocTypeEnum, float]:
    """Pure rule-based fallback so Module 3 never hard-fails without ML deps installed."""
    if signals["has_qr_code"] and signals["has_circular_seal"]:
        return DocTypeEnum.DEGREE_CERTIFICATE, 0.55
    if signals["has_circular_seal"] and signals["edge_density"] < 0.08:
        return DocTypeEnum.DIPLOMA, 0.45
    if signals["edge_density"] >= 0.12:
        return DocTypeEnum.MARKSHEET, 0.5  # dense grid/table pattern
    if 0.7 <= signals["aspect_ratio"] <= 0.75:
        return DocTypeEnum.IDENTITY_CARD, 0.4  # near credit-card aspect ratio
    return DocTypeEnum.UNKNOWN, 0.3


def _apply_layout_boost(
    predicted_type: DocTypeEnum, confidence: float, signals: dict
) -> tuple[DocTypeEnum, float]:
    """Nudges (never flips) confidence based on corroborating OpenCV signals."""
    boost = 0.0
    if predicted_type in (DocTypeEnum.DEGREE_CERTIFICATE, DocTypeEnum.DIPLOMA) and signals["has_circular_seal"]:
        boost += 0.08
    if predicted_type == DocTypeEnum.DEGREE_CERTIFICATE and signals["has_qr_code"]:
        boost += 0.05
    if predicted_type == DocTypeEnum.MARKSHEET and signals["edge_density"] >= 0.1:
        boost += 0.05
    if predicted_type == DocTypeEnum.IDENTITY_CARD and not (0.6 <= signals["aspect_ratio"] <= 0.8):
        boost -= 0.1  # ID cards are reliably near a fixed aspect ratio; penalize mismatches

    return predicted_type, max(0.0, min(1.0, confidence + boost))


# ===========================================================================
# TEXT-BASED OCR CLASSIFICATION  (Enhancement — added alongside image-based)
# ===========================================================================
# Strategy:
#   1. Normalize OCR text (lowercase, collapse whitespace, strip special chars).
#   2. Score each document type using weighted keyword matching from
#      backend/app/config/document_keywords.json — no keywords hardcoded here.
#   3. If top-2 scores are within a 15% margin, apply regex tiebreaking.
#   4. Return a structured ClassificationResult with confidence %, matched
#      keywords, and a human-readable reason.
#
# This classifier gives PRIORITY over the image-based CLIP/heuristic approach
# for document types where OCR text is the authoritative signal (Aadhaar, TC,
# Marksheet, Resume, Diploma, Degree Certificate).
# ===========================================================================

import json
import pathlib
import re
import unicodedata

_KEYWORDS_PATH = pathlib.Path(__file__).parent.parent / "config" / "document_keywords.json"

# Mapping from JSON key → DocTypeEnum
_DOC_TYPE_MAP: dict[str, DocTypeEnum] = {
    "aadhaar_card":          DocTypeEnum.AADHAAR_CARD,
    "marksheet":             DocTypeEnum.MARKSHEET,
    "transfer_certificate":  DocTypeEnum.TRANSFER_CERTIFICATE,
    "diploma":               DocTypeEnum.DIPLOMA,
    "degree_certificate":    DocTypeEnum.DEGREE_CERTIFICATE,
    "resume":                DocTypeEnum.RESUME,
}


@lru_cache(maxsize=1)
def _load_keyword_config() -> dict:
    """Load and cache the keyword dictionary from document_keywords.json."""
    try:
        with open(_KEYWORDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded document_keywords.json successfully.")
        return data.get("document_types", {})
    except Exception as e:
        logger.error(f"Failed to load document_keywords.json: {e}")
        return {}


def _normalize_text(raw_text: str) -> str:
    """
    Prepare OCR text for keyword matching:
      - Unicode normalize (NFKD) and strip accents
      - Lowercase
      - Collapse multiple whitespace / newlines to single space
      - Remove non-alphanumeric characters except spaces
    """
    # Unicode normalization
    text = unicodedata.normalize("NFKD", raw_text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    # Collapse whitespace
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    # Remove characters that are not alphanumeric or space
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"[ ]{2,}", " ", text).strip()
    return text


def _score_keywords(normalized_text: str, config: dict) -> dict[str, dict]:
    """
    For each document type, compute a weighted keyword score.

    Returns:
        {
          "aadhaar_card": {
              "raw_score": 18,
              "max_score": 40,
              "matched_keywords": ["aadhaar", "uidai", "government of india"],
          },
          ...
        }
    """
    scores: dict[str, dict] = {}
    for doc_key, doc_data in config.items():
        raw_score = 0
        max_score = 0
        matched: list[str] = []

        for kw in doc_data.get("keywords", []):
            phrase = kw["phrase"].lower().strip()
            weight = int(kw.get("weight", 1))
            max_score += weight
            if phrase in normalized_text:
                raw_score += weight
                matched.append(kw["phrase"])

        scores[doc_key] = {
            "raw_score":       raw_score,
            "max_score":       max_score,
            "matched_keywords": matched,
        }
    return scores


def _regex_tiebreak(normalized_text: str, doc_key: str, config: dict) -> int:
    """
    Run all regex validators for a document type.
    Returns count of patterns that matched (used to break ties).
    """
    validators = config.get(doc_key, {}).get("regex_validators", {})
    hits = 0
    for pattern in validators.values():
        try:
            if re.search(pattern, normalized_text, re.IGNORECASE):
                hits += 1
        except re.error:
            pass
    return hits


def _build_reason(doc_key: str, matched_keywords: list[str], regex_hit: bool) -> str:
    """
    Build a human-readable explanation for the classification decision.
    Examples:
      "Strong Aadhaar Card keywords matched: \"uidai\", \"aadhaar number\"."
      "Strong SSLC Marksheet keywords matched: \"secondary school leaving certificate\", \"roll number\"; supported by regex pattern validation."
    """
    count = len(matched_keywords)
    display = _load_keyword_config().get(doc_key, {}).get("display_name", doc_key)

    strength = "Strong" if count >= 3 else ("Moderate" if count == 2 else "Weak")
    parts = [f"{strength} {display} keywords matched"]

    if matched_keywords:
        top_kw = ", ".join(f'"{k}"' for k in matched_keywords[:5])
        parts[0] += f": {top_kw}"

    if regex_hit:
        parts.append("supported by regex pattern validation")

    return "; ".join(parts) + "."


def classify_from_text(raw_text: str, filename: str = "") -> ClassificationResult:
    """
    OCR text-based document classifier.
    """
    logger.info("classify_from_text: starting OCR-based classification.")

    config = _load_keyword_config()
    if not config:
        logger.warning("classify_from_text: keyword config empty, returning UNKNOWN.")
        return ClassificationResult(DocTypeEnum.UNKNOWN, 0.0, "ocr-keyword-scorer", {})

    combined_text = f"{filename} {raw_text}".strip()
    normalized = _normalize_text(combined_text)
    logger.debug("Normalized text snippet: %s", normalized[:200])

    scores = _score_keywords(normalized, config)

    # ---------------------------------------------------------------------------
    # Spec-compliant logging: percentage breakdown for every document type
    # ---------------------------------------------------------------------------
    logger.info("OCR Completed")
    score_lines = []
    for doc_key, sv in scores.items():
        display_n = config.get(doc_key, {}).get("display_name", doc_key)
        pct = round((sv["raw_score"] / sv["max_score"]) * 100) if sv["max_score"] else 0
        score_lines.append((display_n, pct))
        logger.info("  %-30s : %d%%", display_n, pct)
    # Also emit detailed debug line for traceability
    for dk, sv in scores.items():
        logger.debug(
            "classify_from_text | type=%-25s raw_score=%-3d max_score=%-3d matched=%s",
            dk, sv["raw_score"], sv["max_score"], sv["matched_keywords"],
        )

    # Filter to types that matched at least one keyword
    candidates = {k: v for k, v in scores.items() if v["raw_score"] > 0}
    if not candidates:
        logger.info("classify_from_text: no keywords matched → UNKNOWN.")
        return ClassificationResult(
            DocTypeEnum.UNKNOWN, 0.0, "ocr-keyword-scorer",
            {"document_type": "Unknown", "confidence": 0, "matched_keywords": [], "reason": "No keywords matched."}
        )

    # ── ENHANCEMENT: Minimum evidence threshold ────────────────────────────
    # A single generic keyword with weight <= 2 alone must NEVER be sufficient
    # to classify a document. Require at least 2 matched keywords OR one
    # keyword with weight >= 3 (a strong document-specific phrase).
    filtered_candidates = {}
    for k, v in candidates.items():
        matched_kws = v["matched_keywords"]
        if len(matched_kws) >= 2 or v["raw_score"] >= 3:
            filtered_candidates[k] = v
        else:
            logger.info(
                "classify_from_text: '%s' rejected — insufficient evidence (1 weak keyword: %s)",
                k, matched_kws,
            )
    if not filtered_candidates:
        logger.info("classify_from_text: all candidates below minimum evidence threshold → UNKNOWN.")
        return ClassificationResult(
            DocTypeEnum.UNKNOWN, 0.0, "ocr-keyword-scorer",
            {"document_type": "Unknown", "confidence": 0, "matched_keywords": [],
             "reason": "Insufficient evidence — only weak/generic keywords matched."}
        )
    candidates = filtered_candidates

    # ── ENHANCEMENT: Strong Aadhaar evidence override ──────────────────────
    # If Aadhaar-specific phrases are detected, boost Aadhaar score and
    # suppress Identity Card to prevent misclassification.
    _STRONG_AADHAAR_PHRASES = [
        "aadhaar", "uidai", "unique identification authority",
        "your aadhaar no", "aadhaar number", "enrolment no",
    ]
    aadhaar_strong_hits = sum(
        1 for phrase in _STRONG_AADHAAR_PHRASES if phrase in normalized
    )
    if aadhaar_strong_hits >= 2 and "aadhaar_card" in candidates:
        logger.info(
            "classify_from_text: Strong Aadhaar evidence (%d phrases) — "
            "boosting aadhaar_card, suppressing identity_card fallback.",
            aadhaar_strong_hits,
        )
        # Boost Aadhaar score by 50% of current score
        candidates["aadhaar_card"]["raw_score"] = int(
            candidates["aadhaar_card"]["raw_score"] * 1.5
        )

    # ── ENHANCEMENT: Strong Marksheet evidence override ────────────────────
    # If marksheet-specific phrases are detected, ensure marksheet wins
    # over Identity Card or generic types.
    _STRONG_MARKSHEET_PHRASES = [
        "marksheet", "mark sheet", "statement of marks", "mark certificate",
        "secondary school leaving", "higher secondary", "sslc", "hsc",
        "board of examinations", "register number", "total marks",
    ]
    marksheet_strong_hits = sum(
        1 for phrase in _STRONG_MARKSHEET_PHRASES if phrase in normalized
    )
    if marksheet_strong_hits >= 2 and "marksheet" in candidates:
        logger.info(
            "classify_from_text: Strong Marksheet evidence (%d phrases) — "
            "boosting marksheet score.",
            marksheet_strong_hits,
        )
        candidates["marksheet"]["raw_score"] = int(
            candidates["marksheet"]["raw_score"] * 1.3
        )

    # Sort by raw_score descending
    ranked = sorted(candidates.items(), key=lambda x: x[1]["raw_score"], reverse=True)
    top_key, top_val = ranked[0]

    # Tiebreak: if top-2 scores differ by less than 10% of the top score, use regex
    # Spec requirement: "If top two document scores differ by less than 10%,
    # perform regex validation before deciding."
    if len(ranked) > 1:
        second_key, second_val = ranked[1]
        top_s = top_val["raw_score"]
        sec_s = second_val["raw_score"]
        if top_s > 0 and (top_s - sec_s) / top_s < 0.10:
            logger.info(
                "classify_from_text: tie between '%s' (%d) and '%s' (%d) — scores within 10%%, applying regex tiebreak.",
                top_key, top_s, second_key, sec_s,
            )
            top_regex   = _regex_tiebreak(normalized, top_key, config)
            sec_regex   = _regex_tiebreak(normalized, second_key, config)
            logger.info("Regex hits: %s=%d  %s=%d", top_key, top_regex, second_key, sec_regex)
            if sec_regex > top_regex:
                top_key, top_val = second_key, second_val
                logger.info("classify_from_text: regex tiebreak flipped result to '%s'.", top_key)
            regex_hit = True
        else:
            regex_hit = _regex_tiebreak(normalized, top_key, config) > 0
    else:
        regex_hit = _regex_tiebreak(normalized, top_key, config) > 0

    # Confidence: raw_score / max_score, boosted by regex matches
    max_s = top_val["max_score"] or 1
    raw_s = top_val["raw_score"]
    confidence_raw = raw_s / max_s
    if regex_hit:
        confidence_raw = min(1.0, confidence_raw + 0.08)

    confidence_pct = round(confidence_raw * 100)
    matched_kws    = top_val["matched_keywords"]
    reason         = _build_reason(top_key, matched_kws, regex_hit)
    display_name   = config.get(top_key, {}).get("display_name", top_key)
    predicted_type = _DOC_TYPE_MAP.get(top_key, DocTypeEnum.UNKNOWN)

    logger.info(
        "Prediction: %s (confidence=%d%%)",
        display_name, confidence_pct,
    )
    logger.info(
        "classify_from_text RESULT → type='%s' confidence=%d%% matched_keywords=%s",
        display_name, confidence_pct, matched_kws,
    )

    signals = {
        "document_type":     display_name,
        "confidence":        confidence_pct,
        "matched_keywords":  matched_kws,
        "reason":            reason,
    }
    return ClassificationResult(predicted_type, round(confidence_raw, 4), "ocr-keyword-scorer", signals)


