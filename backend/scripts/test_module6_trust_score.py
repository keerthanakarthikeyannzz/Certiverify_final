"""
Verification and Demonstration Script for MODULE 6: Trust Score (trust_score)

Tests and Displays the breakdown for:
1. Verified-looking document (all or most checks pass, high coverage, high trust score)
2. Partial-evidence document (clean document with unconfigured QR/blockchain, demonstrates coverage and weight renormalization without penalty)
3. Suspicious document (tampering, duplicate collision, invalid QR, high fraud probability, low score, failed status)

Also tests live database execution via run_trust_score and get_trust_score.
"""
import asyncio
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Certificate, User, TrustScore
from app.services.trust_score import TrustScoreInputs, compute_trust_score
from app.api.trust_score import run_trust_score, get_trust_score
from sqlalchemy import select


def print_breakdown_table(title: str, result):
    print("\n" + "=" * 90)
    print(f"DOCUMENT CASE: {title}")
    print("=" * 90)
    print(f"TRUST SCORE:         {result.score:.2f} / 100")
    print(f"TRUST BAND:          {result.band} ({result.band_label})")
    print(f"EVIDENCE COVERAGE:   {result.coverage_percentage:.1f}% ({result.checks_evaluated} of {result.checks_total} checks evaluated)")
    if result.hard_ceilings_applied:
        print(f"HARD CEILINGS:       {', '.join(result.hard_ceilings_applied)}")
    else:
        print(f"HARD CEILINGS:       None applied")

    print("\nITEMIZED COMPONENT BREAKDOWN:")
    print(f"{'Component':<28} {'Status':<15} {'Value':<8} {'Weight':<10} {'Contrib':<10} {'Reason'}")
    print("-" * 115)
    for c in result.components:
        val_str = f"{c.value:.1f}" if c.value is not None else "—"
        weight_str = f"{c.weight * 100:.1f}%"
        contrib_str = f"+{c.contribution:.2f}"
        print(f"{c.label[:27]:<28} {c.status:<15} {val_str:<8} {weight_str:<10} {contrib_str:<10} {c.reason}")
    print("-" * 115)


