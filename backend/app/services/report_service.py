"""
MODULE 10 - REPORT SERVICE
Generates a professional PDF Verification Report using ReportLab.

Report contents:
  - Header / watermark / verification ID
  - Certificate metadata & preview (embedded image)
  - OCR extracted text table
  - Document type
  - Document comparison results
  - QR verification result
  - Blockchain verification result
  - Tampering detection result
  - Duplicate detection result
  - AI fraud analysis (factor bar chart)
  - Trust score gauge (drawn via ReportLab)
  - Final prediction verdict
  - Verification timeline
  - Digital signature (HMAC-SHA256)
  - Footer with system watermark
"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import textwrap
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfgen_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

from app.core.config import settings

# ---------------------------------------------------------------------------
# Colour palette (dark-mode inspired converted to RGB 0-1)
# ---------------------------------------------------------------------------
COLOR_BG_DARK = colors.HexColor("#0b1220")
COLOR_PANEL = colors.HexColor("#111827")
COLOR_BORDER = colors.HexColor("#1f2937")
COLOR_BRAND = colors.HexColor("#2563eb")
COLOR_GENUINE = colors.HexColor("#16a34a")
COLOR_SUSPICIOUS = colors.HexColor("#d97706")
COLOR_FAKE = colors.HexColor("#dc2626")
COLOR_WHITE = colors.white
COLOR_GRAY = colors.HexColor("#9ca3af")
COLOR_LIGHT_GRAY = colors.HexColor("#e5e7eb")
COLOR_DARK_TEXT = colors.HexColor("#374151")


def _verdict_color(label: str):
    return {
        "genuine": COLOR_GENUINE,
        "suspicious": COLOR_SUSPICIOUS,
        "fake": COLOR_FAKE,
    }.get(label.lower(), COLOR_GRAY)


# ---------------------------------------------------------------------------
# Page template: adds watermark + header/footer on every page
# ---------------------------------------------------------------------------

class _WatermarkCanvas(pdfgen_canvas.Canvas):
    """Canvas subclass that renders an invisible watermark on every page."""

    def __init__(self, filename_or_buffer, **kwargs):
        super().__init__(filename_or_buffer, **kwargs)
        self._doc_title = "CertiVerify AI — Verification Report"

    def showPage(self):
        self._draw_watermark()
        self._draw_footer()
        super().showPage()

    def _draw_watermark(self):
        self.saveState()
        self.setFont("Helvetica-Bold", 52)
        self.setFillColor(colors.HexColor("#1f2937"))
        self.setFillAlpha(0.06)
        self.translate(105 * mm, 148.5 * mm)
        self.rotate(45)
        self.drawCentredString(0, 0, "CERTIVERIFY AI")
        self.restoreState()

    def _draw_footer(self):
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColor(COLOR_GRAY)
        w, h = A4
        self.drawString(15 * mm, 8 * mm, "CertiVerify AI — Confidential Verification Report")
        self.drawRightString(w - 15 * mm, 8 * mm, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        self.restoreState()


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _styles():
    base = getSampleStyleSheet()
    S = {}

    def add(name, **kwargs):
        S[name] = ParagraphStyle(name, **kwargs)

    add("Title", fontName="Helvetica-Bold", fontSize=20, textColor=COLOR_BRAND,
        alignment=TA_CENTER, spaceAfter=4)
    add("Subtitle", fontName="Helvetica", fontSize=9, textColor=COLOR_GRAY,
        alignment=TA_CENTER, spaceAfter=2)
    add("SectionHead", fontName="Helvetica-Bold", fontSize=11, textColor=COLOR_BRAND,
        spaceBefore=12, spaceAfter=4, borderPadding=(0, 0, 2, 0))
    add("Body", fontName="Helvetica", fontSize=8, textColor=COLOR_DARK_TEXT,
        leading=12, spaceAfter=3)
    add("SmallGray", fontName="Helvetica", fontSize=7, textColor=COLOR_GRAY,
        leading=10)
    add("VerdictGenuine", fontName="Helvetica-Bold", fontSize=14,
        textColor=COLOR_GENUINE, alignment=TA_CENTER, spaceAfter=4)
    add("VerdictSuspicious", fontName="Helvetica-Bold", fontSize=14,
        textColor=COLOR_SUSPICIOUS, alignment=TA_CENTER, spaceAfter=4)
    add("VerdictFake", fontName="Helvetica-Bold", fontSize=14,
        textColor=COLOR_FAKE, alignment=TA_CENTER, spaceAfter=4)
    add("Label", fontName="Helvetica-Bold", fontSize=8, textColor=COLOR_DARK_TEXT)
    add("Value", fontName="Helvetica", fontSize=8, textColor=COLOR_DARK_TEXT)
    add("Center", fontName="Helvetica", fontSize=8, textColor=COLOR_DARK_TEXT,
        alignment=TA_CENTER)
    return S


# ---------------------------------------------------------------------------
# Table style helper
# ---------------------------------------------------------------------------

def _table_style(header_bg=None):
    header_bg = header_bg or COLOR_BRAND
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), COLOR_DARK_TEXT),
        ("GRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ])


# ---------------------------------------------------------------------------
# Section builders — each returns a list of Flowables
# ---------------------------------------------------------------------------

def _section_header(title: str, styles: dict) -> list:
    return [
        HRFlowable(width="100%", thickness=0.5, color=COLOR_BRAND, spaceAfter=4),
        Paragraph(title.upper(), styles["SectionHead"]),
    ]


def _build_cover(cert, report_row, styles: dict) -> list:
    items = []
    items.append(Spacer(1, 8 * mm))
    items.append(Paragraph("CertiVerify AI", styles["Title"]))
    items.append(Paragraph("AI-Powered Certificate Verification Report", styles["Subtitle"]))
    items.append(Paragraph(
        f"Verification ID: <b>{report_row['verification_id']}</b>",
        ParagraphStyle("VID", fontName="Helvetica-Bold", fontSize=10,
                       textColor=COLOR_BRAND, alignment=TA_CENTER, spaceAfter=2)
    ))
    items.append(Spacer(1, 6 * mm))

    data = [
        ["Field", "Value"],
        ["Certificate File", cert["original_filename"]],
        ["File Type", cert["file_type"].upper()],
        ["File Size", f"{round(cert['file_size_bytes'] / 1024, 1)} KB"],
        ["SHA-256 Hash", cert["sha256_hash"][:32] + "..."],
        ["Uploaded At", cert["uploaded_at"]],
        ["Generated At", report_row["generated_at"]],
        ["Digital Signature", (report_row.get("digital_signature") or "N/A")[:40] + "..."],
    ]
    t = Table(data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style())
    items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


def _build_document_type(doc_type_row, styles: dict) -> list:
    if not doc_type_row:
        return _section_header("Document Type", styles) + [
            Paragraph("Document type identification not run.", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("Document Type Identification", styles)
    data = [
        ["Field", "Value"],
        ["Predicted Type", doc_type_row["predicted_type"].replace("_", " ").title()],
        ["Confidence Score", f"{round(doc_type_row['confidence_score'] * 100, 1)}%"],
        ["Model Used", doc_type_row["model_used"]],
    ]
    t = Table(data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style())
    items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


def _build_ocr(ocr_row, styles: dict) -> list:
    if not ocr_row:
        return _section_header("OCR Text Extraction", styles) + [
            Paragraph("OCR extraction not run.", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("OCR Text Extraction", styles)

    fields = [
        ("Student Name", ocr_row.get("student_name")),
        ("University Name", ocr_row.get("university_name")),
        ("Register Number", ocr_row.get("register_number")),
        ("Roll Number", ocr_row.get("roll_number")),
        ("Certificate Number", ocr_row.get("certificate_number")),
        ("Department", ocr_row.get("department")),
        ("Course", ocr_row.get("course")),
        ("CGPA", ocr_row.get("cgpa")),
        ("Percentage", ocr_row.get("percentage")),
        ("Date of Issue", ocr_row.get("date_of_issue")),
        ("QR Code Data", ocr_row.get("qr_code_data") or "Not detected"),
        ("Signature Present", "Yes" if ocr_row.get("has_signature") else "No"),
        ("Seal Present", "Yes" if ocr_row.get("has_seal") else "No"),
        ("OCR Accuracy", f"{round((ocr_row.get('ocr_accuracy') or 0) * 100, 1)}%"),
        ("OCR Engine", ocr_row.get("ocr_engine") or "—"),
    ]
    data = [["Field", "Extracted Value"]] + [
        [label, str(val) if val is not None else "—"] for label, val in fields
    ]
    t = Table(data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style())
    items.append(t)

    # Raw text excerpt
    raw = ocr_row.get("raw_text") or ""
    if raw:
        items.append(Spacer(1, 3 * mm))
        items.append(Paragraph("Raw OCR Text (excerpt):", styles["Label"]))
        excerpt = textwrap.shorten(raw.replace("\n", " "), width=500, placeholder="…")
        items.append(Paragraph(excerpt, styles["SmallGray"]))
    items.append(Spacer(1, 4 * mm))
    return items


def _build_comparison(comparison_row, styles: dict) -> list:
    if not comparison_row:
        return _section_header("Document Comparison", styles) + [
            Paragraph("Document comparison not run (requires a document group).", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("Document Comparison Results", styles)
    data = [
        ["Field", "Value"],
        ["Consistency", f"{round(comparison_row.get('consistency_percentage', 0), 1)}%"],
        ["Matching Fields", ", ".join(comparison_row.get("matching_fields") or []) or "None"],
        ["Mismatched Fields", ", ".join(comparison_row.get("mismatched_fields") or []) or "None"],
        ["Missing Fields", ", ".join(comparison_row.get("missing_fields") or []) or "None"],
    ]
    t = Table(data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style())
    items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


def _build_verification(verification_row, styles: dict) -> list:
    if not verification_row:
        return _section_header("AI Verification", styles) + [
            Paragraph("Verification checks not run.", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("AI Verification Results", styles)

    # QR
    items.append(Paragraph("QR Code Verification", styles["Label"]))
    qr_data = [
        ["Check", "Result"],
        ["QR Code Present", "Yes" if verification_row.get("qr_present") else "No"],
        ["QR Valid", str(verification_row.get("qr_valid")) if verification_row.get("qr_present") else "N/A"],
        ["Warning", verification_row.get("qr_warning") or "—"],
    ]
    t = Table(qr_data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t)
    items.append(Spacer(1, 3 * mm))

    # Blockchain
    items.append(Paragraph("Blockchain & Hash Verification", styles["Label"]))
    bc_status = verification_row.get("blockchain_status") or "not_run"
    hash_match = verification_row.get("hash_match_status") or "NOT_REGISTERED"
    bc_data = [
        ["Check", "Result"],
        ["Blockchain Status", bc_status.replace("_", " ").title()],
        ["SHA-256 Hash Consistency", hash_match],
        ["Hash Submitted (first 40)", (verification_row.get("blockchain_hash_submitted") or "—")[:40]],
        ["On-chain Hash (first 40)", (verification_row.get("blockchain_hash_onchain") or "—")[:40]],
        ["Blockchain Hash Match", str(verification_row.get("blockchain_match")) if verification_row.get("blockchain_status") else "N/A"],
        ["Tx Hash", (verification_row.get("blockchain_tx_hash") or "—")[:40]],
    ]
    t = Table(bc_data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t)
    items.append(Spacer(1, 3 * mm))

    # Tampering (enhanced — PART T)
    items.append(Paragraph("Tampering & Forgery Detection", styles["Label"]))
    t_score = verification_row.get("tampering_score")
    t_flags = verification_row.get("tampering_flags") or []
    t_risk = verification_row.get("tampering_risk_level") or (
        ("Low" if t_score < 30 else "Medium" if t_score < 60 else "High") if t_score is not None else "—"
    )
    t_conf = verification_row.get("tampering_confidence")
    t_detail = verification_row.get("tampering_detail") or {}

    tamp_data = [
        ["Check", "Result"],
        ["Tampering Score", f"{round(t_score, 1)}/100" if t_score is not None else "Not run"],
        ["Risk Level", t_risk.replace("_", " ").title() if t_risk else "—"],
        ["Confidence", f"{round(t_conf, 0):.0f}%" if t_conf is not None else "—"],
    ]

    # Image quality row
    iq = t_detail.get("image_quality", {})
    if iq:
        tamp_data.append(["Image Quality", f"{iq.get('score', '—'):.0f}/100 ({iq.get('status', '—')})"])

    # ELA row
    ela = t_detail.get("ela", {})
    if ela:
        tamp_data.append(["ELA Status", f"{ela.get('status', '—')} (score {ela.get('score', '—')})"])

    # Copy-paste row
    cp = t_detail.get("copy_paste", {})
    if cp:
        tamp_data.append(["Copy-Paste", "Detected" if cp.get("detected") else "None detected"])

    # Font consistency row
    fc = t_detail.get("font_consistency", {})
    if fc:
        tamp_data.append(["Font Consistency", f"{fc.get('score', '—')}/100 ({fc.get('status', '—')})"])

    # Signature row
    sig = t_detail.get("signature", {})
    if sig:
        tamp_data.append([
            "Signature",
            f"{'Detected' if sig.get('detected') else 'Not found'} "
            f"(anomaly: {sig.get('anomaly_score', 0):.0f})"
        ])

    # Seal row
    seal = t_detail.get("seal", {})
    if seal:
        tamp_data.append([
            "Seal",
            f"{'Detected' if seal.get('detected') else 'Not found'} "
            f"(anomaly: {seal.get('anomaly_score', 0):.0f})"
        ])

    # Metadata row
    meta = t_detail.get("metadata", {})
    if meta:
        tamp_data.append(["Metadata", f"{meta.get('status', '—')}"])

    # Flags
    tamp_data.append(["Anomaly Flags", ("; ".join(t_flags[:3]) + ("…" if len(t_flags) > 3 else "")) if t_flags else "None"])

    t_table = Table(tamp_data, colWidths=[55 * mm, 120 * mm])
    t_table.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t_table)
    items.append(Spacer(1, 3 * mm))

    # Duplicate
    items.append(Paragraph("Duplicate Detection", styles["Label"]))
    dup_data = [
        ["Check", "Result"],
        ["Is Duplicate", "Yes" if verification_row.get("is_duplicate") else "No"],
        ["Reason", verification_row.get("duplicate_match_reason") or "—"],
    ]
    t = Table(dup_data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t)
    # Cross-Validation (QR data vs OCR fields)
    items.append(Paragraph("QR ↔ OCR Cross-Validation", styles["Label"]))
    cv_status = verification_row.get("cross_validation_status") or "UNAVAILABLE"
    cv_mismatches = verification_row.get("cross_validation_mismatches") or []
    mismatch_text = "; ".join(
        f"{m.get('field')}: QR='{m.get('qr_value')}' vs OCR='{m.get('ocr_value')}'"
        for m in cv_mismatches
    ) if cv_mismatches else "None"
    cv_data = [
        ["Check", "Result"],
        ["Cross-Validation Status", cv_status],
        ["Fields Compared", str(len(cv_mismatches)) + " mismatch(es)" if cv_mismatches else "All consistent"],
        ["Mismatches", mismatch_text[:120]],
    ]
    t = Table(cv_data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(_table_style(header_bg=COLOR_PANEL))
    items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


def _build_fraud(fraud_row, styles: dict) -> list:
    if not fraud_row:
        return _section_header("AI Fraud Analysis", styles) + [
            Paragraph("Fraud analysis not run.", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("AI Fraud Analysis", styles)
    prob = fraud_row.get("fraud_probability", 0)
    prob_pct = round(prob * 100, 1)

    items.append(Paragraph(
        f"Fraud Probability: <b>{prob_pct}%</b>  ({'Low Risk' if prob < 0.3 else 'Medium Risk' if prob < 0.6 else 'High Risk'})",
        styles["Body"]
    ))

    factors = [
        ("OCR Accuracy", fraud_row.get("ocr_accuracy_weight", 0)),
        ("Document Comparison", fraud_row.get("comparison_weight", 0)),
        ("QR Verification", fraud_row.get("qr_weight", 0)),
        ("Blockchain Verification", fraud_row.get("blockchain_weight", 0)),
        ("Tampering Detection", fraud_row.get("tampering_weight", 0)),
        ("Duplicate Detection", fraud_row.get("duplicate_weight", 0)),
        ("Metadata Integrity", fraud_row.get("metadata_integrity_weight", 0)),
        ("Image Quality", fraud_row.get("image_quality_weight", 0)),
    ]
    data = [["Factor", "Weight"]] + [
        [label, f"{round((w or 0) * 100, 1)}%"] for label, w in factors
    ]
    t = Table(data, colWidths=[100 * mm, 75 * mm])
    t.setStyle(_table_style())
    items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


def _build_trust_score(trust_row, styles: dict) -> list:
    if not trust_row:
        return _section_header("Trust Score", styles) + [
            Paragraph("Trust score not computed.", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("Trust Score", styles)
    score = trust_row.get("score", 0)
    label = "Genuine" if score >= 80 else "Suspicious" if score >= 50 else "Fake"
    items.append(Paragraph(
        f"Trust Score: <b>{round(score, 1)} / 100</b>  — <b>{label}</b>",
        styles["Body"]
    ))

    breakdown = trust_row.get("breakdown") or {}
    factor_values = breakdown.get("factor_trust_values") or {}
    if factor_values:
        data = [["Factor", "Score (0–100)"]] + [
            [k.replace("_", " ").title(), f"{round(v, 1)}"] for k, v in factor_values.items()
        ]
        t = Table(data, colWidths=[100 * mm, 75 * mm])
        t.setStyle(_table_style())
        items.append(t)
    items.append(Spacer(1, 4 * mm))
    return items


def _build_prediction(prediction_row, styles: dict) -> list:
    if not prediction_row:
        return _section_header("Final Prediction", styles) + [
            Paragraph("Final prediction not run.", styles["SmallGray"]),
            Spacer(1, 4 * mm),
        ]
    items = _section_header("Final Prediction & Verdict", styles)
    label = (prediction_row.get("label") or "").lower()
    style_name = {
        "genuine": "VerdictGenuine",
        "suspicious": "VerdictSuspicious",
        "fake": "VerdictFake",
    }.get(label, "Body")
    emoji = {"genuine": "✅", "suspicious": "⚠️", "fake": "❌"}.get(label, "")
    items.append(Paragraph(f"{emoji} {label.upper()}", styles[style_name]))
    items.append(Paragraph(
        f"Confidence: <b>{round((prediction_row.get('confidence_score') or 0) * 100, 1)}%</b>",
        styles["Center"]
    ))
    items.append(Spacer(1, 3 * mm))
    items.append(Paragraph("Explanation:", styles["Label"]))
    items.append(Paragraph(prediction_row.get("explanation") or "—", styles["Body"]))
    items.append(Spacer(1, 2 * mm))
    items.append(Paragraph("Recommended Action:", styles["Label"]))
    items.append(Paragraph(prediction_row.get("recommended_action") or "—", styles["Body"]))
    items.append(Spacer(1, 4 * mm))
    return items


def _build_signature_block(report_row, styles: dict) -> list:
    items = _section_header("Digital Signature & Integrity", styles)
    sig = report_row.get("digital_signature") or "N/A"
    items.append(Paragraph(
        "This report has been cryptographically signed by CertiVerify AI. "
        "The signature below is an HMAC-SHA256 of the report payload and can be "
        "verified against the system's secret key.",
        styles["SmallGray"]
    ))
    items.append(Spacer(1, 2 * mm))
    data = [
        ["Verification ID", report_row["verification_id"]],
        ["Digital Signature", sig],
        ["Report Generated", report_row["generated_at"]],
        ["System", "CertiVerify AI v1.0 — AI-Powered Fake Certificate Detection"],
    ]
    t = Table(data, colWidths=[55 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_DARK_TEXT),
        ("GRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    items.append(t)
    items.append(Spacer(1, 6 * mm))
    return items


# ---------------------------------------------------------------------------
# Digital Signature
# ---------------------------------------------------------------------------

def _sign_report(payload: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


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
    Builds the complete PDF and returns raw bytes.
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

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
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


def compute_digital_signature(cert: dict, report_metadata: dict) -> str:
    payload = (
        f"{cert['id']}:{cert['sha256_hash']}:{report_metadata['verification_id']}:"
        f"{report_metadata['generated_at']}"
    )
    return _sign_report(payload)
