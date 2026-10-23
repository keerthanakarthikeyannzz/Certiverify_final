"""
MODULE 8 - REPORT SERVICE
Generates an official, comprehensive PDF Verification Report using ReportLab.

Report contents:
  - Header with organization branding, watermark, and verification ID
  - Public Verification QR Code flowable
  - Certificate metadata & cryptographic SHA-256 fingerprint
  - Document classification stage
  - OCR extracted fields & accuracy
  - Cross-document comparison (multi-document groups)
  - QR code verification & QR <-> OCR cross-validation
  - Blockchain verification (local_ledger / evm)
  - Tampering detection & ELA heatmap image
  - Duplicate detection
  - AI fraud analysis (weights, contributions, overrides)
  - Trust score with 8-component breakdown & evidence coverage
  - Final prediction verdict, plain-language explanation, and recommended action
  - Cryptographic digital signature block (HMAC-SHA256)
  - Footer with confidentiality notice and system watermark
"""
from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import secrets
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

import qrcode
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfgen_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)

from app.core.config import settings

logger = logging.getLogger("certiverify.report_service")

# ---------------------------------------------------------------------------
# Font management: Multi-lingual Unicode font support (Tamil, Latin, etc.)
# ---------------------------------------------------------------------------
_UNICODE_FONT_NAME = "Helvetica"
_UNICODE_FONT_BOLD = "Helvetica-Bold"
_FONT_INITIALIZED = False


def _init_fonts() -> tuple[str, str]:
    """
    Registers a system Unicode TrueType font (supporting Tamil and international scripts).
    Falls back gracefully to Helvetica if no system Unicode font is installed.
    """
    global _UNICODE_FONT_NAME, _UNICODE_FONT_BOLD, _FONT_INITIALIZED
    if _FONT_INITIALIZED:
        return _UNICODE_FONT_NAME, _UNICODE_FONT_BOLD

    candidate_fonts = [
        # macOS system fonts
        ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        ("/System/Library/Fonts/Supplemental/Tamil MN.ttc", "/System/Library/Fonts/Supplemental/Tamil MN.ttc"),
        # Linux standard fonts
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"),
        ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    ]

    for reg_path, bold_path in candidate_fonts:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont("ReportUnicode", reg_path))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("ReportUnicode-Bold", bold_path))
                    _UNICODE_FONT_BOLD = "ReportUnicode-Bold"
                else:
                    _UNICODE_FONT_BOLD = "ReportUnicode"
                _UNICODE_FONT_NAME = "ReportUnicode"
                logger.info("Registered Unicode report font from %s", reg_path)
                break
            except Exception as exc:
                logger.debug("Could not register candidate font %s: %s", reg_path, exc)

    _FONT_INITIALIZED = True
    return _UNICODE_FONT_NAME, _UNICODE_FONT_BOLD


