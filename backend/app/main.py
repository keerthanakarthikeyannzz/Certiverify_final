"""
CertiVerify AI - Application entrypoint.
Wires together middleware, routers, and startup/shutdown events.
"""
import logging
import os

# Prevent TensorFlow/Transformers dynamic library conflict and OpenMP duplication crashes on macOS
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.db.database import init_db
from app.api import auth as auth_router
from app.api import certificates as certificates_router
from app.api import document_type as document_type_router
from app.api import ocr as ocr_router
from app.api import comparison as comparison_router
from app.api import verification as verification_router
from app.api import fraud as fraud_router
from app.api import trust_score as trust_score_router
from app.api import prediction as prediction_router
from app.api import report as report_router
from app.api import direct_compare as direct_compare_router
from app.api import verification_result as verification_result_router
# Priority 8 — Analytics & Pipeline Status
from app.api import analytics as analytics_router
from app.api import pipeline_status as pipeline_status_router

# Enterprise Core — Organizations & Audit Logs
from app.api import organizations as organizations_router
from app.api import audit as audit_router
from app.api import jobs as jobs_router
import ipaddress

_TRUSTED_PROXY_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("::1/128"),
)


def _is_trusted_proxy_host(host: str) -> bool:
    if host in ("testclient", "localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _TRUSTED_PROXY_NETWORKS)
    except ValueError:
        return False


def get_trusted_client_ip(request: Request) -> str:
    """
    Extract client IP address. Trusts X-Forwarded-For ONLY when the direct
    request comes from a trusted local or container reverse proxy (Next.js).
    """
    direct_host = request.client.host if request.client else "127.0.0.1"
    if _is_trusted_proxy_host(direct_host):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                return client_ip
    return direct_host


limiter = Limiter(key_func=get_trusted_client_ip, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Fake Certificate Detection & Verification System - REST API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
is_dev_env = settings.ENV.lower() in ("development", "dev", "test")
cors_origin_regex = (
    settings.CORS_ORIGIN_REGEX
    if settings.CORS_ORIGIN_REGEX is not None
    else (r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if is_dev_env else None)
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "Content-Length",
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
)


# Request ID Correlation Middleware & Security headers
@app.middleware("http")
async def add_security_and_correlation_headers(request: Request, call_next):
    import uuid
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    
    # Phase 4 Telemetry Headers for Rate Limiting
    if hasattr(request.state, "rate_limit"):
        response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit)
    if hasattr(request.state, "rate_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(request.state.rate_remaining)
    if hasattr(request.state, "rate_reset"):
        response.headers["X-RateLimit-Reset"] = str(request.state.rate_reset)

    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        headers = getattr(exc, "headers", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )
    import traceback as _tb
    _logger = logging.getLogger("certiverify.unhandled")
    req_id = getattr(request.state, "request_id", "unknown")
    _logger.error(
        "Unhandled exception [req_id=%s] on %s %s:\n%s",
        req_id, request.method, request.url.path,
        _tb.format_exc(),
    )
    err_detail = "The verification service encountered an internal error. Please try again later."
    if getattr(settings, "ENVIRONMENT", "development") != "production":
        err_detail = f"Internal verification error: {str(exc)}"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": err_detail, "error": str(exc)},
    )


# Component health registry
component_status = {
    "ocr_engine": "initializing" if settings.OCR_WARMUP_ENABLED else "disabled",
    "ocr_detail": None,
    "blockchain_provider": "disabled",
    "blockchain_detail": None,
    "signing_key": "ok",
    "signing_key_detail": None,
}


@app.on_event("startup")
async def on_startup():
    settings.validate_production_configuration()
    import asyncio as _asyncio

    # Initialize database
    try:
        await init_db()
    except Exception as exc:
        logging.getLogger("certiverify.startup").exception("Database initialization failed: %s", exc)

    # Background non-blocking task for heavy component initialization / warmup
    async def _safe_component_init():
        startup_logger = logging.getLogger("certiverify.startup")

        # 1. Check report signing key
        try:
            async def _check_key():
                from app.services.report_service import get_report_signing_key
                key = get_report_signing_key()
                if getattr(settings, "REPORT_SIGNING_KEY", None):
                    component_status["signing_key"] = "ok"
                    component_status["signing_key_detail"] = "Configured"
                else:
                    component_status["signing_key"] = "degraded"
                    component_status["signing_key_detail"] = "Falling back to SECRET_KEY (non-production)"
            await _asyncio.wait_for(_check_key(), timeout=settings.SIGNING_KEY_CHECK_TIMEOUT_SECONDS)
        except Exception as exc:
            startup_logger.exception("Report signing key validation failed: %s", exc)
            component_status["signing_key"] = "degraded"
            component_status["signing_key_detail"] = str(exc)

        # 2. Check blockchain provider
        try:
            async def _check_blockchain():
                bc_prov = (getattr(settings, "BLOCKCHAIN_PROVIDER", "") or "none").strip().lower()
                if bc_prov == "none":
                    component_status["blockchain_provider"] = "disabled"
                    component_status["blockchain_detail"] = "Provider set to none"
                elif bc_prov in ("local_ledger", "local", "ledger"):
                    component_status["blockchain_provider"] = "ok"
                    component_status["blockchain_detail"] = f"Local ledger file: {settings.BLOCKCHAIN_LOCAL_LEDGER_PATH}"
                elif bc_prov in ("evm", "ethereum", "web3"):
                    from app.services.blockchain_service import get_blockchain_provider
                    prov = get_blockchain_provider()
                    w3, contract = prov._get_web3_and_contract()
                    if contract is not None:
                        component_status["blockchain_provider"] = "ok"
                        component_status["blockchain_detail"] = f"Connected to {settings.BLOCKCHAIN_RPC_URL}"
                    else:
                        component_status["blockchain_provider"] = "degraded"
                        component_status["blockchain_detail"] = "RPC unreachable or contract unconfigured"
                else:
                    component_status["blockchain_provider"] = "disabled"
                    component_status["blockchain_detail"] = f"Unknown provider: {bc_prov}"
            await _asyncio.wait_for(_check_blockchain(), timeout=settings.BLOCKCHAIN_CHECK_TIMEOUT_SECONDS)
        except Exception as exc:
            startup_logger.exception("Blockchain provider check failed: %s", exc)
            component_status["blockchain_provider"] = "degraded"
            component_status["blockchain_detail"] = str(exc)

        # 3. EasyOCR warmup
        if not settings.OCR_WARMUP_ENABLED:
            component_status["ocr_engine"] = "disabled"
            component_status["ocr_detail"] = "OCR warmup disabled via settings"
        else:
            try:
                from app.services.ocr_engine import warmup_easyocr
                await _asyncio.wait_for(
                    _asyncio.to_thread(warmup_easyocr),
                    timeout=settings.OCR_WARMUP_TIMEOUT_SECONDS
                )
                component_status["ocr_engine"] = "ok"
                component_status["ocr_detail"] = "EasyOCR model loaded and warmed"
            except Exception as exc:
                startup_logger.exception("EasyOCR warmup failed: %s", exc)
                component_status["ocr_engine"] = "degraded"
                component_status["ocr_detail"] = f"Warmup failed (loads lazily on first OCR call): {exc}"

    _asyncio.create_task(_safe_component_init())


@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
async def health_check():
    """
    Lightweight liveness probe (no DB, no model inference).
    Always returns 200 immediately if process is responsive.
    """
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health/ready", tags=["System"])
@app.get("/api/health/ready", tags=["System"])
async def readiness_check():
    """
    Readiness check verifying database availability and reporting
    status of optional components (OCR models, blockchain, signing key).
    """
    import asyncio as _asyncio
    status_dict = {
        "status": "ready",
        "app": settings.APP_NAME,
        "database": "ok",
        "storage": "ok",
        "components": {
            "ocr_engine": component_status.get("ocr_engine", "disabled"),
            "blockchain_provider": component_status.get("blockchain_provider", "disabled"),
            "signing_key": component_status.get("signing_key", "ok"),
        },
        "details": {
            "ocr": component_status.get("ocr_detail"),
            "blockchain": component_status.get("blockchain_detail"),
            "signing_key": component_status.get("signing_key_detail"),
        },
    }

    # Verify database connectivity with timeout
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import text
        async def _ping_db():
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
        await _asyncio.wait_for(_ping_db(), timeout=settings.HEALTH_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        status_dict["status"] = "unhealthy"
        status_dict["database"] = f"error: {exc}"

    # Verify local/cloud storage path
    try:
        from app.services.storage_service import get_storage_backend
        storage = get_storage_backend()
        if hasattr(storage, "base_dir") and not os.path.exists(storage.base_dir):
            status_dict["storage"] = "warning: storage path missing"
    except Exception as exc:
        status_dict["status"] = "unhealthy"
        status_dict["storage"] = f"error: {exc}"

    # Surface degraded optional components if DB is healthy
    if status_dict["status"] == "ready":
        if any(v == "degraded" for v in status_dict["components"].values()):
            status_dict["status"] = "degraded"

    status_code = (
        status.HTTP_200_OK
        if status_dict["status"] in ("ready", "degraded")
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=status_dict)


# ---------------- Routers ----------------
app.include_router(auth_router.router)
app.include_router(certificates_router.router)
app.include_router(document_type_router.router)
app.include_router(ocr_router.router)
app.include_router(comparison_router.router)
app.include_router(verification_router.router)
app.include_router(fraud_router.router)
app.include_router(trust_score_router.router)
app.include_router(prediction_router.router)

# Module 10 — Verification Report & Dashboard
app.include_router(report_router.router)

# Unified verification result (single-call for trust + fraud + prediction + evidence)
app.include_router(verification_result_router.router)

# Direct Compare — in-memory two-document comparison (no DB writes)
app.include_router(direct_compare_router.router)

# Priority 8 — Analytics & Pipeline Status
app.include_router(analytics_router.router)
app.include_router(pipeline_status_router.router)

# Enterprise Core — Organizations & Audit Logs & Async Jobs
app.include_router(organizations_router.router)
app.include_router(audit_router.router)
app.include_router(jobs_router.router)

# Phase 3 — Evidence Provenance & Explainable AI
from app.api import evidence as evidence_router
app.include_router(evidence_router.router)

# Phase 4 — Enterprise API Engine & Webhooks
from app.api import api_keys as api_keys_router
from app.api import webhooks as webhooks_router
app.include_router(api_keys_router.router)
app.include_router(webhooks_router.router)




