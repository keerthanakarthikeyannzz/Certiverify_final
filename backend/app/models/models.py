"""
SQLAlchemy ORM models.
Schema covers Modules 1-10 of the workflow:
 1. User / Auth
 2. Certificate Upload
 3. Document Type Identification
 4. OCR Extracted Data
 5. Document Comparison
 6. Verification (QR / Blockchain / Tampering / Duplicate)
 7. Fraud Analysis
 8. Trust Score
 9. Final Prediction
10. Verification Report
"""
import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Enum, Float, Integer,
    Text, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ENTERPRISE CORE - MULTI-TENANCY & AUDIT LOGGING
# ---------------------------------------------------------------------------

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(150), nullable=False)
    slug = Column(String(150), unique=True, index=True, nullable=False)
    status = Column(String(30), default="active", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", back_populates="organization")
    certificates = relationship("Certificate", back_populates="organization")
    audit_logs = relationship("AuditLog", back_populates="organization")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default="member", nullable=False)  # owner, admin, member, viewer
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="org_memberships")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    actor_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)       # e.g., login, certificate:upload, certificate:verify, etc.
    entity_type = Column(String(100), nullable=False)  # user, certificate, report, etc.
    entity_id = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    metadata_json = Column(JSON, nullable=True)

    organization = relationship("Organization", back_populates="audit_logs")
    actor_user = relationship("User", back_populates="audit_logs")


# ---------------------------------------------------------------------------
# MODULE 1 - USER / AUTH
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    UNIVERSITY = "university"
    EMPLOYER = "employer"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.STUDENT, nullable=False)

    is_active = Column(Boolean, default=True)
    is_email_verified = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
    org_memberships = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="owner")
    otp_codes = relationship("OTPCode", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor_user")


class OTPPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "email_verification"
    LOGIN = "login"
    PASSWORD_RESET = "password_reset"


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    code = Column(String(10), nullable=False)
    purpose = Column(Enum(OTPPurpose), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="otp_codes")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)


# ---------------------------------------------------------------------------
# MODULE 2 - CERTIFICATE UPLOAD
# ---------------------------------------------------------------------------

