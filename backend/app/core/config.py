"""
Central application configuration.
All values are pulled from environment variables (.env) — never hardcode secrets.
"""
from pydantic import model_validator, field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Any


class Settings(BaseSettings):
    # App
    APP_NAME: str = "CertiVerify AI - Fake Certificate Detection & Verification System"
    ENV: str = "production"  # Safe default: requires explicit ENV=development for dev mode
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Security / JWT
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEV_LONG_LIVED_SESSION: bool = False
    DEV_SESSION_EXPIRE_MINUTES: int = 1440
    OTP_EXPIRE_MINUTES: int = 10

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://certiverify:certiverify@localhost:5432/certiverify"
    DB_POOL_PRE_PING: bool = True
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_POOL_TIMEOUT_SECONDS: int = 30

    # Verification Job Lifecycle & Stale Recovery
    JOB_STALE_TIMEOUT_SECONDS: int = 120
    JOB_MAX_RETRIES: int = 3

    # Server Host & Port
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Health & System Checks
    HEALTH_PATH: str = "/health"
    READINESS_PATH: str = "/health/ready"
    HEALTH_CHECK_TIMEOUT_SECONDS: float = 3.0
    OCR_WARMUP_ENABLED: bool = True
    OCR_WARMUP_TIMEOUT_SECONDS: float = 30.0
    BLOCKCHAIN_CHECK_TIMEOUT_SECONDS: float = 3.0
    SIGNING_KEY_CHECK_TIMEOUT_SECONDS: float = 1.0

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    CORS_ORIGIN_REGEX: str | None = None

    # Email (SMTP) - used for verification + OTP emails
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@certiverify.ai"

    # File storage
    STORAGE_BACKEND: str = "local"  # "local" | "s3" | "cloudinary"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 15
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".jpg", ".jpeg", ".png"]

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "ap-south-1"

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Blockchain Configuration
    BLOCKCHAIN_PROVIDER: str = "none"  # "none" | "local_ledger" | "evm"
    BLOCKCHAIN_RPC_URL: str = "http://127.0.0.1:8545"  # Ganache / Node RPC
    BLOCKCHAIN_CONTRACT_ADDRESS: str = ""
    BLOCKCHAIN_ABI_PATH: str = ""
    BLOCKCHAIN_NETWORK_NAME: str = "localhost"
    BLOCKCHAIN_CONFIRMATION_COUNT: int = 1
    BLOCKCHAIN_TIMEOUT_SECONDS: float = 5.0
    BLOCKCHAIN_MAX_RETRIES: int = 2
    BLOCKCHAIN_RETRY_BACKOFF_SECONDS: float = 0.5
    BLOCKCHAIN_LOCAL_LEDGER_PATH: str = "data/local_blockchain_ledger.json"

    WEB3_PROVIDER_URL: str = "http://127.0.0.1:8545"  # Ganache (legacy alias)
    CONTRACT_ADDRESS: str = ""                         # (legacy alias)
    CONTRACT_OWNER_PRIVATE_KEY: str = ""

    # QR & External Verification
    QR_TRUSTED_DOMAINS: str = ""  # Comma-separated allowlist, e.g. "university.edu,gov.in"
    TRUSTED_QR_DOMAINS: str = ""  # Legacy alias
    QR_LIVE_CHECK_ENABLED: bool = False
    QR_LIVE_CHECK_TIMEOUT_SECONDS: float = 5.0
    QR_FUZZY_MATCH_THRESHOLD: float = 0.70
    UNIVERSITY_VERIFICATION_API: str = ""

    # Tampering & Forgery Detection Configuration (Module 3)
    TAMPERING_CHECK_WEIGHTS: str = '{"ela": 0.25, "pdf_metadata_structure": 0.20, "copy_move": 0.20, "noise_inconsistency": 0.15, "font_layout": 0.10, "image_quality": 0.10}'
    TAMPERING_ELA_QUALITY: int = 90
    TAMPERING_HEATMAP_OUTPUT_DIR: str = "uploads/ela_heatmaps"
    TAMPERING_RISK_BANDS: str = '{"LOW": 25.0, "MEDIUM": 60.0, "HIGH": 100.0}'
    TAMPERING_SUSPICIOUS_PRODUCERS: str = "photoshop,canva,illustrator,gimp,inkscape,coreldraw,paint.net,affinity,pixelmator,pdfedit"
    TAMPERING_METADATA_ONLY_CONFIDENCE_CAP: float = 40.0
    TAMPERING_COPY_MOVE_MIN_MATCHES: int = 12
    TAMPERING_ELA_ANOMALY_THRESHOLD: float = 18.0

    # MODULE 4: Duplicate Detection Settings
    DUPLICATE_CROSS_ORG_ALLOWED: bool = False
    DUPLICATE_EXCLUDE_SAME_GROUP: bool = False
    DUPLICATE_PERCEPTUAL_MAX_DISTANCE: int = 10
    DUPLICATE_FUZZY_NAME_THRESHOLD: float = 85.0
    DUPLICATE_FUZZY_FIELD_THRESHOLD: float = 85.0
    DUPLICATE_PERCEPTUAL_HASH_SIZE: int = 8

    # MODULE 5: AI Fraud Analysis Settings (8 signals matching DB schema)
    FRAUD_WEIGHT_OCR_ACCURACY: float = 0.15
    FRAUD_WEIGHT_COMPARISON: float = 0.15
    FRAUD_WEIGHT_QR: float = 0.10
    FRAUD_WEIGHT_BLOCKCHAIN: float = 0.15
    FRAUD_WEIGHT_TAMPERING: float = 0.20
    FRAUD_WEIGHT_DUPLICATE: float = 0.10
    FRAUD_WEIGHT_METADATA_INTEGRITY: float = 0.05
    FRAUD_WEIGHT_IMAGE_QUALITY: float = 0.10

    # Hard-floor override thresholds
    FRAUD_OVERRIDE_BLOCKCHAIN_MISMATCH_FLOOR: float = 0.85
    FRAUD_OVERRIDE_DIFFERENT_OWNER_DUPLICATE_FLOOR: float = 0.85
    FRAUD_OVERRIDE_CONFLICT_FLOOR: float = 0.90
    FRAUD_OVERRIDE_TAMPERING_THRESHOLD: float = 70.0
    FRAUD_OVERRIDE_TAMPERING_FLOOR: float = 0.75
    FRAUD_OVERRIDE_QR_INVALID_FLOOR: float = 0.65

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # MODULE 6: Trust Score Settings (8 components + bands)
    TRUST_SCORE_BAND_HIGH: float = 80.0
    TRUST_SCORE_BAND_MEDIUM: float = 50.0
    TRUST_WEIGHT_OCR: float = 0.15
    TRUST_WEIGHT_COMPARISON: float = 0.10
    TRUST_WEIGHT_QR: float = 0.15
    TRUST_WEIGHT_BLOCKCHAIN: float = 0.15
    TRUST_WEIGHT_TAMPERING: float = 0.15
    TRUST_WEIGHT_DUPLICATE: float = 0.10
    TRUST_WEIGHT_FRAUD: float = 0.10
    TRUST_WEIGHT_IMAGE_QUALITY: float = 0.10

    # MODULE 7: Final Prediction Settings
    PREDICTION_MIN_COVERAGE_FOR_VERDICT: float = 0.50  # Must have >= 50% checks evaluated (4 of 8)
    PREDICTION_GENUINE_TRUST_MIN: float = 80.0
    PREDICTION_GENUINE_FRAUD_MAX: float = 0.25
    PREDICTION_SUSPICIOUS_TRUST_MIN: float = 50.0
    PREDICTION_SUSPICIOUS_FRAUD_MAX: float = 0.60
    PREDICTION_ACTION_GENUINE: str = "Accept certificate — credential verified against institutional and forensic standards."
    PREDICTION_ACTION_SUSPICIOUS: str = "Manual review required — escalate to admissions/compliance officer for secondary inspection."
    PREDICTION_ACTION_FAKE: str = "Reject certificate — evidence indicates duplicate collision, tampering, or cryptographic forgery."
    PREDICTION_ACTION_INCONCLUSIVE: str = "Request original hardcopy or direct verification from the issuing institution (insufficient evidence coverage / inconclusive verdict)."


    # MODULE 8: PDF Report Generation Settings
    REPORT_ORG_NAME: str = "CertiVerify Enterprise"
    REPORT_LOGO_PATH: str | None = None
    REPORT_FOOTER_TEXT: str = "Confidential Verification Report — CertiVerify Enterprise Integrity Engine"
    REPORT_OUTPUT_DIR: str = "uploads/reports"
    REPORT_PAGE_SIZE: str = "A4"  # A4 or LETTER
    REPORT_VERIFY_URL_TEMPLATE: str = "http://localhost:3000/verify/{verification_id}"
    REPORT_SIGNING_KEY: str | None = None

    # Auth & Email Verification
    EMAIL_VERIFICATION_REQUIRED: bool | None = None

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def compute_email_verification(self) -> "Settings":
        if self.EMAIL_VERIFICATION_REQUIRED is None:
            self.EMAIL_VERIFICATION_REQUIRED = self.ENV.lower() not in ("development", "dev", "test")
        return self

    @model_validator(mode="after")
    def validate_fraud_weights(self) -> "Settings":
        total_weights = (
            self.FRAUD_WEIGHT_OCR_ACCURACY
            + self.FRAUD_WEIGHT_COMPARISON
            + self.FRAUD_WEIGHT_QR
            + self.FRAUD_WEIGHT_BLOCKCHAIN
            + self.FRAUD_WEIGHT_TAMPERING
            + self.FRAUD_WEIGHT_DUPLICATE
            + self.FRAUD_WEIGHT_METADATA_INTEGRITY
            + self.FRAUD_WEIGHT_IMAGE_QUALITY
        )
        if total_weights <= 0.0:
            raise ValueError(f"Total fraud weights must be positive, got {total_weights}")
        return self

    def validate_production_configuration(self) -> None:
        """
        Production safety check: Refuses startup if unsafe settings are detected in production.
        """
        if self.ENV.lower() in ("production", "prod"):
            insecure_defaults = {
                "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32",
                "secret",
                "changeme",
                "replace_with_openssl_rand_hex_32",
                "testsecret",
            }
            if not self.SECRET_KEY or self.SECRET_KEY in insecure_defaults or len(self.SECRET_KEY) < 32:
                raise ValueError("Insecure or default SECRET_KEY set in production mode!")
            if self.DEBUG:
                raise ValueError("PRODUCTION REFUSAL: DEBUG mode must be disabled (DEBUG=false) in production.")
            if not self.DATABASE_URL.lower().startswith(("postgresql://", "postgresql+asyncpg://")):
                raise ValueError(
                    f"PRODUCTION REFUSAL: Database must be PostgreSQL in production (got {self.DATABASE_URL.split('://')[0]})."
                )
            if "*" in self.ALLOWED_ORIGINS:
                raise ValueError("PRODUCTION REFUSAL: Wildcard CORS origin '*' is forbidden in production.")
            if self.DEV_LONG_LIVED_SESSION:
                raise ValueError("PRODUCTION REFUSAL: DEV_LONG_LIVED_SESSION cannot be enabled in production.")

    validate_production_secrets = validate_production_configuration

    class Config:
        env_file = (".env", "backend/.env")
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_production_secrets()
    return s


settings = get_settings()

