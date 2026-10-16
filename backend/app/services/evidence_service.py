"""
PHASE 3 - EVIDENCE PROVENANCE SERVICE

Normalizes verification engine outputs into immutable, traceable EvidenceItem records.
"""
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Certificate,
    DocumentType,
    OCRData,
    VerificationResult,
    FraudAnalysis,
    TrustScore,
    EvidenceItem,
    EvidenceType,
    VerificationJob,
)
from app.services.audit_service import log_audit_event

logger = logging.getLogger("certiverify.evidence_service")


async def record_evidence(
    db: AsyncSession,
    certificate_id: str,
    evidence_type: str | EvidenceType,
    source: str,
    stage: str,
    document_hash: str,
    algorithm_engine: str,
    confidence: float,
    result: str,
    explanation: str,
    organization_id: str | None = None,
    verification_job_id: str | None = None,
    algorithm_version: str = "1.0.0",
    details: dict | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem:
    """
    Persists an EvidenceItem entity in the database.
    If a verification_job_id is supplied, replaces any previous item for the SAME job & stage
    to prevent duplicate evidence records within a single job execution run.
    Different verification jobs preserve separate, immutable evidence sets.
    """
    if isinstance(evidence_type, EvidenceType):
        ev_type_enum = evidence_type
    else:
        ev_type_enum = EvidenceType(evidence_type)

    # Check if an evidence item already exists for this exact job & evidence_type
    item: EvidenceItem | None = None
    if verification_job_id:
        existing_res = await db.execute(
            select(EvidenceItem).where(
                EvidenceItem.verification_job_id == verification_job_id,
                EvidenceItem.evidence_type == ev_type_enum,
            )
        )
        item = existing_res.scalar_one_or_none()

    if item is None:
        item = EvidenceItem(
            organization_id=organization_id,
            certificate_id=certificate_id,
            verification_job_id=verification_job_id,
            evidence_type=ev_type_enum,
            source=source,
            stage=stage,
            timestamp=datetime.utcnow(),
            document_hash=document_hash,
            algorithm_engine=algorithm_engine,
            algorithm_version=algorithm_version,
            confidence=round(float(confidence), 4),
            result=result,
            explanation=explanation,
            details=details or {},
        )
        db.add(item)
    else:
        # Update existing record for the current run
        item.organization_id = organization_id
        item.source = source
        item.stage = stage
        item.timestamp = datetime.utcnow()
        item.document_hash = document_hash
        item.algorithm_engine = algorithm_engine
        item.algorithm_version = algorithm_version
        item.confidence = round(float(confidence), 4)
        item.result = result
        item.explanation = explanation
        item.details = details or {}

    await db.commit()
    await db.refresh(item)

    await log_audit_event(
        db,
        action="evidence:generated",
        entity_type="evidence_item",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_id=item.id,
        metadata_json={
            "certificate_id": certificate_id,
            "verification_job_id": verification_job_id,
            "evidence_type": ev_type_enum.value,
            "result": result,
        },
    )

    return item


# ---------------------------------------------------------------------------
# STAGE-SPECIFIC EMITTERS
# ---------------------------------------------------------------------------

async def emit_document_analysis_evidence(
    db: AsyncSession,
    cert: Certificate,
    doc_type_row: DocumentType | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> list[EvidenceItem]:
    """Emit STRUCTURE and METADATA evidence items."""
    items = []

    # 1. METADATA Evidence
    meta_explanation = (
        f"File '{cert.original_filename}' ({cert.file_size_bytes} bytes, {cert.file_type.upper()}) "
        f"verified with SHA-256 hash {cert.sha256_hash}."
    )
    meta_item = await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.METADATA,
        source="System File Hasher",
        stage="DOCUMENT_ANALYSIS",
        document_hash=cert.sha256_hash,
        algorithm_engine="SHA-256 Hasher & File Sniffer",
        confidence=1.0,
        result="PASS",
        explanation=meta_explanation,
        details={
            "original_filename": cert.original_filename,
            "file_type": cert.file_type,
            "file_size_bytes": cert.file_size_bytes,
            "sha256_hash": cert.sha256_hash,
        },
        actor_user_id=actor_user_id,
    )
    items.append(meta_item)

    # 2. STRUCTURE Evidence
    if doc_type_row:
        pred_type = doc_type_row.predicted_type.value if hasattr(doc_type_row.predicted_type, "value") else str(doc_type_row.predicted_type)
        conf = doc_type_row.confidence_score or 0.85
        struct_explanation = (
            f"Classified document type as '{pred_type}' with confidence {round(conf * 100, 1)}% "
            f"using model '{doc_type_row.model_used}'."
        )
        struct_item = await record_evidence(
            db=db,
            certificate_id=cert.id,
            organization_id=cert.organization_id,
            verification_job_id=verification_job_id,
            evidence_type=EvidenceType.STRUCTURE,
            source="AI Document Classifier",
            stage="DOCUMENT_ANALYSIS",
            document_hash=cert.sha256_hash,
            algorithm_engine=doc_type_row.model_used or "CLIP ViT-B/32",
            confidence=conf,
            result="PASS" if conf >= 0.6 else "WARN",
            explanation=struct_explanation,
            details={
                "predicted_type": pred_type,
                "confidence_score": conf,
                "model_used": doc_type_row.model_used,
            },
            actor_user_id=actor_user_id,
        )
        items.append(struct_item)

    return items


async def emit_ocr_evidence(
    db: AsyncSession,
    cert: Certificate,
    ocr_row: OCRData | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit OCR evidence item."""
    if not ocr_row:
        return None

    ocr_acc = ocr_row.ocr_accuracy or 0.0
    status = "PASS" if ocr_acc >= 0.7 else ("WARN" if ocr_acc >= 0.4 else "FAIL")
    fields_detected = []
    if ocr_row.student_name:
        fields_detected.append(f"Name: {ocr_row.student_name}")
    if ocr_row.university_name:
        fields_detected.append(f"University: {ocr_row.university_name}")
    if ocr_row.certificate_number:
        fields_detected.append(f"Cert No: {ocr_row.certificate_number}")

    summary = ", ".join(fields_detected) if fields_detected else "No primary fields detected"
    explanation = (
        f"OCR extraction engine ({ocr_row.ocr_engine}) completed with overall accuracy {round(ocr_acc * 100, 1)}%. "
        f"Extracted: {summary}."
    )

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.OCR,
        source=ocr_row.ocr_engine or "EasyOCR + Tesseract Engine",
        stage="OCR",
        document_hash=cert.sha256_hash,
        algorithm_engine=ocr_row.ocr_engine or "EasyOCR + Tesseract",
        confidence=ocr_acc,
        result=status,
        explanation=explanation,
        details={
            "student_name": ocr_row.student_name,
            "university_name": ocr_row.university_name,
            "register_number": ocr_row.register_number,
            "certificate_number": ocr_row.certificate_number,
            "department": ocr_row.department,
            "course": ocr_row.course,
            "cgpa": ocr_row.cgpa,
            "percentage": ocr_row.percentage,
            "date_of_issue": ocr_row.date_of_issue,
            "has_signature": ocr_row.has_signature,
            "has_seal": ocr_row.has_seal,
            "field_confidences": ocr_row.field_confidences or {},
            "ocr_accuracy": ocr_acc,
        },
        actor_user_id=actor_user_id,
    )


async def emit_qr_evidence(
    db: AsyncSession,
    cert: Certificate,
    verification_row: VerificationResult | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit QR verification evidence item."""
    if not verification_row:
        return None

    qr_present = bool(verification_row.qr_present)
    qr_valid = bool(verification_row.qr_valid) if verification_row.qr_valid is not None else None

    if not qr_present:
        result = "NOT_FOUND"
        conf = 0.0
        explanation = verification_row.qr_warning or "No embedded QR barcode detected in document image."
    elif qr_valid:
        result = "PASS"
        conf = 0.95
        explanation = "QR Code detected, payload decoded successfully, and cryptographic signature verified."
    else:
        result = "WARN"
        conf = 0.60
        explanation = verification_row.qr_warning or "QR Code present but payload validation yielded warnings or mismatches."

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.QR,
        source="QR Detector & Decoder",
        stage="QR_VERIFICATION",
        document_hash=cert.sha256_hash,
        algorithm_engine="OpenCV QR Code Detector / pyzbar",
        confidence=conf,
        result=result,
        explanation=explanation,
        details={
            "qr_present": qr_present,
            "qr_valid": qr_valid,
            "qr_decoded_data": verification_row.qr_decoded_data,
            "qr_warning": verification_row.qr_warning,
        },
        actor_user_id=actor_user_id,
    )


async def emit_blockchain_evidence(
    db: AsyncSession,
    cert: Certificate,
    verification_row: VerificationResult | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit BLOCKCHAIN evidence item."""
    if not verification_row:
        return None

    status = (verification_row.blockchain_status or "unavailable").lower()

    if status == "verified":
        result = "PASS"
        conf = 1.0
        explanation = f"Document SHA-256 hash verified on-chain. Tx Hash: {verification_row.blockchain_tx_hash or 'N/A'}."
    elif status == "not_found":
        result = "NOT_FOUND"
        conf = 0.50
        explanation = "Document hash was not found registered on the blockchain ledger."
    elif status == "mismatch":
        result = "FAIL"
        conf = 0.95
        explanation = "Document hash on-chain mismatches current document payload!"
    else:
        result = "UNAVAILABLE"
        conf = 0.0
        explanation = "Blockchain node registry service is currently unavailable or unconfigured."

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.BLOCKCHAIN,
        source="Distributed Ledger Proof",
        stage="BLOCKCHAIN_VERIFICATION",
        document_hash=cert.sha256_hash,
        algorithm_engine="Ethereum Smart Contract Registry (Web3.py)",
        confidence=conf,
        result=result,
        explanation=explanation,
        details={
            "blockchain_status": status,
            "tx_hash": verification_row.blockchain_tx_hash,
            "hash_submitted": verification_row.blockchain_hash_submitted,
            "hash_onchain": verification_row.blockchain_hash_onchain,
            "match": verification_row.blockchain_match,
        },
        actor_user_id=actor_user_id,
    )


async def emit_tampering_evidence(
    db: AsyncSession,
    cert: Certificate,
    verification_row: VerificationResult | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit TAMPER evidence item."""
    if not verification_row:
        return None

    tamp_score = verification_row.tampering_score if verification_row.tampering_score is not None else 0.0
    risk_level = verification_row.tampering_risk_level or "LOW"
    flags = verification_row.tampering_flags or []

    if tamp_score >= 60.0 or risk_level in ("HIGH_RISK", "VERY_HIGH_RISK"):
        result = "FAIL"
        conf = round(tamp_score / 100.0, 4)
        explanation = f"Severe image tampering detected (Anomaly Index: {round(tamp_score, 1)}/100). Risk: {risk_level}. Flags: {', '.join(flags) if flags else 'Pixel ELA'}"
    elif tamp_score >= 30.0 or risk_level in ("MODERATE_RISK", "MINOR_ANOMALIES"):
        result = "WARN"
        conf = round(tamp_score / 100.0, 4)
        explanation = f"Minor forensic anomalies detected (Anomaly Index: {round(tamp_score, 1)}/100). Flags: {', '.join(flags) if flags else 'Compression artifacts'}"
    else:
        result = "PASS"
        conf = round(1.0 - (tamp_score / 100.0), 4)
        explanation = f"No significant visual tampering or pixel manipulations detected (Anomaly Index: {round(tamp_score, 1)}/100)."

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.TAMPER,
        source="Forensic ELA & Computer Vision",
        stage="TAMPER_ANALYSIS",
        document_hash=cert.sha256_hash,
        algorithm_engine="Error Level Analysis (ELA) + Laplacian + Metadata Forensic Inspector",
        confidence=conf,
        result=result,
        explanation=explanation,
        details={
            "tampering_score": tamp_score,
            "tampering_risk_level": risk_level,
            "tampering_flags": flags,
            "ela_heatmap_path": verification_row.ela_heatmap_path,
            "tampering_detail": verification_row.tampering_detail or {},
        },
        actor_user_id=actor_user_id,
    )


async def emit_duplicate_evidence(
    db: AsyncSession,
    cert: Certificate,
    verification_row: VerificationResult | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit DUPLICATE evidence item."""
    if not verification_row:
        return None

    is_dup = bool(verification_row.is_duplicate)
    reason = verification_row.duplicate_match_reason or "System registry scan completed."

    if is_dup:
        result = "DUPLICATE"
        conf = 0.95
        explanation = f"Duplicate certificate match detected! Reason: {reason}."
    else:
        result = "CLEAN"
        conf = 0.95
        explanation = "No duplicate certificate matching SHA-256 hash or identity numbers found in registry."

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.DUPLICATE,
        source="Registry Duplicate Engine",
        stage="DUPLICATE_DETECTION",
        document_hash=cert.sha256_hash,
        algorithm_engine="SHA-256 / Certificate No / Register No Registry Matcher",
        confidence=conf,
        result=result,
        explanation=explanation,
        details={
            "is_duplicate": is_dup,
            "duplicate_of_certificate_id": verification_row.duplicate_of_certificate_id,
            "duplicate_match_reason": reason,
            "duplicate_detail": verification_row.duplicate_detail or {},
        },
        actor_user_id=actor_user_id,
    )


async def emit_fraud_evidence(
    db: AsyncSession,
    cert: Certificate,
    fraud_row: FraudAnalysis | None,
    fraud_result_dict: dict | None = None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit FRAUD analysis evidence item with explainable factor breakdown."""
    if not fraud_row:
        return None

    fp = fraud_row.fraud_probability if fraud_row.fraud_probability is not None else 0.0
    pct = round(fp * 100, 1)

    if fp >= 0.60:
        result = "HIGH_RISK"
    elif fp >= 0.30:
        result = "MEDIUM_RISK"
    else:
        result = "LOW_RISK"

    # Build factor contributions explanation from real weights
    weights = {
        "ocr_accuracy": fraud_row.ocr_accuracy_weight or 0.0,
        "comparison": fraud_row.comparison_weight or 0.0,
        "qr": fraud_row.qr_weight or 0.0,
        "blockchain": fraud_row.blockchain_weight or 0.0,
        "tampering": fraud_row.tampering_weight or 0.0,
        "duplicate": fraud_row.duplicate_weight or 0.0,
        "metadata": fraud_row.metadata_integrity_weight or 0.0,
        "image_quality": fraud_row.image_quality_weight or 0.0,
    }
    
    top_factors = sorted(
        [f"{k} (weight {round(v * 100, 1)}%)" for k, v in weights.items() if v > 0],
        key=lambda x: x,
        reverse=True,
    )

    factor_summary = ", ".join(top_factors[:4]) if top_factors else "standard risk model"
    explanation = f"Bayesian Fraud Analysis evaluated statistical risk at {pct}%. Contributing signal weights: {factor_summary}."

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.FRAUD,
        source="AI Fraud Synthesis Engine",
        stage="FRAUD_ANALYSIS",
        document_hash=cert.sha256_hash,
        algorithm_engine="Multi-Signal Weighted Fraud Risk Evaluator",
        confidence=round(1.0 - fp, 4),
        result=result,
        explanation=explanation,
        details={
            "fraud_probability": fp,
            "weights": weights,
            "extra_details": fraud_result_dict or {},
        },
        actor_user_id=actor_user_id,
    )


async def emit_trust_score_evidence(
    db: AsyncSession,
    cert: Certificate,
    trust_row: TrustScore | None,
    verification_job_id: str | None = None,
    actor_user_id: str | None = None,
) -> EvidenceItem | None:
    """Emit TRUST_SCORE evidence item with explainable factor contributions."""
    if not trust_row:
        return None

    score = trust_row.score if trust_row.score is not None else 0.0

    if score >= 80.0:
        result = "PASS"
    elif score >= 50.0:
        result = "WARN"
    else:
        result = "FAIL"

    breakdown = trust_row.breakdown or {}
    factor_values = breakdown.get("factor_trust_values", {})
    
    parts = []
    for f_name, f_val in factor_values.items():
        if f_val is not None:
            parts.append(f"{f_name.replace('_', ' ')}: {round(float(f_val), 1)}/100")

    factors_str = "; ".join(parts[:4]) if parts else "overall telemetry evaluation"
    explanation = f"Composite Trust Score computed at {round(score, 1)}/100. Telemetry breakdown: {factors_str}."

    return await record_evidence(
        db=db,
        certificate_id=cert.id,
        organization_id=cert.organization_id,
        verification_job_id=verification_job_id,
        evidence_type=EvidenceType.TRUST_SCORE,
        source="Trust Score Engine",
        stage="TRUST_SCORE",
        document_hash=cert.sha256_hash,
        algorithm_engine="Normalized Trust Telemetry Evaluator",
        confidence=round(score / 100.0, 4),
        result=result,
        explanation=explanation,
        details={
            "trust_score": score,
            "breakdown": breakdown,
        },
        actor_user_id=actor_user_id,
    )