class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)   # local path / S3 key / Cloudinary URL
    file_type = Column(String(10), nullable=False)        # pdf/jpg/jpeg/png
    file_size_bytes = Column(Integer, nullable=False)
    sha256_hash = Column(String(64), index=True, nullable=False)

    group_id = Column(UUID(as_uuid=False), nullable=True)  # links related docs (degree+marksheet+resume) for Module 5

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    is_history_hidden = Column(Boolean, default=False, nullable=False, server_default="false")
    history_deleted_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", back_populates="certificates")
    owner = relationship("User", back_populates="certificates")
    document_type = relationship("DocumentType", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    ocr_data = relationship("OCRData", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    verification = relationship("VerificationResult", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    fraud_analysis = relationship("FraudAnalysis", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    trust_score = relationship("TrustScore", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    prediction = relationship("FinalPrediction", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    report = relationship("VerificationReport", back_populates="certificate", uselist=False, cascade="all, delete-orphan", passive_deletes=True)



# ---------------------------------------------------------------------------
# MODULE 3 - AI DOCUMENT TYPE IDENTIFICATION
# ---------------------------------------------------------------------------

class DocTypeEnum(str, enum.Enum):
    DEGREE_CERTIFICATE = "degree_certificate"
    MARKSHEET = "marksheet"
    DIPLOMA = "diploma"
    RESUME = "resume"
    TRANSFER_CERTIFICATE = "transfer_certificate"
    EXPERIENCE_CERTIFICATE = "experience_certificate"
    AADHAAR_CARD = "aadhaar_card"     # Added: precise Aadhaar detection via OCR keyword scoring
    IDENTITY_CARD = "identity_card"   # Kept for backward compatibility (image-based fallback)
    UNKNOWN = "unknown"


class DocumentType(Base):
    __tablename__ = "document_types"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)
    predicted_type = Column(Enum(DocTypeEnum), nullable=False)
    confidence_score = Column(Float, nullable=False)  # 0-1
    model_used = Column(String(50), default="vit-document-classifier")
    created_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="document_type")


# ---------------------------------------------------------------------------
# MODULE 4 - OCR TEXT EXTRACTION
# ---------------------------------------------------------------------------

class OCRData(Base):
    __tablename__ = "ocr_data"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)

    student_name = Column(String(150))
    university_name = Column(String(255))
    register_number = Column(String(100))
    roll_number = Column(String(100))
    certificate_number = Column(String(100))
    department = Column(String(150))
    course = Column(String(150))
    cgpa = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    date_of_issue = Column(String(50))
    qr_code_data = Column(Text, nullable=True)
    has_signature = Column(Boolean, default=False)
    has_seal = Column(Boolean, default=False)

    raw_text = Column(Text)               # full OCR dump
    field_confidences = Column(JSON)      # {"student_name": 0.94, ...}
    ocr_accuracy = Column(Float)          # overall 0-1
    ocr_engine = Column(String(50), default="easyocr+tesseract")

    created_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="ocr_data")


# ---------------------------------------------------------------------------
# MODULE 5 - DOCUMENT COMPARISON
# ---------------------------------------------------------------------------

class DocumentComparison(Base):
    __tablename__ = "document_comparisons"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    group_id = Column(UUID(as_uuid=False), index=True, nullable=False)  # matches Certificate.group_id

    matching_fields = Column(JSON)     # ["student_name", "register_number", ...]
    mismatched_fields = Column(JSON)   # ["cgpa", ...]
    missing_fields = Column(JSON)      # ["department", ...]
    consistency_percentage = Column(Float)  # 0-100
    details = Column(JSON)  # {field: {"values": [...], "status": "matching|mismatched|missing"}}

    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# MODULE 6 - AI VERIFICATION (QR / Blockchain / Tampering / Duplicate)
# ---------------------------------------------------------------------------

class VerificationResult(Base):
    __tablename__ = "verification_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)

    # QR Check
    qr_present = Column(Boolean, default=False)
    qr_decoded_data = Column(JSON, nullable=True)
    qr_valid = Column(Boolean, nullable=True)
    qr_warning = Column(String(255), nullable=True)

    # Blockchain Verification
    blockchain_hash_submitted = Column(String(64), nullable=True)
    blockchain_hash_onchain = Column(String(64), nullable=True)
    blockchain_match = Column(Boolean, nullable=True)
    blockchain_tx_hash = Column(String(100), nullable=True)
    blockchain_status = Column(String(50), nullable=True)  # verified/not_found/mismatch/pending

    # Tampering Detection
    tampering_score = Column(Float, nullable=True)           # 0-100 (higher = more tampering)
    tampering_flags = Column(JSON, nullable=True)            # ["font_manipulation", "ela_anomaly", ...]
    ela_heatmap_path = Column(String(500), nullable=True)
    tampering_risk_level = Column(String(30), nullable=True) # LOW | MINOR_ANOMALIES | MODERATE_RISK | HIGH_RISK | VERY_HIGH_RISK
    tampering_confidence = Column(Float, nullable=True)      # 0-100 overall detection confidence
    tampering_detail = Column(JSON, nullable=True)           # full structured result (image_quality, ela, copy_paste, etc.)

    # Duplicate Detection
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_certificate_id = Column(UUID(as_uuid=False), nullable=True)
    duplicate_match_reason = Column(String(255), nullable=True)
    duplicate_detail = Column(JSON, nullable=True)   # {type, status, confidence, matched_fields, conflicting_fields, ...}

    # Cross-Validation (QR data vs OCR fields vs DB record)
    cross_validation_status = Column(String(50), nullable=True)   # CONSISTENT | MISMATCH | PARTIAL | UNAVAILABLE
    cross_validation_mismatches = Column(JSON, nullable=True)      # [{field, qr_value, ocr_value}, ...]

    # Hash Consistency (freshly computed hash vs stored hash at verify time)
    hash_match_status = Column(String(20), nullable=True)          # MATCH | MISMATCH | NOT_REGISTERED
    created_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="verification")

    @property
    def qr_status(self) -> str:
        if self.qr_valid is True:
            return "verified"
        if not self.qr_present:
            return "no_qr_found"
        if self.qr_warning and "domain" in self.qr_warning.lower():
            return "domain_not_allowed"
        if self.qr_warning and "expired" in self.qr_warning.lower():
            return "token_expired"
        if self.qr_warning and ("match" in self.qr_warning.lower() or "mismatch" in self.qr_warning.lower()):
            return "ocr_mismatch"
        if self.qr_valid is False:
            return "invalid_payload"
        return "unverified"

    @property
    def status(self) -> str:
        return self.qr_status

    @property
    def duplicate_status(self) -> str | None:
        if self.duplicate_detail and isinstance(self.duplicate_detail, dict):
            return self.duplicate_detail.get("duplicate_status")
        return "DUPLICATE" if self.is_duplicate else "NO_DUPLICATE"

    @property
    def tampering_status(self) -> str:
        if self.tampering_detail and isinstance(self.tampering_detail, dict):
            st = self.tampering_detail.get("tampering_status") or self.tampering_detail.get("status")
            if st:
                return st
        if self.tampering_risk_level == "SKIPPED":
            return "not_applicable_for_pdf_text_layer"
        if self.tampering_score is not None:
            return "analyzed"
        return "unavailable"

    @property
    def reason(self) -> str | None:
        return self.qr_warning



# ---------------------------------------------------------------------------
# MODULE 7 - AI FRAUD ANALYSIS
# ---------------------------------------------------------------------------

class FraudAnalysis(Base):
    __tablename__ = "fraud_analysis"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)

    ocr_accuracy_weight = Column(Float)
    comparison_weight = Column(Float)
    qr_weight = Column(Float)
    blockchain_weight = Column(Float)
    tampering_weight = Column(Float)
    duplicate_weight = Column(Float)
    metadata_integrity_weight = Column(Float)
    image_quality_weight = Column(Float)

    fraud_probability = Column(Float)  # 0-1
    created_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="fraud_analysis")


