"""
PRIORITY 8 - ANALYTICS API

Provides aggregated analytics over the current user's certificates.
All queries target existing tables — NO new DB tables created.

Endpoints:
  GET /api/v1/analytics/overview          — extended dashboard metrics
  GET /api/v1/analytics/doc-types         — document type distribution
  GET /api/v1/analytics/trust-distribution — trust score histogram (4 bands)
  GET /api/v1/analytics/fraud-signals     — per-signal fraud indicator counts
  GET /api/v1/analytics/time-trends       — daily/weekly verification counts
  GET /api/v1/analytics/university-stats  — top university breakdown (no PII)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    Certificate, DocumentType, FinalPrediction, FraudAnalysis,
    OCRData, TrustScore, User, VerificationReport, VerificationResult,
)
from app.api.deps import get_current_verified_user

router = APIRouter(tags=["Analytics"])


# ── Pydantic response models ─────────────────────────────────────────────────

class AnalyticsOverview(BaseModel):
    total_certificates: int
    genuine_count: int
    suspicious_count: int
    fake_count: int
    not_predicted_count: int
    duplicate_count: int
    tampered_count: int
    qr_verified_count: int
    blockchain_verified_count: int
    avg_trust_score: Optional[float] = None
    avg_ocr_accuracy: Optional[float] = None
    avg_fraud_probability: Optional[float] = None
    avg_tampering_score: Optional[float] = None
    qr_verification_rate: Optional[float] = None      # 0-100 %
    blockchain_verification_rate: Optional[float] = None
    tampering_detection_rate: Optional[float] = None
    verification_completion_rate: Optional[float] = None


class DocTypeDistribution(BaseModel):
    doc_types: dict[str, int]        # {"aadhaar": 5, "degree": 12, ...}
    total_classified: int


class TrustBand(BaseModel):
    label: str       # "90-100", "80-89", "60-79", "0-59"
    description: str # "High Trust", "Good Trust", etc.
    count: int
    percentage: float


class TrustDistribution(BaseModel):
    bands: list[TrustBand]
    total_scored: int


class FraudSignals(BaseModel):
    tampering_detected: int
    duplicates_detected: int
    blockchain_mismatch: int
    qr_invalid: int
    comparison_mismatch: int
    certificate_conflict: int      # CERTIFICATE_CONFLICT from P7


class TimeTrend(BaseModel):
    period: str             # "2026-08-28", "2026-W35", "2026-08"
    uploaded: int
    verified: int


class TimeTrendResponse(BaseModel):
    daily: list[TimeTrend]     # last 14 days
    weekly: list[TimeTrend]    # last 8 weeks
    monthly: list[TimeTrend]   # last 6 months


class UniversityStat(BaseModel):
    university_name: str
    total: int
    genuine: int
    suspicious: int
    fake: int
    avg_trust_score: Optional[float] = None


class UniversityStats(BaseModel):
    universities: list[UniversityStat]


# ── Shared helper ────────────────────────────────────────────────────────────

async def _get_user_cert_ids(user: User, db: AsyncSession) -> tuple[list[str], list[Certificate]]:
    certs_result = await db.execute(
        select(Certificate)
        .where(Certificate.owner_id == user.id)
        .order_by(Certificate.uploaded_at.desc())
    )
    certs = certs_result.scalars().all()
    return [c.id for c in certs], list(certs)


def _map_by_cert_id(rows) -> dict:
    return {r.certificate_id: r for r in rows}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/v1/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Extended analytics overview — all metrics sourced from existing tables."""
    cert_ids, certs = await _get_user_cert_ids(user, db)
    total = len(cert_ids)

    if not cert_ids:
        return AnalyticsOverview(
            total_certificates=0, genuine_count=0, suspicious_count=0,
            fake_count=0, not_predicted_count=total, duplicate_count=0,
            tampered_count=0, qr_verified_count=0, blockchain_verified_count=0,
        )

    pred_rows = _map_by_cert_id(
        (await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id.in_(cert_ids)))).scalars().all()
    )
    vr_rows = _map_by_cert_id(
        (await db.execute(select(VerificationResult).where(VerificationResult.certificate_id.in_(cert_ids)))).scalars().all()
    )
    trust_rows = _map_by_cert_id(
        (await db.execute(select(TrustScore).where(TrustScore.certificate_id.in_(cert_ids)))).scalars().all()
    )
    ocr_rows = _map_by_cert_id(
        (await db.execute(select(OCRData).where(OCRData.certificate_id.in_(cert_ids)))).scalars().all()
    )
    fraud_rows = _map_by_cert_id(
        (await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id.in_(cert_ids)))).scalars().all()
    )

    genuine = suspicious = fake = not_predicted = 0
    for cid in cert_ids:
        p = pred_rows.get(cid)
        if p is None:
            not_predicted += 1
        elif str(p.label) in ("genuine", "PredictionLabel.genuine"):
            genuine += 1
        elif str(p.label) in ("suspicious", "PredictionLabel.suspicious"):
            suspicious += 1
        elif str(p.label) in ("fake", "PredictionLabel.fake"):
            fake += 1
        else:
            not_predicted += 1

    duplicate_count = sum(1 for vr in vr_rows.values() if vr.is_duplicate)
    tampered_count = sum(
        1 for vr in vr_rows.values()
        if vr.tampering_risk_level in ("HIGH_RISK", "VERY_HIGH_RISK")
    )
    qr_verified = sum(1 for vr in vr_rows.values() if vr.qr_valid is True)
    blockchain_verified = sum(
        1 for vr in vr_rows.values() if vr.blockchain_status == "verified"
    )

    trust_scores = [t.score for t in trust_rows.values() if t.score is not None]
    ocr_accs = [o.ocr_accuracy for o in ocr_rows.values() if o.ocr_accuracy is not None]
    fraud_probs = [f.fraud_probability for f in fraud_rows.values() if f.fraud_probability is not None]
    tamp_scores = [vr.tampering_score for vr in vr_rows.values() if vr.tampering_score is not None]

    verified_count = len(vr_rows)

    return AnalyticsOverview(
        total_certificates=total,
        genuine_count=genuine,
        suspicious_count=suspicious,
        fake_count=fake,
        not_predicted_count=not_predicted,
        duplicate_count=duplicate_count,
        tampered_count=tampered_count,
        qr_verified_count=qr_verified,
        blockchain_verified_count=blockchain_verified,
        avg_trust_score=round(sum(trust_scores) / len(trust_scores), 2) if trust_scores else None,
        avg_ocr_accuracy=round(sum(ocr_accs) / len(ocr_accs), 4) if ocr_accs else None,
        avg_fraud_probability=round(sum(fraud_probs) / len(fraud_probs), 4) if fraud_probs else None,
        avg_tampering_score=round(sum(tamp_scores) / len(tamp_scores), 2) if tamp_scores else None,
        qr_verification_rate=round(qr_verified / total * 100, 1) if total else None,
        blockchain_verification_rate=round(blockchain_verified / total * 100, 1) if total else None,
        tampering_detection_rate=round(tampered_count / total * 100, 1) if total else None,
        verification_completion_rate=round(verified_count / total * 100, 1) if total else None,
    )