def get_report_output_dir() -> Path:
    """
    Resolves the canonical report output directory as an absolute Path.
    """
    raw_dir = getattr(settings, "REPORT_OUTPUT_DIR", "uploads/reports") or "uploads/reports"
    p = Path(raw_dir)
    if not p.is_absolute():
        project_root = Path(__file__).resolve().parent.parent.parent
        p = (project_root / raw_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_report_path(stored_path: str | None, verification_id: str | None = None) -> Path | None:
    """
    Resolves a stored report PDF path across execution environments and relative paths.
    """
    if stored_path:
        # 1. Direct path check
        p = Path(stored_path)
        if p.is_file():
            return p.resolve()

        # 2. Relative to backend / project root
        project_root = Path(__file__).resolve().parent.parent.parent
        p_proj = (project_root / stored_path).resolve()
        if p_proj.is_file():
            return p_proj

        # 3. Relative to CWD
        p_cwd = (Path.cwd() / stored_path).resolve()
        if p_cwd.is_file():
            return p_cwd

        # 4. Check filename inside canonical REPORT_OUTPUT_DIR
        out_dir = get_report_output_dir()
        p_out = (out_dir / p.name).resolve()
        if p_out.is_file():
            return p_out

    if verification_id:
        out_dir = get_report_output_dir()
        p_vid = (out_dir / f"{verification_id}.pdf").resolve()
        if p_vid.is_file():
            return p_vid

    return None

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
COLOR_BG_DARK = colors.HexColor("#0b1220")
COLOR_PANEL = colors.HexColor("#111827")
COLOR_BORDER = colors.HexColor("#1f2937")
COLOR_BRAND = colors.HexColor("#2563eb")
COLOR_GENUINE = colors.HexColor("#16a34a")
COLOR_SUSPICIOUS = colors.HexColor("#d97706")
COLOR_FAKE = colors.HexColor("#dc2626")
COLOR_INCONCLUSIVE = colors.HexColor("#6b7280")
COLOR_WHITE = colors.white
COLOR_GRAY = colors.HexColor("#9ca3af")
COLOR_LIGHT_GRAY = colors.HexColor("#e5e7eb")
COLOR_DARK_TEXT = colors.HexColor("#374151")


def _get_page_size():
    ps = (getattr(settings, "REPORT_PAGE_SIZE", "A4") or "A4").strip().upper()
    if ps in ("LETTER", "US_LETTER", "USLETTER"):
        return LETTER
    return A4


def _verdict_color(label: str):
    lbl = (label or "").lower()
    if "genuine" in lbl:
        return COLOR_GENUINE
    if "suspicious" in lbl:
        return COLOR_SUSPICIOUS
    if "fake" in lbl or "forged" in lbl:
        return COLOR_FAKE
    return COLOR_INCONCLUSIVE


# ---------------------------------------------------------------------------
# Page template: adds watermark + header/footer on every page
# ---------------------------------------------------------------------------

class _WatermarkCanvas(pdfgen_canvas.Canvas):
    """Canvas subclass that renders a subtle watermark and running footer on every page."""

    def __init__(self, filename_or_buffer, pagesize=None, **kwargs):
        super().__init__(filename_or_buffer, pagesize=pagesize, **kwargs)
        self._doc_title = f"{settings.REPORT_ORG_NAME} — Verification Report"
        self._font_regular, self._font_bold = _init_fonts()

    def showPage(self):
        self._draw_watermark()
        self._draw_footer()
        super().showPage()

    def _draw_watermark(self):
        self.saveState()
        self.setFont(self._font_bold, 44)
        self.setFillColor(colors.HexColor("#1f2937"))
        self.setFillAlpha(0.04)
        w, h = self._pagesize
        self.translate(w / 2.0, h / 2.0)
        self.rotate(45)
        watermark_text = (getattr(settings, "REPORT_ORG_NAME", "CERTIVERIFY ENTERPRISE") or "CERTIVERIFY ENTERPRISE").upper()
        self.drawCentredString(0, 0, watermark_text)
        self.restoreState()

    def _draw_footer(self):
        self.saveState()
        self.setFont(self._font_regular, 7)
        self.setFillColor(COLOR_GRAY)
        w, h = self._pagesize
        footer_text = getattr(settings, "REPORT_FOOTER_TEXT", "Confidential Verification Report") or "Confidential Verification Report"
        self.drawString(15 * mm, 8 * mm, footer_text)
        self.drawRightString(
            w - 15 * mm,
            8 * mm,
            f"Page {self._pageNumber}  |  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        )
        self.restoreState()


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _styles():
    base = getSampleStyleSheet()
    font_regular, font_bold = _init_fonts()
    S = {}

    def add(name, **kwargs):
        S[name] = ParagraphStyle(name, **kwargs)

    add("Title", fontName=font_bold, fontSize=18, textColor=COLOR_BRAND,
        alignment=TA_LEFT, spaceAfter=2)
    add("Subtitle", fontName=font_regular, fontSize=9, textColor=COLOR_GRAY,
        alignment=TA_LEFT, spaceAfter=2)
    add("SectionHead", fontName=font_bold, fontSize=10, textColor=COLOR_BRAND,
        spaceBefore=10, spaceAfter=4)
    add("Body", fontName=font_regular, fontSize=8, textColor=COLOR_DARK_TEXT,
        leading=11, spaceAfter=2)
    add("SmallGray", fontName=font_regular, fontSize=7, textColor=COLOR_GRAY,
        leading=10)
    add("VerdictGenuine", fontName=font_bold, fontSize=13,
        textColor=COLOR_GENUINE, alignment=TA_CENTER, spaceAfter=3)
    add("VerdictSuspicious", fontName=font_bold, fontSize=13,
        textColor=COLOR_SUSPICIOUS, alignment=TA_CENTER, spaceAfter=3)
    add("VerdictFake", fontName=font_bold, fontSize=13,
        textColor=COLOR_FAKE, alignment=TA_CENTER, spaceAfter=3)
    add("VerdictInconclusive", fontName=font_bold, fontSize=13,
        textColor=COLOR_INCONCLUSIVE, alignment=TA_CENTER, spaceAfter=3)
    add("Label", fontName=font_bold, fontSize=8, textColor=COLOR_DARK_TEXT)
    add("Value", fontName=font_regular, fontSize=8, textColor=COLOR_DARK_TEXT)
    add("Center", fontName=font_regular, fontSize=8, textColor=COLOR_DARK_TEXT,
        alignment=TA_CENTER)
    return S


def _table_style(header_bg=None):
    header_bg = header_bg or COLOR_BRAND
    font_regular, font_bold = _init_fonts()
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("FONTNAME", (0, 1), (-1, -1), font_regular),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), COLOR_DARK_TEXT),
        ("GRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ])


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_header(title: str, styles: dict) -> list:
    return [
        Spacer(1, 2 * mm),
        HRFlowable(width="100%", thickness=0.5, color=COLOR_BRAND, spaceAfter=3),
        Paragraph(title.upper(), styles["SectionHead"]),
    ]


def generate_verification_qr_flowable(verification_id: str) -> RLImage:
    """
    Generates an in-memory PNG QR code for the public verification URL.
    """
    url_template = getattr(settings, "REPORT_VERIFY_URL_TEMPLATE", "http://localhost:3000/verify/{verification_id}")
    verify_url = url_template.format(verification_id=verification_id)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return RLImage(buf, width=28 * mm, height=28 * mm)


def _build_cover(cert: dict, report_row: dict, styles: dict) -> list:
    items = []
    items.append(Spacer(1, 4 * mm))

    # Branding header
    org_name = report_row.get("organization_name") or getattr(settings, "REPORT_ORG_NAME", "CertiVerify Enterprise")
    items.append(Paragraph(org_name, styles["Title"]))
    items.append(Paragraph("Official Certificate Verification & Forensic Audit Dossier", styles["Subtitle"]))
    items.append(Spacer(1, 4 * mm))

    # Verification ID banner
    font_regular, font_bold = _init_fonts()
    vid = report_row.get("verification_id", "CV-UNKNOWN")
    items.append(Paragraph(
        f"Verification Reference ID: <b>{vid}</b>",
        ParagraphStyle("VID", fontName=font_bold, fontSize=9.5,
                       textColor=COLOR_BRAND, spaceAfter=4)
    ))

    # File size display
    size_bytes = cert.get("file_size_bytes") or 0
    size_str = f"{round(size_bytes / 1024, 1)} KB" if size_bytes < 1024 * 1024 else f"{round(size_bytes / (1024*1024), 2)} MB"

    meta_table_data = [
        ["Attribute", "Record Details"],
        ["Certificate Filename", cert.get("original_filename", "—")],
        ["File Format & Size", f"{cert.get('file_type', '—').upper()} ({size_str})"],
        ["Cryptographic SHA-256", (cert.get("sha256_hash") or "—")[:44] + "..."],
        ["Uploaded Timestamp", cert.get("uploaded_at", "—")],
        ["Verification Timestamp", report_row.get("generated_at", "—")],
        ["Auditing Institution", org_name],
        ["Authorized Verifier", f"{report_row.get('verifier_name', 'System')} <{report_row.get('verifier_email', 'noreply@certiverify.ai')}>"],
    ]

    t_meta = Table(meta_table_data, colWidths=[45 * mm, 95 * mm])
    t_meta.setStyle(_table_style())

    # QR Code side block
    qr_flowable = generate_verification_qr_flowable(vid)
    verify_url = getattr(settings, "REPORT_VERIFY_URL_TEMPLATE", "http://localhost:3000/verify/{verification_id}").format(verification_id=vid)
    qr_box = [
        qr_flowable,
        Spacer(1, 1 * mm),
        Paragraph("<font size=6 color='#6b7280'><b>Scan to Verify Online</b></font>", ParagraphStyle("QR1", alignment=TA_CENTER)),
        Paragraph(f"<font size=5 color='#9ca3af'>{verify_url[:35]}...</font>", ParagraphStyle("QR2", alignment=TA_CENTER)),
    ]

    split_table = Table([[t_meta, qr_box]], colWidths=[140 * mm, 40 * mm])
    split_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    items.append(split_table)
    items.append(Spacer(1, 3 * mm))
    return items


def _build_document_type(doc_type_row: Optional[dict], styles: dict) -> list:
    items = _section_header("1. Document Type Identification", styles)
    if not doc_type_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (Document classification was not run).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    pred_type = doc_type_row.get("predicted_type", "unknown")
    if hasattr(pred_type, "value"):
        pred_type = pred_type.value
    data = [
        ["Field", "Value"],
        ["Predicted Type", str(pred_type).replace("_", " ").title()],
        ["Confidence Score", f"{round((doc_type_row.get('confidence_score') or 0) * 100, 1)}%"],
        ["Classification Model", doc_type_row.get("model_used") or "Heuristic & Signature Classifier"],
    ]
    t = Table(data, colWidths=[55 * mm, 125 * mm])
    t.setStyle(_table_style())
    items.append(t)
    return items


def _build_ocr(ocr_row: Optional[dict], styles: dict) -> list:
    items = _section_header("2. OCR Text Extraction & Metadata", styles)
    if not ocr_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (OCR extraction was not run).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    fields = [
        ("Student / Candidate Name", ocr_row.get("student_name")),
        ("University / Organization", ocr_row.get("university_name")),
        ("Register / Enrollment No.", ocr_row.get("register_number")),
        ("Roll Number", ocr_row.get("roll_number")),
        ("Certificate / Serial No.", ocr_row.get("certificate_number")),
        ("Department / Faculty", ocr_row.get("department")),
        ("Course / Degree", ocr_row.get("course")),
        ("CGPA", ocr_row.get("cgpa")),
        ("Percentage / Marks", ocr_row.get("percentage")),
        ("Date of Issue", ocr_row.get("date_of_issue")),
        ("Digital / Wet Signature", "Detected" if ocr_row.get("has_signature") else "Not detected"),
        ("Institutional Seal / Stamp", "Detected" if ocr_row.get("has_seal") else "Not detected"),
        ("OCR Confidence / Accuracy", f"{round((ocr_row.get('ocr_accuracy') or 0) * 100, 1)}%"),
        ("OCR Engine", ocr_row.get("ocr_engine") or "Tesseract / EasyOCR"),
    ]
    data = [["Field", "Extracted Value"]] + [
        [label, str(val) if val is not None and str(val).strip() else "—"] for label, val in fields
    ]
    t = Table(data, colWidths=[55 * mm, 125 * mm])
    t.setStyle(_table_style())
    items.append(t)

    raw = ocr_row.get("raw_text") or ""
    if raw:
        items.append(Spacer(1, 2 * mm))
        items.append(Paragraph("<b>Raw Extracted Text (Excerpt):</b>", styles["Label"]))
        excerpt = textwrap.shorten(raw.replace("\n", " "), width=450, placeholder="…")
        items.append(Paragraph(excerpt, styles["SmallGray"]))
    return items


def _build_comparison(comparison_row: Optional[dict], styles: dict) -> list:
    items = _section_header("3. Cross-Document Group Comparison", styles)
    if not comparison_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (Document comparison requires a multi-document upload group).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    data = [
        ["Field", "Value"],
        ["Consistency Score", f"{round(comparison_row.get('consistency_percentage', 0), 1)}%"],
        ["Matching Identity Fields", ", ".join(comparison_row.get("matching_fields") or []) or "None"],
        ["Mismatched Fields", ", ".join(comparison_row.get("mismatched_fields") or []) or "None"],
        ["Missing Fields", ", ".join(comparison_row.get("missing_fields") or []) or "None"],
    ]
    t = Table(data, colWidths=[55 * mm, 125 * mm])
    t.setStyle(_table_style())
    items.append(t)
    return items


def _build_verification(verification_row: Optional[dict], styles: dict) -> list:
    items = _section_header("4. Forensic Verification & Integrity Analysis", styles)
    if not verification_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (Forensic verification checks have not been executed).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    # --- QR Verification ---
    items.append(Paragraph("<b>A. QR Code Verification</b>", styles["Label"]))
    qr_present = verification_row.get("qr_present")
    if qr_present is False or qr_present is None:
        qr_status = "Not evaluated (No QR code detected on document)" if qr_present is False else "Not evaluated (QR check not run)"
        qr_data = [
            ["Check", "Result"],
            ["QR Code Detected", "No"],
            ["Status", qr_status],
        ]
    else:
        qr_data = [
            ["Check", "Result"],
            ["QR Code Detected", "Yes"],
            ["QR Authenticity", "Valid (Verified)" if verification_row.get("qr_valid") else "Invalid / Untrusted"],
            ["QR Advisory Note", verification_row.get("qr_warning") or "No anomalies detected"],
        ]
        # Cross validation
        cv_status = verification_row.get("cross_validation_status") or "EVALUATED"
        cv_mismatches = verification_row.get("cross_validation_mismatches") or []
        qr_data.append([
            "QR ↔ OCR Consistency",
            f"{len(cv_mismatches)} mismatch(es) found" if cv_mismatches else "All extracted fields match QR payload",
        ])

    t_qr = Table(qr_data, colWidths=[55 * mm, 125 * mm])
    t_qr.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t_qr)
    items.append(Spacer(1, 2 * mm))

    # --- Blockchain Verification ---
    items.append(Paragraph("<b>B. Blockchain & Immutable Hash Ledger</b>", styles["Label"]))
    bc_status = (verification_row.get("blockchain_status") or "").upper()
    provider = getattr(settings, "BLOCKCHAIN_PROVIDER", "none")
    if bc_status == "NOT_APPLICABLE" or provider == "none":
        bc_data = [
            ["Check", "Result"],
            ["Provider", f"{provider} (Disabled / Not configured)"],
            ["Status", "Not evaluated (Blockchain ledger provider not configured)"],
        ]
    else:
        bc_data = [
            ["Check", "Result"],
            ["Provider & Status", f"{provider.upper()} — {bc_status}"],
            ["Hash Consistency", verification_row.get("hash_match_status") or "NOT_REGISTERED"],
            ["Hash Submitted", (verification_row.get("blockchain_hash_submitted") or "—")[:40]],
            ["On-Chain Record Hash", (verification_row.get("blockchain_hash_onchain") or "—")[:40]],
            ["Transaction Reference", (verification_row.get("blockchain_tx_hash") or "—")[:40]],
        ]
    t_bc = Table(bc_data, colWidths=[55 * mm, 125 * mm])
    t_bc.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t_bc)
    items.append(Spacer(1, 2 * mm))

    # --- Tampering & ELA ---
    items.append(Paragraph("<b>C. Tampering & Image Forgery Detection</b>", styles["Label"]))
    t_score = verification_row.get("tampering_score")
    if t_score is None:
        t_data = [
            ["Check", "Result"],
            ["Tampering Detection", "Not evaluated (Tampering analysis was not run)"],
        ]
    else:
        t_risk = verification_row.get("tampering_risk_level") or (
            "LOW_RISK" if t_score < 30 else "MEDIUM_RISK" if t_score < 60 else "HIGH_RISK"
        )
        t_conf = verification_row.get("tampering_confidence")
        t_detail = verification_row.get("tampering_detail") or {}
        t_flags = verification_row.get("tampering_flags") or []

        t_data = [
            ["Forensic Check", "Findings"],
            ["Overall Tampering Score", f"{round(t_score, 1)} / 100"],
            ["Risk Level & Confidence", f"{t_risk.replace('_', ' ').title()} ({round(t_conf or 0):.0f}% confidence)"],
        ]
        # Image quality
        iq = t_detail.get("image_quality", {})
        if iq:
            t_data.append(["Image Quality & Resolution", f"Score: {iq.get('score', 0):.0f}/100 ({iq.get('status', 'OK')})"])
        # ELA status
        ela = t_detail.get("ela", {})
        if ela:
            t_data.append(["Error Level Analysis (ELA)", f"Status: {ela.get('status', '—')} (Score: {ela.get('score', 0):.1f})"])
        else:
            t_data.append(["Error Level Analysis (ELA)", "Not evaluated (Heatmap file unavailable or digital text document)"])
        # Copy-paste / clone
        cp = t_detail.get("copy_paste", {})
        if cp:
            t_data.append(["Copy-Move / Clone Detection", "Clone regions detected" if cp.get("detected") else "None detected"])
        # Font consistency
        fc = t_detail.get("font_consistency", {})
        if fc:
            t_data.append(["Font Typography Consistency", f"Score: {fc.get('score', 0):.0f}/100 ({fc.get('status', 'OK')})"])
        # Signature & Seal
        sig = t_detail.get("signature", {})
        if sig:
            t_data.append(["Signature Analysis", f"{'Detected' if sig.get('detected') else 'Not found'} (Anomaly score: {sig.get('anomaly_score', 0):.0f})"])
        seal = t_detail.get("seal", {})
        if seal:
            t_data.append(["Seal / Stamp Analysis", f"{'Detected' if seal.get('detected') else 'Not found'} (Anomaly score: {seal.get('anomaly_score', 0):.0f})"])
        # Metadata
        meta = t_detail.get("metadata", {})
        if meta:
            t_data.append(["Document Metadata Integrity", f"{meta.get('status', 'OK')}"])
        t_data.append(["Forensic Flags", "; ".join(t_flags[:4]) if t_flags else "No anomaly flags"])

    t_tamp = Table(t_data, colWidths=[55 * mm, 125 * mm])
    t_tamp.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t_tamp)
    items.append(Spacer(1, 2 * mm))

    # ELA Heatmap Image Embedding (if available on disk)
    ela_path = verification_row.get("ela_heatmap_path")
    if ela_path and os.path.exists(ela_path):
        try:
            with PILImage.open(ela_path) as pimg:
                pw, ph = pimg.size
                aspect = ph / pw if pw > 0 else 0.75
                target_w = 110 * mm
                target_h = target_w * aspect
                if target_h > 70 * mm:
                    target_h = 70 * mm
                    target_w = target_h / aspect
            items.append(Paragraph("<b>Error Level Analysis (ELA) Heatmap:</b>", styles["Label"]))
            items.append(RLImage(ela_path, width=target_w, height=target_h))
            items.append(Paragraph("<i>Visual forensic heatmap: highlighted regions indicate compression variance and potential localized modifications.</i>", styles["SmallGray"]))
            items.append(Spacer(1, 2 * mm))
        except Exception as exc:
            logger.warning("Could not embed ELA heatmap: %s", exc)
            items.append(Paragraph(f"ELA Heatmap: Not evaluated (Error loading image: {exc})", styles["SmallGray"]))
    else:
        items.append(Paragraph("<i>ELA Heatmap: Not evaluated (Heatmap image unavailable or vector PDF document).</i>", styles["SmallGray"]))
        items.append(Spacer(1, 2 * mm))

    # --- Duplicate Detection ---
    items.append(Paragraph("<b>D. Duplicate & Collision Detection</b>", styles["Label"]))
    is_dup = verification_row.get("is_duplicate")
    if is_dup is None:
        dup_data = [
            ["Check", "Result"],
            ["Duplicate Detection", "Not evaluated (Duplicate detection was not run)"],
        ]
    else:
        dup_data = [
            ["Check", "Result"],
            ["Collision Detected", "Yes (Duplicate)" if is_dup else "No (Unique Record)"],
            ["Match Analysis", verification_row.get("duplicate_match_reason") or ("Unique document (No duplicates detected in registry)" if not is_dup else "Collision detected")],
            ["Duplicate Of Certificate ID", verification_row.get("duplicate_of_certificate_id") or "None"],
        ]
    t_dup = Table(dup_data, colWidths=[55 * mm, 125 * mm])
    t_dup.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t_dup)
    return items