async def main():
    await init_db()

    print("\n==========================================================================")
    print("MODULE 6: TRUST SCORE STAGE TEST & DEMONSTRATION")
    print("==========================================================================")

    # =========================================================================
    # CASE 1: VERIFIED-LOOKING DOCUMENT (Full evidence, clean and authentic)
    # =========================================================================
    verified_inputs = TrustScoreInputs(
        ocr_accuracy=0.98,
        field_extraction_completeness=1.0,
        doc_classification_confidence=0.99,
        document_consistency_pct=98.5,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        blockchain_match=True,
        tampering_score=4.2, # authentic
        tampering_risk_level="LOW",
        is_duplicate=False,
        fraud_probability=0.03,
        image_quality_score=94.0,
    )
    verified_result = compute_trust_score(verified_inputs)
    print_breakdown_table("1. VERIFIED-LOOKING DOCUMENT (FULL EVIDENCE)", verified_result)

    assert verified_result.score >= 90.0, f"Expected score >= 90, got {verified_result.score}"
    assert verified_result.band == "HIGH"
    assert verified_result.coverage == 1.0
    assert verified_result.checks_evaluated == 8

    # =========================================================================
    # CASE 2: PARTIAL-EVIDENCE DOCUMENT (Missing QR & Blockchain, clean OCR & Tampering)
    # =========================================================================
    partial_inputs = TrustScoreInputs(
        ocr_accuracy=0.96,
        field_extraction_completeness=0.95,
        doc_classification_confidence=0.95,
        document_consistency_pct=None, # Single doc upload -> not evaluated
        qr_present=False,              # Document has no QR -> not evaluated
        qr_valid=None,
        blockchain_status="unavailable", # Blockchain not configured -> not evaluated
        blockchain_match=None,
        tampering_score=7.8,           # Clean visual analysis
        tampering_risk_level="LOW",
        is_duplicate=False,            # Unique in registry
        fraud_probability=0.07,        # Clean fraud profile
        image_quality_score=91.5,
    )
    partial_result = compute_trust_score(partial_inputs)
    print_breakdown_table("2. PARTIAL-EVIDENCE DOCUMENT (4 OF 8 CHECKS EVALUATED)", partial_result)

    assert partial_result.checks_evaluated == 5
    assert partial_result.coverage == 5 / 8
    # Score must remain in HIGH band despite unconfigured checks (not dragged down to 0)
    assert partial_result.score >= 85.0, f"Expected score >= 85, got {partial_result.score}"
    assert partial_result.band == "HIGH"

    # Verify that QR and Blockchain are listed as "not evaluated"
    qr_c = next(c for c in partial_result.components if c.component == "qr")
    assert qr_c.status == "not evaluated"
    assert qr_c.weight == 0.0
    assert qr_c.contribution == 0.0

    bc_c = next(c for c in partial_result.components if c.component == "blockchain")
    assert bc_c.status == "not evaluated"
    assert bc_c.weight == 0.0

    # =========================================================================
    # CASE 3: SUSPICIOUS DOCUMENT (Tampering, invalid QR, duplicate collision)
    # =========================================================================
    suspicious_inputs = TrustScoreInputs(
        ocr_accuracy=0.62,
        field_extraction_completeness=0.50,
        doc_classification_confidence=0.70,
        document_consistency_pct=35.0,
        qr_present=True,
        qr_valid=False,                 # Invalid QR
        qr_warning="Cryptographic signature mismatch",
        blockchain_status="mismatch",   # Blockchain hash mismatch
        blockchain_match=False,
        tampering_score=72.5,           # Severe tampering
        tampering_risk_level="HIGH_RISK",
        is_duplicate=True,              # Duplicate collision
        duplicate_same_owner=False,
        duplicate_detail={"same_owner": False, "owner_distinction": "DIFFERENT_OWNER_DUPLICATE"},
        fraud_probability=0.88,         # Very high fraud probability
        image_quality_score=42.0,
    )
    suspicious_result = compute_trust_score(suspicious_inputs)
    print_breakdown_table("3. SUSPICIOUS DOCUMENT (CRITICAL ANOMALIES & HARD CEILINGS)", suspicious_result)

    assert suspicious_result.score <= 15.0, f"Expected score <= 15 due to duplicate collision ceiling, got {suspicious_result.score}"
    assert suspicious_result.band == "LOW"
    assert len(suspicious_result.hard_ceilings_applied) > 0

    # =========================================================================
    # CASE 4: LIVE DATABASE PERSISTENCE & API ROUTE VERIFICATION
    # =========================================================================
    print("\n==========================================================================")
    print("4. LIVE DATABASE & GET /trust-score ENDPOINT VERIFICATION")
    print("==========================================================================")
    async with AsyncSessionLocal() as db:
        # Load sample clean certificate
        orig_cert_id = "b4d835cd6e81412692317d3854a156f5"
        cert_res = await db.execute(select(Certificate).where(Certificate.id == orig_cert_id))
        cert = cert_res.scalar_one_or_none()
        assert cert is not None, f"Certificate {orig_cert_id} not found!"

        user_res = await db.execute(select(User).where(User.id == cert.owner_id))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {cert.owner_id} not found!"

        # Run trust score calculation
        print(f"Executing run_trust_score for certificate ID: {cert.id}...")
        api_post_res = await run_trust_score(cert.id, user=user, db=db)
        print(f"POST Response: score={api_post_res.score}, band={api_post_res.band}, coverage={api_post_res.coverage_percentage}%")

        # Test GET /trust-score endpoint
        print(f"Calling get_trust_score for certificate ID: {cert.id}...")
        api_get_res = await get_trust_score(cert.id, user=user, db=db)
        print(f"GET Response:  score={api_get_res.score}, band={api_get_res.band}, coverage={api_get_res.coverage_percentage}%")
        assert api_post_res.score == api_get_res.score
        assert api_get_res.components is not None
        assert len(api_get_res.components) == 8

        # Confirm database row in trust_scores table
        db_trust = (await db.execute(select(TrustScore).where(TrustScore.certificate_id == cert.id))).scalar_one()
        assert db_trust.score == api_get_res.score
        assert db_trust.breakdown is not None
        assert "coverage" in db_trust.breakdown
        assert "components" in db_trust.breakdown
        print("Database persistence confirmed in trust_scores table (score + breakdown JSON)!")

    print("\nALL MODULE 6 TRUST SCORE VERIFICATIONS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