@router.get("/api/v1/analytics/doc-types", response_model=DocTypeDistribution)
async def analytics_doc_types(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Document type distribution from the DocumentType classifier table."""
    cert_ids, _ = await _get_user_cert_ids(user, db)
    if not cert_ids:
        return DocTypeDistribution(doc_types={}, total_classified=0)

    dt_rows = (await db.execute(
        select(DocumentType).where(DocumentType.certificate_id.in_(cert_ids))
    )).scalars().all()

    counts: dict[str, int] = defaultdict(int)
    for row in dt_rows:
        # predicted_type is a DocTypeEnum — normalise to string
        key = str(row.predicted_type.value if hasattr(row.predicted_type, "value") else row.predicted_type)
        counts[key] += 1

    return DocTypeDistribution(doc_types=dict(counts), total_classified=len(dt_rows))


@router.get("/api/v1/analytics/trust-distribution", response_model=TrustDistribution)
async def analytics_trust_distribution(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Trust score histogram split into 4 risk bands."""
    cert_ids, _ = await _get_user_cert_ids(user, db)
    if not cert_ids:
        return TrustDistribution(bands=[], total_scored=0)

    trust_rows = (await db.execute(
        select(TrustScore).where(TrustScore.certificate_id.in_(cert_ids))
    )).scalars().all()

    band_counts = {"90-100": 0, "80-89": 0, "60-79": 0, "0-59": 0}
    for t in trust_rows:
        s = t.score
        if s is None:
            continue
        if s >= 90:
            band_counts["90-100"] += 1
        elif s >= 80:
            band_counts["80-89"] += 1
        elif s >= 60:
            band_counts["60-79"] += 1
        else:
            band_counts["0-59"] += 1

    total_scored = len(trust_rows)
    bands = [
        TrustBand(label="90–100", description="High Trust",       count=band_counts["90-100"], percentage=round(band_counts["90-100"] / total_scored * 100, 1) if total_scored else 0),
        TrustBand(label="80–89",  description="Good Trust",       count=band_counts["80-89"],  percentage=round(band_counts["80-89"]  / total_scored * 100, 1) if total_scored else 0),
        TrustBand(label="60–79",  description="Suspicious Range", count=band_counts["60-79"],  percentage=round(band_counts["60-79"]  / total_scored * 100, 1) if total_scored else 0),
        TrustBand(label="0–59",   description="High Risk",        count=band_counts["0-59"],   percentage=round(band_counts["0-59"]   / total_scored * 100, 1) if total_scored else 0),
    ]
    return TrustDistribution(bands=bands, total_scored=total_scored)


@router.get("/api/v1/analytics/fraud-signals", response_model=FraudSignals)
async def analytics_fraud_signals(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-signal fraud indicator counts across all of the user's certificates."""
    cert_ids, certs = await _get_user_cert_ids(user, db)
    if not cert_ids:
        return FraudSignals(
            tampering_detected=0, duplicates_detected=0, blockchain_mismatch=0,
            qr_invalid=0, comparison_mismatch=0, certificate_conflict=0,
        )

    vr_rows = (await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id.in_(cert_ids))
    )).scalars().all()

    tampering = sum(1 for vr in vr_rows if vr.tampering_risk_level in ("HIGH_RISK", "VERY_HIGH_RISK"))
    duplicates = sum(1 for vr in vr_rows if vr.is_duplicate)
    bc_mismatch = sum(1 for vr in vr_rows if vr.blockchain_status == "mismatch")
    qr_invalid = sum(1 for vr in vr_rows if vr.qr_present and vr.qr_valid is False)

    # Certificate conflict: duplicate_detail.duplicate_status == CERTIFICATE_CONFLICT
    cert_conflict = sum(
        1 for vr in vr_rows
        if vr.duplicate_detail
        and isinstance(vr.duplicate_detail, dict)
        and vr.duplicate_detail.get("duplicate_type") == "CERTIFICATE_CONFLICT"
    )

    # Comparison mismatch: uses DocumentComparison if available (keyed on group_id)
    from app.models.models import DocumentComparison
    group_ids = list({c.group_id for c in certs if c.group_id})
    comp_mismatch = 0
    if group_ids:
        comp_rows = (await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id.in_(group_ids))
        )).scalars().all()
        comp_mismatch = sum(1 for c in comp_rows if c.consistency_percentage is not None and c.consistency_percentage < 70)

    return FraudSignals(
        tampering_detected=tampering,
        duplicates_detected=duplicates,
        blockchain_mismatch=bc_mismatch,
        qr_invalid=qr_invalid,
        comparison_mismatch=comp_mismatch,
        certificate_conflict=cert_conflict,
    )


