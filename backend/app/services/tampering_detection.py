"""
MODULE 6 - AI VERIFICATION: TAMPERING & FORGERY DETECTION (MODULE 3)

Pluggable, independent checks architecture for document tampering and forgery detection:
  1. Error Level Analysis (ELA) with compression normalization and heatmap generation.
  2. PDF structure and metadata analysis (producer tools, mod/creation dates, revisions, fonts, image-only).
  3. Optional image checks: Copy-Move clone detection and Noise Inconsistency analysis.
  4. Font and text layout consistency analysis.
  5. Image quality baseline (blur, contrast, brightness, resolution).
  6. Signature and seal region consistency checks.

Guarantees:
  - Check weights, thresholds, ELA JPEG quality, and risk-level bands come from settings/env.
  - Optional checks missing dependencies skip gracefully and record reason in tampering_detail.
  - False-positive mitigation: scans and re-saved PDFs are treated fairly; metadata-only signals cap confidence.
  - Generates colorized ELA heatmap PNG bytes for persistence and authenticated serving.
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

from app.core.config import settings

logger = logging.getLogger("certiverify.tampering")


# ---------------------------------------------------------------------------
# Data Structures & Check Base Class
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """Structured finding with evidence, score, confidence, and status."""
    type: str
    status: str          # DETECTED | WARNING | NORMAL | UNAVAILABLE | SKIPPED
    score: float         # 0-100 contribution from this signal
    confidence: float    # 0-100
    reason: str
    regions: list | None = None   # [{x, y, w, h}]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TamperingCheckResult:
    """Standardized result returned by each independent tampering check."""
    name: str
    score: float                 # 0.0 to 100.0 (higher = more anomalous/tampered)
    flags: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    confidence: float = 80.0     # 0.0 to 100.0
    status: str = "NORMAL"       # NORMAL | WARNING | DETECTED | SKIPPED | UNAVAILABLE
    skipped: bool = False
    skip_reason: Optional[str] = None
    regions: Optional[list] = None


@dataclass
class TamperingContext:
    """Context passed to each pluggable tampering check."""
    file_bytes: bytes
    file_type: str
    image: np.ndarray            # Preprocessed BGR numpy array
    doc_type: Optional[str] = None
    ocr_fields: Optional[dict] = None
    bbox_results: Optional[list] = None


class TamperingCheck(ABC):
    """Abstract base class for independent, pluggable tampering checks."""
    name: str

    @abstractmethod
    def run(self, context: TamperingContext) -> TamperingCheckResult:
        """Execute check and return standardized TamperingCheckResult."""
        pass


@dataclass
class TamperingResult:
    """Final composite tampering analysis result."""
    score: float                                         # 0-100 composite score
    flags: list[str] = field(default_factory=list)
    ela_heatmap_png: Optional[bytes] = None

    risk_level: str = "LOW"                              # LOW | MEDIUM | HIGH | NOT_APPLICABLE
    confidence: float = 0.0                              # 0-100 overall detection confidence
    status: str = "analyzed"                             # analyzed | not_applicable_for_pdf_text_layer | failed: <reason>
    
    # Per-check details dictionary (Module 3 spec)
    tampering_detail: dict[str, Any] = field(default_factory=dict)

    # Backward-compatible sub-dicts
    image_quality: dict = field(default_factory=dict)
    ela: dict = field(default_factory=dict)
    copy_paste: dict = field(default_factory=dict)
    font_consistency: dict = field(default_factory=dict)
    text_analysis: dict = field(default_factory=dict)
    signature: dict = field(default_factory=dict)
    seal: dict = field(default_factory=dict)
    metadata_detail: dict = field(default_factory=dict)
    document_structure: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Check 1: Error Level Analysis (ELA) with Fair Compression Normalization
# ---------------------------------------------------------------------------

class ELACheck(TamperingCheck):
    name = "ela"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        quality = int(getattr(settings, "TAMPERING_ELA_QUALITY", 90))
        anomaly_threshold = float(getattr(settings, "TAMPERING_ELA_ANOMALY_THRESHOLD", 18.0))

        image = context.image
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        original = Image.fromarray(rgb)

        # 1. Resave at target JPEG quality
        buffer = io.BytesIO()
        original.save(buffer, "JPEG", quality=quality)
        buffer.seek(0)
        resaved = Image.open(buffer)

        # 2. Raw error difference
        ela_diff = ImageChops.difference(original, resaved)
        extrema = ela_diff.getextrema()
        max_diff = max((channel[1] for channel in extrema), default=1) or 1
        scale = 255.0 / max_diff
        enhanced_diff = ImageEnhance.Brightness(ela_diff).enhance(scale)
        ela_array = np.array(enhanced_diff)

        # 3. Fair Compression Normalization:
        # Uniform scans or photos naturally have higher baseline error across the whole page.
        # Tampering causes LOCALIZED error discrepancy (a patch that has different compression history).
        raw_diff_gray = cv2.cvtColor(np.array(ela_diff), cv2.COLOR_RGB2GRAY).astype(np.float32)
        diff_gray = cv2.cvtColor(ela_array, cv2.COLOR_RGB2GRAY)
        h, w = raw_diff_gray.shape[:2]
        global_mean = float(np.mean(raw_diff_gray))
        global_std = float(np.std(raw_diff_gray))

        patch_size = 32
        raw_patch_means = []
        for y in range(0, h - patch_size, patch_size):
            for x in range(0, w - patch_size, patch_size):
                patch = raw_diff_gray[y:y + patch_size, x:x + patch_size]
                raw_patch_means.append(float(np.mean(patch)))

        if raw_patch_means:
            median_patch = float(np.median(raw_patch_means))
            p95_patch = float(np.percentile(raw_patch_means, 95))
            # Ratio of localized discrepancy to baseline
            disparity_ratio = (p95_patch - median_patch) / max(median_patch, 0.5)
            patch_std = float(np.std(raw_patch_means))

            # Count significant outlier patches (> global_mean + 2.0 * max(global_std, 0.5))
            threshold_val = global_mean + 2.0 * max(global_std, 0.5)
            outlier_count = sum(1 for p in raw_patch_means if p > threshold_val)
            outlier_pct = (outlier_count / len(raw_patch_means)) * 100.0

            # Normalized ELA score (fair to scans):
            # If the entire scan is uniformly noisy, disparity_ratio is small -> low score.
            # If a localized region was edited, disparity_ratio and patch_std are elevated.
            normalized_score = min(max((disparity_ratio * 25.0) + (patch_std * 8.0) + (outlier_pct * 2.0), 0.0), 100.0)
        else:
            normalized_score = 0.0
            disparity_ratio = 0.0
            outlier_count = 0

        # Legacy raw ELA score (for backwards compatibility)
        legacy_raw_score = round(float(np.mean(ela_array)) / 255.0 * 100.0, 2)
        score = round(normalized_score, 2)

        flags: list[str] = []
        status = "NORMAL"
        if score >= anomaly_threshold:
            status = "WARNING" if score < 45.0 else "DETECTED"
            flags.append(
                f"Elevated ELA localized anomaly (score {score:.1f}/100, disparity {disparity_ratio:.2f}) — "
                "possible localized editing or recompression artifact"
            )

        # Generate colorized heatmap PNG
        heatmap_colored = cv2.applyColorMap(diff_gray, cv2.COLORMAP_JET)
        heatmap_png = _array_to_png_bytes(heatmap_colored)

        detail = {
            "score": score,
            "raw_ela_score": legacy_raw_score,
            "global_mean_error": round(global_mean, 2),
            "global_std_error": round(global_std, 2),
            "disparity_ratio": round(disparity_ratio, 2),
            "outlier_patch_count": outlier_count,
            "jpeg_quality": quality,
            "status": "POSSIBLE_MANIPULATION" if score >= anomaly_threshold else "NORMAL",
            "_heatmap_png": heatmap_png,
        }

        return TamperingCheckResult(
            name=self.name,
            score=score,
            flags=flags,
            detail=detail,
            confidence=80.0,
            status=status,
        )


# ---------------------------------------------------------------------------
# Check 2: PDF Structure and Metadata Analysis
# ---------------------------------------------------------------------------

class PDFStructureMetadataCheck(TamperingCheck):
    name = "pdf_metadata_structure"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        file_bytes = context.file_bytes
        file_type = (context.file_type or "").lower().lstrip(".")
        flags: list[str] = []
        anomalies: list[str] = []
        score = 0.0
        details: dict[str, Any] = {
            "producer": None,
            "creator": None,
            "creation_date": None,
            "modification_date": None,
            "incremental_updates_count": 0,
            "has_differing_fonts": False,
            "is_image_only": False,
            "signals": [],
        }

        suspicious_tools_raw = getattr(
            settings,
            "TAMPERING_SUSPICIOUS_PRODUCERS",
            "photoshop,canva,illustrator,gimp,inkscape,coreldraw,paint.net,affinity,pixelmator,pdfedit",
        )
        suspicious_tools = [t.strip().lower() for t in suspicious_tools_raw.split(",") if t.strip()]

        if file_type == "pdf":
            try:
                import fitz
                with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                    meta = doc.metadata or {}
                    
                    producer = (meta.get("producer") or "").lower()
                    creator = (meta.get("creator") or "").lower()
                    details["producer"] = meta.get("producer")
                    details["creator"] = meta.get("creator")

                    # Signal 1: Suspicious editing software in producer/creator
                    for tool in suspicious_tools:
                        if tool in producer or tool in creator:
                            msg = f"PDF produced/edited with {tool.title()} — document editor metadata detected"
                            anomalies.append(msg)
                            details["signals"].append({"signal": "suspicious_editor", "tool": tool})
                            score = max(score, 50.0)
                            break

                    # Signal 2: Modification date later than creation date
                    create_date = meta.get("creationDate")
                    mod_date = meta.get("modDate")
                    details["creation_date"] = create_date
                    details["modification_date"] = mod_date
                    if create_date and mod_date and create_date != mod_date:
                        msg = "PDF modification date differs from creation date (document re-saved after creation)"
                        anomalies.append(msg)
                        details["signals"].append({"signal": "date_mismatch", "create": create_date, "mod": mod_date})
                        score = max(score, 25.0)

                    # Signal 3: Incremental updates / multiple revisions
                    eof_count = file_bytes.count(b"%%EOF")
                    details["incremental_updates_count"] = eof_count
                    if eof_count > 1:
                        msg = f"PDF contains {eof_count} revision segments (%%EOF markers) — document underwent incremental updates"
                        anomalies.append(msg)
                        details["signals"].append({"signal": "incremental_updates", "count": eof_count})
                        score = max(score, min(20.0 + (eof_count - 1) * 5.0, 45.0))

                    # Signal 4: Embedded fonts differing between regions
                    font_names: set[str] = set()
                    text_len = 0
                    for page in doc:
                        text_len += len(page.get_text().strip())
                        for f in page.get_fonts():
                            if len(f) > 3 and f[3]:
                                font_names.add(str(f[3]))

                    details["font_families_count"] = len(font_names)
                    details["fonts_detected"] = list(font_names)[:10]
                    if len(font_names) >= 4:
                        msg = f"Multiple distinct font families detected across document regions ({len(font_names)} fonts)"
                        anomalies.append(msg)
                        details["has_differing_fonts"] = True
                        details["signals"].append({"signal": "differing_fonts", "count": len(font_names)})
                        score = max(score, 20.0)

                    # Signal 5: Image-only pages (scanned document with no native text layer)
                    has_images = any(len(p.get_images()) > 0 for p in doc)
                    if text_len < 10 and has_images:
                        details["is_image_only"] = True
                        details["signals"].append({"signal": "image_only_page"})
            except Exception as exc:
                logger.debug("PDF structure metadata check non-fatal error: %s", exc)
                details["error"] = str(exc)

        else:
            # Image EXIF checks
            try:
                pil_img = Image.open(io.BytesIO(file_bytes))
                exif = pil_img.getexif()
                software = exif.get(305)
                if software:
                    sw_lower = str(software).lower()
                    details["software"] = str(software)
                    for tool in suspicious_tools:
                        if tool in sw_lower:
                            anomalies.append(f"Image EXIF Software tag indicates editing with '{software}'")
                            details["signals"].append({"signal": "suspicious_image_editor", "software": str(software)})
                            score = max(score, 50.0)
                            break
            except Exception:
                pass

        flags.extend(anomalies)
        status = "NORMAL"
        if score >= 45:
            status = "WARNING"
        elif score >= 20:
            status = "MINOR_WARNING"

        details["status"] = status
        details["anomalies"] = anomalies
        details["score"] = round(score, 2)

        return TamperingCheckResult(
            name=self.name,
            score=round(score, 2),
            flags=flags,
            detail=details,
            confidence=85.0 if not anomalies else 65.0,  # Signals, not absolute proof
            status=status,
        )


# ---------------------------------------------------------------------------
# Check 3: Optional Copy-Move / Clone Detection
# ---------------------------------------------------------------------------

class CopyMoveCheck(TamperingCheck):
    name = "copy_move"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        min_cluster = int(getattr(settings, "TAMPERING_COPY_MOVE_MIN_MATCHES", 12))
        try:
            image = context.image
            count, regions = _detect_clone_regions_with_boxes(image)
            risk = _clone_risk(count)
            flags: list[str] = []
            status = "NORMAL"
            if count >= min_cluster:
                status = "DETECTED"
                flags.append(
                    f"Copy-paste anomaly: {count} keypoint pairs share identical spatial displacement "
                    "(possible duplicated/cloned content)"
                )

            detail = {
                "detected": count >= min_cluster,
                "score": round(risk, 2),
                "cluster_size": count,
                "regions": regions,
                "status": status,
            }
            return TamperingCheckResult(
                name=self.name,
                score=round(risk, 2),
                flags=flags,
                detail=detail,
                confidence=70.0,
                status=status,
                regions=regions,
            )
        except Exception as exc:
            logger.info("Copy-move check skipped or unavailable: %s", exc)
            return TamperingCheckResult(
                name=self.name,
                score=0.0,
                flags=[],
                detail={"status": "skipped", "reason": f"Feature matcher unavailable: {exc}"},
                confidence=0.0,
                status="SKIPPED",
                skipped=True,
                skip_reason=str(exc),
            )


# ---------------------------------------------------------------------------
# Check 4: Optional Noise Inconsistency Check
# ---------------------------------------------------------------------------

class NoiseInconsistencyCheck(TamperingCheck):
    name = "noise_inconsistency"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        try:
            image = context.image
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]

            # High-pass / median filter residual to isolate high-frequency sensor/compression noise
            median = cv2.medianBlur(gray, 3)
            residual = cv2.absdiff(gray, median)

            tile_size = 32
            tile_stds = []
            for y in range(0, h - tile_size, tile_size):
                for x in range(0, w - tile_size, tile_size):
                    # Filter out purely blank white/black document margins
                    tile_gray = gray[y:y + tile_size, x:x + tile_size]
                    if np.mean(tile_gray) > 248 or np.mean(tile_gray) < 8:
                        continue
                    tile_res = residual[y:y + tile_size, x:x + tile_size]
                    tile_stds.append(float(np.std(tile_res)))

            if len(tile_stds) < 15:
                return TamperingCheckResult(
                    name=self.name,
                    score=0.0,
                    flags=[],
                    detail={"status": "NORMAL", "reason": "Insufficient text/content tiles for noise distribution"},
                    confidence=60.0,
                    status="NORMAL",
                )

            mean_noise = float(np.mean(tile_stds))
            std_noise = float(np.std(tile_stds))
            cv_noise = std_noise / max(mean_noise, 0.5)

            # Spliced regions create distinct noise clusters or extreme variance
            outlier_tiles = sum(1 for s in tile_stds if abs(s - mean_noise) > 3.0 * max(std_noise, 0.5))
            outlier_pct = (outlier_tiles / len(tile_stds)) * 100.0

            # Score based on noise variance across document tiles
            score = 0.0
            flags: list[str] = []
            status = "NORMAL"

            if cv_noise > 0.70 or outlier_pct > 3.0:
                score = min(max((cv_noise - 0.70) * 120.0 + (outlier_pct * 4.0), 20.0), 100.0)
                status = "WARNING" if score < 60.0 else "DETECTED"
                flags.append(
                    f"Noise level inconsistency across image tiles (CV={cv_noise:.2f}, outliers={outlier_pct:.1f}%) — "
                    "possible spliced or digitally inserted elements"
                )

            detail = {
                "score": round(score, 2),
                "mean_noise": round(mean_noise, 2),
                "noise_std": round(std_noise, 2),
                "noise_cv": round(cv_noise, 3),
                "outlier_tile_count": outlier_tiles,
                "tiles_analyzed": len(tile_stds),
                "status": status,
            }
            return TamperingCheckResult(
                name=self.name,
                score=round(score, 2),
                flags=flags,
                detail=detail,
                confidence=70.0,
                status=status,
            )
        except Exception as exc:
            logger.info("Noise inconsistency check skipped: %s", exc)
            return TamperingCheckResult(
                name=self.name,
                score=0.0,
                flags=[],
                detail={"status": "skipped", "reason": f"Noise analysis unavailable: {exc}"},
                confidence=0.0,
                status="SKIPPED",
                skipped=True,
                skip_reason=str(exc),
            )


# ---------------------------------------------------------------------------
# Check 5: Font & Text Layout Consistency
# ---------------------------------------------------------------------------

class FontLayoutCheck(TamperingCheck):
    name = "font_layout"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        image = context.image
        bbox_results = context.bbox_results

        font_res = _analyze_font_consistency(image, bbox_results)
        text_res = _analyze_text_layout(image)

        font_risk = max(0.0, 100.0 - font_res["score"])
        text_risk = max(0.0, 100.0 - text_res["score"])
        combined_score = round(min((font_risk * 0.6) + (text_risk * 0.4), 100.0), 2)

        flags: list[str] = []
        if font_res["status"] == "POSSIBLE_EDIT":
            flags.append("Font inconsistency detected: text regions differ in apparent size or stroke weight")
        if text_res["status"] == "ANOMALOUS":
            flags.append(f"Text layout anomaly: {text_res.get('detail', 'irregular baseline spacing')}")

        status = "WARNING" if combined_score > 25.0 else "NORMAL"
        detail = {
            "score": combined_score,
            "font_consistency": font_res,
            "text_layout": text_res,
            "status": status,
        }
        return TamperingCheckResult(
            name=self.name,
            score=combined_score,
            flags=flags,
            detail=detail,
            confidence=65.0,
            status=status,
        )


# ---------------------------------------------------------------------------
# Check 6: Image Quality Baseline
# ---------------------------------------------------------------------------

class ImageQualityCheck(TamperingCheck):
    name = "image_quality"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        iq = _analyze_image_quality(context.image)
        # Low quality contributes to risk only as a modifier
        score = round(max(0.0, 100.0 - iq["score"]) * 0.4, 2)
        flags: list[str] = []
        if iq["score"] < 40:
            flags.append(f"Low image quality ({iq['score']:.0f}/100) — {iq['detail']} (does not prove forgery)")

        return TamperingCheckResult(
            name=self.name,
            score=score,
            flags=flags,
            detail=iq,
            confidence=90.0,
            status="WARNING" if iq["score"] < 40 else "NORMAL",
        )


# ---------------------------------------------------------------------------
# Check 7: Signature and Seal Region Analysis
# ---------------------------------------------------------------------------

class SignatureSealCheck(TamperingCheck):
    name = "signature_seal"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        sig = _analyze_signature(context.image)
        seal = _analyze_seal(context.image)

        score = round(max(sig["anomaly_score"], seal["anomaly_score"]), 2)
        flags: list[str] = []
        if sig["anomaly_score"] > 30:
            flags.append(f"Signature region anomaly: {sig['reason']}")
        if seal["anomaly_score"] > 30:
            flags.append(f"Seal/stamp region anomaly: {seal['reason']}")

        status = "WARNING" if score > 30 else "NORMAL"
        return TamperingCheckResult(
            name=self.name,
            score=score,
            flags=flags,
            detail={"signature": sig, "seal": seal, "score": score},
            confidence=55.0,
            status=status,
        )


# ---------------------------------------------------------------------------
# Check 8: Document Structure Check
# ---------------------------------------------------------------------------

class DocumentStructureCheck(TamperingCheck):
    name = "document_structure"

    def run(self, context: TamperingContext) -> TamperingCheckResult:
        struct = _check_document_structure(context.doc_type, context.ocr_fields)
        flags: list[str] = []
        if struct["anomaly_score"] > 0 and struct["missing_fields"]:
            flags.append(f"Expected fields missing for {context.doc_type}: {', '.join(struct['missing_fields'])}")

        return TamperingCheckResult(
            name=self.name,
            score=round(struct["anomaly_score"], 2),
            flags=flags,
            detail=struct,
            confidence=70.0,
            status="ANOMALY" if struct["anomaly_score"] > 20 else "NORMAL",
        )


# ---------------------------------------------------------------------------
# Pluggable Registry & Configurable Evaluator
# ---------------------------------------------------------------------------

def get_default_tampering_checks() -> list[TamperingCheck]:
    """Returns the ordered list of pluggable tampering checks."""
    return [
        ELACheck(),
        PDFStructureMetadataCheck(),
        CopyMoveCheck(),
        NoiseInconsistencyCheck(),
        FontLayoutCheck(),
        ImageQualityCheck(),
        SignatureSealCheck(),
        DocumentStructureCheck(),
    ]


def _parse_weights(configured_weights_raw: Any) -> dict[str, float]:
    defaults = {
        "ela": 0.25,
        "pdf_metadata_structure": 0.20,
        "copy_move": 0.20,
        "noise_inconsistency": 0.15,
        "font_layout": 0.10,
        "image_quality": 0.05,
        "signature_seal": 0.05,
    }
    if not configured_weights_raw:
        return defaults

    if isinstance(configured_weights_raw, dict):
        return configured_weights_raw

    try:
        loaded = json.loads(str(configured_weights_raw))
        if isinstance(loaded, dict):
            return {k: float(v) for k, v in loaded.items()}
    except Exception:
        pass
    return defaults


def _parse_risk_bands(configured_bands_raw: Any) -> list[tuple[float, str]]:
    defaults = [(25.0, "LOW"), (60.0, "MEDIUM"), (101.0, "HIGH")]
    if not configured_bands_raw:
        return defaults

    try:
        bands_dict = json.loads(str(configured_bands_raw)) if isinstance(configured_bands_raw, str) else configured_bands_raw
        if isinstance(bands_dict, dict):
            # Sort by threshold value ascending
            items = sorted(bands_dict.items(), key=lambda kv: float(kv[1]))
            return [(float(v), str(k).upper()) for k, v in items]
    except Exception:
        pass
    return defaults


# ---------------------------------------------------------------------------
# Pure Digital Vector PDF Check
# ---------------------------------------------------------------------------

def is_pdf_pure_text_layer(file_bytes: bytes, file_type: str) -> bool:
    """Detect if a PDF is a native vector text document with no raster images to manipulate."""
    ft = file_type.lower().lstrip(".")
    if ft != "pdf" or not file_bytes:
        return False
    try:
        import fitz
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            has_text = any(len(p.get_text().strip()) > 30 for p in doc)
            has_images = any(len(p.get_images()) > 0 for p in doc)
            return has_text and not has_images
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main Entry Point: analyze_tampering
# ---------------------------------------------------------------------------

def analyze_tampering(
    file_bytes: bytes,
    file_type: str,
    image: np.ndarray,
    doc_type: Optional[str] = None,
    ocr_fields: Optional[dict] = None,
    bbox_results: Optional[list] = None,
    allow_pdf_text_layer_check: bool = True,
) -> TamperingResult:
    """
    Main entry point for Module 3 Tampering & Forgery Detection.
    Executes pluggable check pipeline, weighs scores, and produces TamperingResult.
    """
    # 1. Fast-path: Digital vector text PDF with no raster images
    if allow_pdf_text_layer_check and is_pdf_pure_text_layer(file_bytes, file_type):
        meta_check = PDFStructureMetadataCheck().run(
            TamperingContext(file_bytes, file_type, image, doc_type, ocr_fields, bbox_results)
        )
        return TamperingResult(
            score=0.0,
            flags=["Image forensics not applicable: digital PDF vector text layer with no raster images"],
            ela_heatmap_png=None,
            risk_level="NOT_APPLICABLE",
            confidence=95.0,
            status="not_applicable_for_pdf_text_layer",
            tampering_detail={"pdf_metadata_structure": meta_check.detail, "status": "not_applicable_for_pdf_text_layer"},
            metadata_detail=meta_check.detail,
            findings=[Finding("metadata", meta_check.status, meta_check.score, 95.0, "Digital vector PDF text layer")],
        )

    t_start = time.time()
    context = TamperingContext(
        file_bytes=file_bytes,
        file_type=file_type,
        image=image,
        doc_type=doc_type,
        ocr_fields=ocr_fields,
        bbox_results=bbox_results,
    )

    # 2. Execute all pluggable checks
    checks = get_default_tampering_checks()
    check_results: dict[str, TamperingCheckResult] = {}
    flags: list[str] = []
    findings: list[Finding] = []
    ela_heatmap_bytes: Optional[bytes] = None

    for chk in checks:
        try:
            res = chk.run(context)
            check_results[chk.name] = res
            if not res.skipped and res.flags:
                flags.extend(res.flags)

            findings.append(Finding(
                type=chk.name,
                status=res.status,
                score=res.score,
                confidence=res.confidence,
                reason="; ".join(res.flags) if res.flags else f"{chk.name} check normal",
                regions=res.regions,
            ))

            if chk.name == "ela" and "_heatmap_png" in res.detail:
                ela_heatmap_bytes = res.detail["_heatmap_png"]

        except Exception as exc:
            logger.error("Tampering check '%s' raised unexpected exception: %s", chk.name, exc, exc_info=True)
            check_results[chk.name] = TamperingCheckResult(
                name=chk.name,
                score=0.0,
                detail={"status": "failed", "error": str(exc)},
                skipped=True,
                skip_reason=str(exc),
            )

    # 3. Weighted Score Combination across active (non-skipped) checks
    configured_weights = _parse_weights(getattr(settings, "TAMPERING_CHECK_WEIGHTS", None))
    active_weights: dict[str, float] = {}
    active_scores: dict[str, float] = {}

    for name, r in check_results.items():
        if not r.skipped and name in configured_weights:
            w = configured_weights[name]
            active_weights[name] = w
            active_scores[name] = r.score

    total_weight = sum(active_weights.values())
    if total_weight > 0:
        composite_score = sum(active_weights[k] * active_scores[k] for k in active_weights) / total_weight
    else:
        composite_score = 0.0

    composite_score = round(min(max(composite_score, 0.0), 100.0), 2)

    # 4. False Positive Mitigation:
    # If the only anomalies are metadata/date signals while visual checks (ELA, copy_move, noise)
    # show no localized image manipulation, cap the confidence to prevent false alarms on re-saved scans.
    meta_result = check_results.get("pdf_metadata_structure")
    meta_has_signals = meta_result and meta_result.score >= 20.0
    
    visual_anomalies = any(
        check_results.get(name) and check_results[name].score >= 25.0
        for name in ("ela", "copy_move", "noise_inconsistency")
    )

    all_confidences = [r.confidence for r in check_results.values() if not r.skipped]
    base_confidence = float(np.mean(all_confidences)) if all_confidences else 70.0

    if meta_has_signals and not visual_anomalies:
        cap = float(getattr(settings, "TAMPERING_METADATA_ONLY_CONFIDENCE_CAP", 40.0))
        final_confidence = round(min(base_confidence, cap), 1)
        flags.append(
            "Note: Document metadata indicates re-saving or modification, but no localized image tampering "
            "was detected (typical for re-saved scans or print drivers)"
        )
    else:
        final_confidence = round(base_confidence, 1)

    # 5. Risk Level Classification from Configurable Bands
    risk_bands = _parse_risk_bands(getattr(settings, "TAMPERING_RISK_BANDS", None))
    risk_level = "LOW"
    for threshold, label in risk_bands:
        if composite_score <= threshold:
            risk_level = label
            break

    # 6. Detailed breakdown per check
    tampering_detail: dict[str, Any] = {
        "status": "analyzed",
        "composite_score": composite_score,
        "risk_level": risk_level,
        "confidence": final_confidence,
        "active_weights": active_weights,
        "checks": {
            name: {
                "score": r.score,
                "status": r.status,
                "skipped": r.skipped,
                "flags": r.flags,
                "detail": {k: v for k, v in r.detail.items() if not k.startswith("_")},
                **({"skip_reason": r.skip_reason} if r.skipped else {}),
            }
            for name, r in check_results.items()
        },
    }

    elapsed = round(time.time() - t_start, 2)
    logger.info(
        "Tampering analysis complete | score=%.1f | risk=%s | conf=%.1f | checks=%d | time=%.2fs",
        composite_score, risk_level, final_confidence, len(check_results), elapsed,
    )

    ela_dict = {
        k: v for k, v in check_results.get("ela", TamperingCheckResult("ela", 0.0)).detail.items()
        if not k.startswith("_")
    }

    return TamperingResult(
        score=composite_score,
        flags=flags,
        ela_heatmap_png=ela_heatmap_bytes,
        risk_level=risk_level,
        confidence=final_confidence,
        status="analyzed",
        tampering_detail=tampering_detail,
        image_quality=check_results.get("image_quality", TamperingCheckResult("iq", 0.0)).detail,
        ela=ela_dict,
        copy_paste=check_results.get("copy_move", TamperingCheckResult("cp", 0.0)).detail,
        font_consistency=check_results.get("font_layout", TamperingCheckResult("fl", 0.0)).detail.get("font_consistency", {}),
        text_analysis=check_results.get("font_layout", TamperingCheckResult("fl", 0.0)).detail.get("text_layout", {}),
        signature=check_results.get("signature_seal", TamperingCheckResult("ss", 0.0)).detail.get("signature", {}),
        seal=check_results.get("signature_seal", TamperingCheckResult("ss", 0.0)).detail.get("seal", {}),
        metadata_detail=check_results.get("pdf_metadata_structure", TamperingCheckResult("meta", 0.0)).detail,
        document_structure=check_results.get("document_structure", TamperingCheckResult("ds", 0.0)).detail,
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
# Helper Functions (Fast & Memory Efficient)
# ---------------------------------------------------------------------------

def compute_ela(image: np.ndarray, quality: int = 90) -> tuple[np.ndarray, float]:
    """Backward-compatible wrapper for ELA calculation."""
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


def _analyze_image_quality(image: np.ndarray) -> dict:
    h, w = image.shape[:2]
    megapixels = (h * w) / 1_000_000
    res_score = min(megapixels / 2.0, 1.0) * 100

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score = min(lap_var / 500.0, 1.0) * 100

    contrast = float(np.std(gray))
    contrast_score = min(contrast / 60.0, 1.0) * 100

    median = cv2.medianBlur(gray, 3)
    noise_sigma = float(np.std(cv2.absdiff(gray, median)))
    noise_score = max(0.0, 100.0 - noise_sigma * 5.0)

    mean_bright = float(np.mean(gray))
    bright_score = 100.0 - abs(mean_bright - 128) / 128.0 * 50.0

    overall = (res_score * 0.25 + blur_score * 0.30 + contrast_score * 0.20 +
               noise_score * 0.15 + bright_score * 0.10)

    detail_parts = []
    if blur_score < 30:
        detail_parts.append("low sharpness/blurry")
    if contrast_score < 30:
        detail_parts.append("low contrast")
    if res_score < 30:
        detail_parts.append("low resolution")

    detail = "; ".join(detail_parts) if detail_parts else "Good overall image quality"
    return {
        "score": round(overall, 1),
        "detail": detail,
        "metrics": {
            "resolution": round(res_score, 1),
            "sharpness": round(blur_score, 1),
            "contrast": round(contrast_score, 1),
            "noise": round(noise_score, 1),
            "brightness": round(bright_score, 1),
        },
    }


def _detect_clone_regions_with_boxes(
    image: np.ndarray,
    hamming_threshold: int = 25,
    min_spatial_distance: float = 25.0,
    offset_bucket_size: float = 6.0,
) -> tuple[int, list]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    scale = 1.0
    if max(h, w) > 1000:
        scale = 1000.0 / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    orb = cv2.ORB_create(nfeatures=600)
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
    if top_count >= 12:
        sz = int(20 / scale)
        for bucket, kp1, _ in match_details:
            if bucket == top_bucket:
                x, y = int(kp1.pt[0] / scale), int(kp1.pt[1] / scale)
                region_boxes.append({"x": max(x - sz, 0), "y": max(y - sz, 0), "w": sz * 2, "h": sz * 2})

    return top_count, region_boxes[:20]


def _clone_risk(cluster_size: int) -> float:
    if cluster_size < 12:
        return 0.0
    if cluster_size >= 35:
        return 100.0
    return round((cluster_size - 12) / 23.0 * 100.0, 2)


def _analyze_font_consistency(image: np.ndarray, bbox_results: Optional[list] = None) -> dict:
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


def _analyze_text_layout(image: np.ndarray) -> dict:
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        h, w = thresh.shape[:2]
        projection = np.sum(thresh == 255, axis=1).astype(float)
        min_text_density = w * 0.03
        text_rows = np.where(projection > min_text_density)[0]

        if len(text_rows) < 3:
            return {"score": 85.0, "status": "NORMAL", "detail": "Sparse text layout"}

        line_centers: list[int] = []
        block_start = text_rows[0]
        prev = text_rows[0]
        for r in text_rows[1:]:
            if r - prev > 4:
                line_centers.append((block_start + prev) // 2)
                block_start = r
            prev = r
        line_centers.append((block_start + prev) // 2)

        spacing_penalty = 0.0
        cv_sp = 0.0
        if len(line_centers) >= 3:
            spacings = [line_centers[i + 1] - line_centers[i] for i in range(len(line_centers) - 1)]
            mean_sp = float(np.mean(spacings))
            std_sp = float(np.std(spacings))
            cv_sp = std_sp / max(mean_sp, 1.0)
            if cv_sp > 0.65:
                spacing_penalty = min(cv_sp * 30, 40)

        score = round(max(0.0, 100.0 - spacing_penalty), 2)
        return {
            "score": score,
            "status": "ANOMALOUS" if spacing_penalty > 25 else "NORMAL",
            "detail": f"Line spacing CV={cv_sp:.2f}" if spacing_penalty > 25 else "Normal line layout",
            "line_count": len(line_centers),
        }
    except Exception as exc:
        return {"score": 80.0, "status": "NORMAL", "detail": f"Text layout check unavailable: {exc}"}


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
            anomaly_score = 35.0
            reason = f"Multiple ({len(sig_contours)}) signature-like contours detected"
        else:
            full_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            full_sharp = float(cv2.Laplacian(full_gray, cv2.CV_64F).var())
            sig_sharp = float(cv2.Laplacian(gray_b, cv2.CV_64F).var())
            ratio = sig_sharp / max(full_sharp, 1.0)
            if ratio < 0.25:
                anomaly_score = 25.0
                reason = "Signature region significantly blurrier than document baseline"
            else:
                anomaly_score = 5.0
                reason = "Signature detected and consistent with document quality"

    return {"detected": detected, "anomaly_score": round(anomaly_score, 2), "reason": reason}


def _analyze_seal(image: np.ndarray) -> dict:
    """Fast seal detection with downscaling for sub-second execution."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    scale = 1.0
    if max(h, w) > 800:
        scale = 800.0 / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    blurred = cv2.medianBlur(gray, 5)
    sh, sw = gray.shape[:2]

    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=60,
        param1=100, param2=35, minRadius=15, maxRadius=min(sh, sw) // 3,
    )

    detected = circles is not None and len(circles[0]) > 0
    anomaly_score = 0.0
    reason = "No circular seal detected"

    if detected:
        n = len(circles[0])
        if n > 3:
            anomaly_score = 30.0
            reason = f"Multiple circular seals detected ({n})"
        else:
            anomaly_score = 5.0
            reason = f"Seal detected ({n}) — consistent"

    return {"detected": detected, "anomaly_score": round(anomaly_score, 2), "reason": reason}