def _build_fraud(fraud_row: Optional[dict], styles: dict) -> list:
    items = _section_header("5. AI Fraud Analysis & Risk Modeling", styles)
    if not fraud_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (AI fraud analysis was not run).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    prob = fraud_row.get("fraud_probability", 0)
    prob_pct = round(prob * 100, 1)
    risk_label = "LOW RISK" if prob < 0.3 else "MEDIUM RISK" if prob < 0.6 else "HIGH RISK"

    items.append(Paragraph(
        f"Fraud Probability Score: <b>{prob_pct}%</b>  —  <b>{risk_label}</b>",
        styles["Body"]
    ))

    factors = [
        ("OCR Text Extraction Accuracy", fraud_row.get("ocr_accuracy_weight", 0)),
        ("Cross-Document Comparison Consistency", fraud_row.get("comparison_weight", 0)),
        ("QR Code Payload & Domain Trust", fraud_row.get("qr_weight", 0)),
        ("Blockchain Ledger Integrity", fraud_row.get("blockchain_weight", 0)),
        ("Tampering & Forgery Signals", fraud_row.get("tampering_weight", 0)),
        ("Duplicate & Identity Collision", fraud_row.get("duplicate_weight", 0)),
        ("File Metadata & Structural Integrity", fraud_row.get("metadata_integrity_weight", 0)),
        ("Image Acquisition Quality", fraud_row.get("image_quality_weight", 0)),
    ]
    data = [["Risk Factor Component", "Calibrated Weight"]] + [
        [label, f"{round((w or 0) * 100, 1)}%"] for label, w in factors
    ]
    t = Table(data, colWidths=[110 * mm, 70 * mm])
    t.setStyle(_table_style())
    items.append(t)
    return items