# ---------------------------------------------------------------------------
# MODULE 8 - TRUST SCORE
# ---------------------------------------------------------------------------

class TrustScore(Base):
    __tablename__ = "trust_scores"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)
    score = Column(Float, nullable=False)  # 0-100
    breakdown = Column(JSON)  # per-factor contribution
    created_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="trust_score")


# ---------------------------------------------------------------------------
# MODULE 9 - FINAL PREDICTION
# ---------------------------------------------------------------------------

class PredictionLabel(str, enum.Enum):
    GENUINE = "genuine"
    SUSPICIOUS = "suspicious"
    FAKE = "fake"
    INCONCLUSIVE = "inconclusive"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v_lower = value.strip().lower()
            if "inconclusive" in v_lower:
                return cls.INCONCLUSIVE
        return super()._missing_(value)


class FinalPrediction(Base):
    __tablename__ = "final_predictions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)
    label = Column(Enum(PredictionLabel), nullable=False)
    confidence_score = Column(Float, nullable=False)  # 0-1
    explanation = Column(Text)
    recommended_action = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="prediction")


# ---------------------------------------------------------------------------
# MODULE 10 - VERIFICATION REPORT
# ---------------------------------------------------------------------------

class VerificationReport(Base):
    __tablename__ = "verification_reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)
    verification_id = Column(String(50), unique=True, nullable=False)  # human-readable e.g. CV-2026-000123
    pdf_path = Column(String(500), nullable=True)
    digital_signature = Column(String(255), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)

    certificate = relationship("Certificate", back_populates="report")


# ---------------------------------------------------------------------------
# PHASE 2 - ASYNC VERIFICATION JOBS & PIPELINE OBSERVABILITY
# ---------------------------------------------------------------------------