@router.get("/api/v1/analytics/time-trends", response_model=TimeTrendResponse)
async def analytics_time_trends(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily (14d), weekly (8w), and monthly (6mo) upload/verification trends."""
    _, certs = await _get_user_cert_ids(user, db)

    cert_ids = [c.id for c in certs]
    vr_map: dict[str, datetime] = {}
    if cert_ids:
        vr_rows = (await db.execute(
            select(VerificationResult).where(VerificationResult.certificate_id.in_(cert_ids))
        )).scalars().all()
        vr_map = {vr.certificate_id: vr.created_at for vr in vr_rows}

    now = datetime.utcnow()

    # Daily last 14 days
    daily: list[TimeTrend] = []
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_str = day.strftime("%Y-%m-%d")
        uploaded = sum(1 for c in certs if c.uploaded_at.date() == day)
        verified = sum(1 for c in certs if c.id in vr_map and vr_map[c.id].date() == day)
        daily.append(TimeTrend(period=day_str, uploaded=uploaded, verified=verified))

    # Weekly last 8 weeks
    weekly: list[TimeTrend] = []
    for i in range(7, -1, -1):
        week_start = (now - timedelta(weeks=i)).date()
        week_start -= timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6)
        label = f"{week_start.strftime('%Y-%m-%d')}"
        uploaded = sum(1 for c in certs if week_start <= c.uploaded_at.date() <= week_end)
        verified = sum(1 for c in certs if c.id in vr_map and week_start <= vr_map[c.id].date() <= week_end)
        weekly.append(TimeTrend(period=label, uploaded=uploaded, verified=verified))

    # Monthly last 6 months
    monthly: list[TimeTrend] = []
    for i in range(5, -1, -1):
        target = now.replace(day=1) - timedelta(days=i * 30)
        label = target.strftime("%Y-%m")
        uploaded = sum(1 for c in certs if c.uploaded_at.strftime("%Y-%m") == label)
        verified = sum(1 for c in certs if c.id in vr_map and vr_map[c.id].strftime("%Y-%m") == label)
        monthly.append(TimeTrend(period=label, uploaded=uploaded, verified=verified))

    return TimeTrendResponse(daily=daily, weekly=weekly, monthly=monthly)


@router.get("/api/v1/analytics/university-stats", response_model=UniversityStats)
async def analytics_university_stats(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Top university breakdown — no student PII exposed, only aggregate counts."""
    cert_ids, _ = await _get_user_cert_ids(user, db)
    if not cert_ids:
        return UniversityStats(universities=[])

    ocr_rows = (await db.execute(
        select(OCRData).where(OCRData.certificate_id.in_(cert_ids))
    )).scalars().all()

    pred_rows = _map_by_cert_id(
        (await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id.in_(cert_ids)))).scalars().all()
    )
    trust_rows = _map_by_cert_id(
        (await db.execute(select(TrustScore).where(TrustScore.certificate_id.in_(cert_ids)))).scalars().all()
    )

    # Aggregate per university
    uni_data: dict[str, dict] = {}
    for ocr in ocr_rows:
        uni = (ocr.university_name or "").strip()
        if not uni or uni.lower() in ("n/a", "na", "none", "unknown", ""):
            uni = "Unknown / N/A"
        if uni not in uni_data:
            uni_data[uni] = {"total": 0, "genuine": 0, "suspicious": 0, "fake": 0, "trust_scores": []}
        uni_data[uni]["total"] += 1
        pred = pred_rows.get(ocr.certificate_id)
        if pred:
            label = str(pred.label.value if hasattr(pred.label, "value") else pred.label)
            if label == "genuine":
                uni_data[uni]["genuine"] += 1
            elif label == "suspicious":
                uni_data[uni]["suspicious"] += 1
            elif label == "fake":
                uni_data[uni]["fake"] += 1
        trust = trust_rows.get(ocr.certificate_id)
        if trust and trust.score is not None:
            uni_data[uni]["trust_scores"].append(trust.score)

    # Sort by total desc, return top 10
    stats = []
    for uni, d in sorted(uni_data.items(), key=lambda x: x[1]["total"], reverse=True)[:10]:
        ts = d["trust_scores"]
        stats.append(UniversityStat(
            university_name=uni,
            total=d["total"],
            genuine=d["genuine"],
            suspicious=d["suspicious"],
            fake=d["fake"],
            avg_trust_score=round(sum(ts) / len(ts), 1) if ts else None,
        ))

    return UniversityStats(universities=stats)