def _build_trust_score(trust_row: Optional[dict], styles: dict) -> list:
    items = _section_header("6. Trust Score & Evidence Coverage", styles)
    if not trust_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (Trust score calculation was not run).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    score = trust_row.get("score", 0)
    band_high = getattr(settings, "TRUST_SCORE_BAND_HIGH", 80.0)
    band_med = getattr(settings, "TRUST_SCORE_BAND_MEDIUM", 50.0)
    band = "HIGH TRUST" if score >= band_high else "MEDIUM TRUST" if score >= band_med else "LOW TRUST"

    breakdown = trust_row.get("breakdown") or {}
    cov_raw = breakdown.get("coverage", 1.0)
    if isinstance(cov_raw, dict):
        cov_pct = cov_raw.get("percentage")
        if cov_pct is None:
            cov_ratio = cov_raw.get("ratio", 1.0)
            cov_pct = round(cov_ratio * 100, 1)
        cov_summary = cov_raw.get("summary", f"{cov_pct}% evaluated")
    elif isinstance(cov_raw, (int, float)):
        cov_pct = round(cov_raw * 100, 1) if cov_raw <= 1.0 else round(cov_raw, 1)
        cov_summary = f"{cov_pct}% evaluated"
    else:
        cov_pct = 100.0
        cov_summary = "100% evaluated"

    items.append(Paragraph(
        f"Institutional Trust Score: <b>{round(score, 1)} / 100</b>  —  <b>{band}</b>  |  Evidence Coverage: <b>{cov_summary}</b>",
        styles["Body"]
    ))

    # 8-Component Breakdown (supports list of dicts or dict of dicts)
    components = breakdown.get("components") or []
    if components:
        t_data = [["Component", "Value", "Weight", "Contribution", "Status", "Reason"]]
        if isinstance(components, list):
            for c in components:
                name = c.get("label") or c.get("component") or "Component"
                val = c.get("value")
                val_str = f"{round(val, 1)}" if val is not None else "—"
                wt = c.get("weight", 0)
                wt_str = f"{round(wt * 100, 1)}%"
                contrib = c.get("contribution", 0)
                contrib_str = f"{round(contrib, 1)}"
                status = c.get("status", "EVALUATED")
                reason = c.get("reason", "Evaluated")
                status_disp = "Evaluated" if str(status).upper() in ("EVALUATED", "VALID", "CLEAN") else "Not evaluated"
                t_data.append([str(name)[:25], val_str, wt_str, contrib_str, status_disp, str(reason)[:50]])
        elif isinstance(components, dict):
            for comp_name, comp_info in components.items():
                disp_name = comp_name.replace("_", " ").title()
                val = comp_info.get("value")
                val_str = f"{round(val, 1)}" if val is not None else "—"
                wt = comp_info.get("weight", 0)
                wt_str = f"{round(wt * 100, 1)}%"
                contrib = comp_info.get("contribution", 0)
                contrib_str = f"{round(contrib, 1)}"
                status = comp_info.get("status", "EVALUATED")
                reason = comp_info.get("reason", "Evaluated")
                status_disp = "Evaluated" if str(status).upper() in ("EVALUATED", "VALID", "CLEAN") else "Not evaluated"
                t_data.append([disp_name[:25], val_str, wt_str, contrib_str, status_disp, str(reason)[:50]])

        t_breakdown = Table(t_data, colWidths=[36 * mm, 14 * mm, 16 * mm, 18 * mm, 24 * mm, 72 * mm])
        t_breakdown.setStyle(_table_style())
        items.append(t_breakdown)
    else:
        # Fallback to factor_trust_values
        factor_values = breakdown.get("factor_trust_values") or {}
        if factor_values:
            t_data = [["Factor", "Trust Value (0–100)"]] + [
                [k.replace("_", " ").title(), f"{round(v, 1)}"] for k, v in factor_values.items()
            ]
            t = Table(t_data, colWidths=[110 * mm, 70 * mm])
            t.setStyle(_table_style())
            items.append(t)

    return items