def _check_document_structure(doc_type: Optional[str], ocr_fields: Optional[dict]) -> dict:
    doc_structure = {
        "degree_certificate": ["student_name", "university_name", "course", "certificate_number"],
        "diploma": ["student_name", "university_name", "course"],
        "marksheet": ["student_name", "register_number"],
        "sslc": ["student_name", "register_number"],
        "hsc": ["student_name", "register_number"],
        "sslc_marksheet": ["student_name", "register_number"],
        "hsc_marksheet": ["student_name", "register_number"],
        "aadhaar_card": ["student_name"],
        "transfer_certificate": ["student_name", "university_name"],
        "resume": [],
    }

    if not doc_type or doc_type == "resume" or not ocr_fields:
        return {"anomaly_score": 0.0, "missing_fields": [], "reason": "Structure check skipped"}

    required = doc_structure.get(doc_type, [])
    if not required:
        return {"anomaly_score": 0.0, "missing_fields": [], "reason": f"No structural schema for '{doc_type}'"}

    missing = []
    for f in required:
        val = ocr_fields.get(f)
        if not val or (isinstance(val, tuple) and not val[0]):
            missing.append(f)

    anomaly_score = round((len(missing) / len(required)) * 50.0, 2)
    reason = f"Missing expected fields: {', '.join(missing)}" if missing else f"All expected fields present for {doc_type}"
    return {"anomaly_score": anomaly_score, "missing_fields": missing, "reason": reason}


# ---------------------------------------------------------------------------
# Backward-compatible Helper Wrappers
# ---------------------------------------------------------------------------

def check_metadata(file_bytes: bytes, file_type: str) -> list[str]:
    """Backward-compatible wrapper."""
    chk = PDFStructureMetadataCheck()
    dummy_img = np.zeros((10, 10, 3), dtype=np.uint8)
    res = chk.run(TamperingContext(file_bytes, file_type, dummy_img))
    return res.flags


def laplacian_variance(image: np.ndarray) -> float:
    """Backward-compatible wrapper."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def detect_signature(image: np.ndarray) -> bool:
    """Backward-compatible wrapper."""
    return _analyze_signature(image)["detected"]


def detect_seal(image: np.ndarray) -> bool:
    """Backward-compatible wrapper."""
    return _analyze_seal(image)["detected"]


def detect_clone_regions(image: np.ndarray, **kwargs) -> int:
    """Backward-compatible wrapper."""
    count, _ = _detect_clone_regions_with_boxes(image)
    return count


def _array_to_png_bytes(array: np.ndarray) -> bytes:
    image = Image.fromarray(array)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()
