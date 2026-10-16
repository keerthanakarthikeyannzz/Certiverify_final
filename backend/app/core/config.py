"""
Central application configuration.
All values are pulled from environment variables (.env) — never hardcode secrets.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


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
    OTP_EXPIRE_MINUTES: int = 10

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://certiverify:certiverify@localhost:5432/certiverify"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

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

    # Blockchain
    WEB3_PROVIDER_URL: str = "http://127.0.0.1:8545"  # Ganache
    CONTRACT_ADDRESS: str = ""
    CONTRACT_OWNER_PRIVATE_KEY: str = ""

    # QR & External Verification
    TRUSTED_QR_DOMAINS: str = ""
    UNIVERSITY_VERIFICATION_API: str = ""

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

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