def _build_prediction(prediction_row: Optional[dict], styles: dict) -> list:
    items = _section_header("7. Final Verdict & Recommended Action", styles)
    if not prediction_row:
        items.append(Paragraph("Status: <b>Not evaluated</b> (Final prediction was not run).", styles["Body"]))
        items.append(Spacer(1, 2 * mm))
        return items

    label = (prediction_row.get("label") or "INCONCLUSIVE").upper()
    style_name = (
        "VerdictGenuine" if "GENUINE" in label
        else "VerdictSuspicious" if "SUSPICIOUS" in label
        else "VerdictFake" if ("FAKE" in label or "FORGED" in label)
        else "VerdictInconclusive"
    )
    emoji = "✅ " if "GENUINE" in label else "⚠️ " if "SUSPICIOUS" in label else "❌ " if ("FAKE" in label or "FORGED" in label) else "❓ "

    items.append(Paragraph(f"{emoji}{label}", styles[style_name]))
    items.append(Paragraph(
        f"Classification Confidence: <b>{round((prediction_row.get('confidence_score') or 0) * 100, 1)}%</b>",
        styles["Center"]
    ))
    items.append(Spacer(1, 2 * mm))

    pred_data = [
        ["Attribute", "Decision Support Assessment"],
        ["Verdict Explanation", prediction_row.get("explanation") or "No explanation generated."],
        ["Recommended Action", prediction_row.get("recommended_action") or "Escalate for manual inspection."],
        ["Regulatory Disclaimer", "CertiVerify AI is an assistive decision-support engine. Institutional officers should exercise independent regulatory judgment."],
    ]
    t = Table(pred_data, colWidths=[45 * mm, 135 * mm])
    t.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t)
    return items