class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineStage(str, enum.Enum):
    QUEUED = "QUEUED"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    OCR = "OCR"
    QR_VERIFICATION = "QR_VERIFICATION"
    BLOCKCHAIN_VERIFICATION = "BLOCKCHAIN_VERIFICATION"
    TAMPER_ANALYSIS = "TAMPER_ANALYSIS"
    DUPLICATE_DETECTION = "DUPLICATE_DETECTION"
    FRAUD_ANALYSIS = "FRAUD_ANALYSIS"
    TRUST_SCORE = "TRUST_SCORE"
    COMPLETED = "COMPLETED"


class VerificationJob(Base):
    __tablename__ = "verification_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False)

    status = Column(Enum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    current_stage = Column(Enum(PipelineStage), default=PipelineStage.QUEUED, nullable=False)
    progress_percentage = Column(Integer, default=0, nullable=False)

    stage_states = Column(JSON, nullable=True)
    error_details = Column(Text, nullable=True)
    failed_stage = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    certificate = relationship("Certificate", backref="verification_jobs")


# ---------------------------------------------------------------------------
# PHASE 3 - EVIDENCE PROVENANCE & EXPLAINABLE AI
# ---------------------------------------------------------------------------

class EvidenceType(str, enum.Enum):
    OCR = "OCR"
    QR = "QR"
    BLOCKCHAIN = "BLOCKCHAIN"
    TAMPER = "TAMPER"
    DUPLICATE = "DUPLICATE"
    STRUCTURE = "STRUCTURE"
    METADATA = "METADATA"
    FRAUD = "FRAUD"
    TRUST_SCORE = "TRUST_SCORE"


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True, index=True)
    certificate_id = Column(UUID(as_uuid=False), ForeignKey("certificates.id"), nullable=False, index=True)
    verification_job_id = Column(UUID(as_uuid=False), ForeignKey("verification_jobs.id"), nullable=True, index=True)

    evidence_type = Column(Enum(EvidenceType), nullable=False, index=True)
    source = Column(String(100), nullable=False)                    # e.g., "EasyOCR + Field Extractor"
    stage = Column(String(50), nullable=False)                     # e.g., "OCR", "DOCUMENT_ANALYSIS"
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    document_hash = Column(String(64), nullable=False)             # SHA-256 hash of certificate
    algorithm_engine = Column(String(100), nullable=False)
    algorithm_version = Column(String(50), default="1.0.0", nullable=True)
    confidence = Column(Float, nullable=False)                     # 0.0 - 1.0 (or normalized %)
    result = Column(String(50), nullable=False)                       # PASS, WARN, FAIL, VERIFIED, etc.
    explanation = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)                           # structured metadata/breakdown
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("Organization")
    certificate = relationship("Certificate", backref="evidence_items")
    verification_job = relationship("VerificationJob", backref="evidence_items")


# ---------------------------------------------------------------------------
# PHASE 4 - ENTERPRISE API ENGINE & WEBHOOKS
# ---------------------------------------------------------------------------

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    key_prefix = Column(String(16), nullable=False)                 # e.g., "cv_live_a1b2c3d4"
    hashed_key = Column(String(255), unique=True, index=True, nullable=False) # SHA-256 hash of raw key
    name = Column(String(100), nullable=False)
    permissions = Column(JSON, nullable=False)                       # ["certificate:read", "certificate:upload", ...]
    status = Column(String(30), default="active", nullable=False)   # active | revoked | expired
    rate_limit = Column(Integer, default=100, nullable=False)       # requests per minute
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", backref="api_keys")


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    endpoint_url = Column(String(500), nullable=False)
    secret_hash = Column(String(255), nullable=False)              # Secret key for HMAC-SHA256 signature
    subscribed_events = Column(JSON, nullable=False)                # ["verification.completed", "verification.failed", ...]
    active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    organization = relationship("Organization", backref="webhook_endpoints")
    deliveries = relationship("WebhookDelivery", back_populates="endpoint", cascade="all, delete-orphan")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    webhook_endpoint_id = Column(UUID(as_uuid=False), ForeignKey("webhook_endpoints.id"), nullable=False, index=True)

    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(30), default="PENDING", nullable=False)  # SUCCESS | FAILED | PENDING | RETRYING
    attempt_count = Column(Integer, default=1, nullable=False)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)

    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")