def _build_signature_block(report_row: dict, styles: dict) -> list:
    items = _section_header("8. Cryptographic Digital Signature & Integrity Block", styles)
    vid = report_row.get("verification_id", "CV-UNKNOWN")
    sig = report_row.get("digital_signature") or "PENDING_COMPUTATION"

    items.append(Paragraph(
        "This dossier has been cryptographically sealed by CertiVerify Enterprise. "
        "The digital signature below is a detached HMAC-SHA256 computed over the final PDF document bytes. "
        "Any alteration to this document invalidates the signature and fails cryptographic verification.",
        styles["SmallGray"]
    ))
    items.append(Spacer(1, 2 * mm))

    data = [
        ["Verification ID", vid],
        ["Signature Mode", "HMAC-SHA256 Detached Document Signature"],
        ["Digital Signature", sig],
        ["Generated At", report_row.get("generated_at", "—")],
        ["System Engine", "CertiVerify Enterprise Integrity Engine v1.0"],
    ]
    font_regular, font_bold = _init_fonts()
    t = Table(data, colWidths=[45 * mm, 135 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), font_bold),
        ("FONTNAME", (1, 0), (1, -1), font_regular),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_DARK_TEXT),
        ("GRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


# ---------------------------------------------------------------------------
# Digital Signature Helpers
# ---------------------------------------------------------------------------

def make_verification_id() -> str:
    """
    Generates a unique, human-readable, non-guessable verification ID.
    Format: CV-{YYYY}-{8 hex cryptographically secure token}
    """
    year = datetime.utcnow().year
    token = secrets.token_hex(4).upper()
    return f"CV-{year}-{token}"


def get_report_signing_key() -> str:
    """
    Retrieves the report signing key from settings / env.
    Refuses in production if missing; warns and falls back to SECRET_KEY in development.
    """
    key = getattr(settings, "REPORT_SIGNING_KEY", None)
    if not key:
        env_mode = (getattr(settings, "ENV", "development") or "development").lower()
        if env_mode in ("production", "prod"):
            raise RuntimeError(
                "REPORT_SIGNING_KEY is not configured in production environment. "
                "Refusing to generate signed verification reports."
            )
        logger.warning(
            "REPORT_SIGNING_KEY is not configured in %s; falling back to SECRET_KEY for report digital signature.",
            env_mode,
        )
        key = settings.SECRET_KEY
    return key


def compute_report_signature(pdf_bytes: bytes, key: Optional[str] = None) -> str:
    """
    Computes a detached HMAC-SHA256 signature over the generated PDF bytes.
    """
    signing_key = key or get_report_signing_key()
    return hmac.new(signing_key.encode("utf-8"), pdf_bytes, hashlib.sha256).hexdigest()


def verify_report_signature(
    pdf_content_or_path: bytes | str,
    expected_signature: str,
    key: Optional[str] = None,
) -> bool:
    """
    Verifies that the given PDF matches the expected HMAC-SHA256 signature.
    Returns True if valid, False if altered or key mismatch.
    """
    try:
        if isinstance(pdf_content_or_path, str):
            if not os.path.exists(pdf_content_or_path):
                logger.error("Verification failed: PDF path does not exist: %s", pdf_content_or_path)
                return False
            with open(pdf_content_or_path, "rb") as f:
                pdf_bytes = f.read()
        else:
            pdf_bytes = pdf_content_or_path

        actual_signature = compute_report_signature(pdf_bytes, key=key)
        return hmac.compare_digest(actual_signature, expected_signature)
    except Exception as e:
        logger.exception("Error verifying report signature: %s", e)
        return False


def compute_digital_signature(cert: dict | bytes, report_metadata: Optional[dict] = None) -> str:
    """
    Compatibility wrapper:
    If called with (pdf_bytes), computes detached signature over bytes.
    If called with (cert_dict, report_meta), computes detached signature over manifest string.
    """
    if isinstance(cert, bytes):
        return compute_report_signature(cert)
    payload = (
        f"{cert.get('id', '')}:{cert.get('sha256_hash', '')}:"
        f"{report_metadata.get('verification_id', '') if report_metadata else ''}:"
        f"{report_metadata.get('generated_at', '') if report_metadata else ''}"
    )
    signing_key = get_report_signing_key()
    return hmac.new(signing_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report_pdf(
    cert: dict,
    doc_type_row: Optional[dict],
    ocr_row: Optional[dict],
    comparison_row: Optional[dict],
    verification_row: Optional[dict],
    fraud_row: Optional[dict],
    trust_row: Optional[dict],
    prediction_row: Optional[dict],
    report_row: dict,
) -> bytes:
    """
    Builds the complete multi-page PDF Verification Report and returns raw bytes.
    """
    buf = io.BytesIO()
    styles = _styles()

    story = []
    story += _build_cover(cert, report_row, styles)
    story += _build_document_type(doc_type_row, styles)
    story += _build_ocr(ocr_row, styles)
    story += _build_comparison(comparison_row, styles)
    story += _build_verification(verification_row, styles)
    story += _build_fraud(fraud_row, styles)
    story += _build_trust_score(trust_row, styles)
    story += _build_prediction(prediction_row, styles)
    story += _build_signature_block(report_row, styles)

    page_size = _get_page_size()
    doc = BaseDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="main",
    )
    template = PageTemplate(id="main", frames=[frame])
    doc.addPageTemplates([template])

    doc.build(story, canvasmaker=_WatermarkCanvas)
    buf.seek(0)
    return buf.read()
