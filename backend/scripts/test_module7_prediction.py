"""
Verification and Demonstration Script for MODULE 7: Final Prediction Stage (prediction)

Evaluates and Displays:
1. Verified-looking document (Full positive evidence, high trust score, low fraud probability, high coverage)
2. Partial-evidence document (< 50% coverage, demonstrating the INCONCLUSIVE verdict gate for verification safety)
3. Suspicious / Forged document (Severe tampering, duplicate collision, invalid QR, hard override forcing FAKE)

Also tests Live Database Execution:
- POST /{certificate_id}/predict (populates final_predictions, verification_jobs, audit_logs)
- GET /{certificate_id}/prediction (returns stored verdict, explanation, action, evidence, and reasons)
"""
import asyncio
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Certificate, User, FinalPrediction, VerificationJob, AuditLog
from app.services.final_prediction import PredictionInputs, predict
from app.api.prediction import run_prediction, get_prediction
from sqlalchemy import select


def print_verdict_card(title: str, result):
    print("\n" + "=" * 95)
    print(f"DOCUMENT CASE: {title}")
    print("=" * 95)
    print(f"FINAL VERDICT LABEL:     {result.label.upper()}")
    print(f"CONFIDENCE SCORE:        {result.confidence * 100:.1f}%")
    print(f"TRUST SCORE:             {result.trust_score:.2f} / 100")
    print(f"AI FRAUD PROBABILITY:    {result.fraud_probability * 100:.1f}%")
    print(f"EVIDENCE COVERAGE:       {result.coverage * 100:.1f}%")
    print(f"RECOMMENDED ACTION:      {result.recommended_action}")

    print("\nPLAIN LANGUAGE EXPLANATION:")
    print("-" * 95)
    print(result.explanation)
    print("-" * 95)

    print("\nEVALUATED CHECKS BREAKDOWN:")
    print(f"  [✓] Verified Positive Evidence ({len(result.passed_checks)}):")
    for p in result.passed_checks:
        print(f"      • {p}")
    print(f"  [✗] Identified Risk Signals & Failures ({len(result.failed_checks)}):")
    for f in result.failed_checks:
        print(f"      • {f}")
    print(f"  [○] Checks Excluded / Not Evaluated ({len(result.not_evaluated_checks)}):")
    for n in result.not_evaluated_checks:
        print(f"      • {n}")
    print("-" * 95)


async def main():
    await init_db()

    print("\n" + "#" * 95)
    print("MODULE 7: FINAL PREDICTION STAGE TEST & DEMONSTRATION")
    print("#" * 95)

    # =========================================================================
    # CASE 1: VERIFIED-LOOKING DOCUMENT
    # =========================================================================
    verified_inputs = PredictionInputs(
        trust_score=94.5,
        coverage=1.0,
        checks_evaluated=8,
        checks_total=8,
        fraud_probability=0.03,
        ocr_accuracy=0.98,
        doc_classification_confidence=0.99,
        field_extraction_completeness=1.0,
        comparison_consistency_pct=98.5,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        blockchain_match=True,
        tampering_score=4.2,
        tampering_status="analyzed",
        tampering_risk_level="LOW",
        is_duplicate=False,
        image_quality_score=94.0,
    )
    verified_result = predict(verified_inputs)
    print_verdict_card("1. VERIFIED-LOOKING DOCUMENT (FULL EVIDENCE)", verified_result)

    assert verified_result.label == "genuine"
    assert verified_result.confidence >= 0.85
    assert len(verified_result.passed_checks) >= 6
    assert len(verified_result.failed_checks) == 0

    # =========================================================================
    # CASE 2: PARTIAL-EVIDENCE DOCUMENT (LOW COVERAGE < 50% -> INCONCLUSIVE)
    # =========================================================================
    partial_inputs = PredictionInputs(
        trust_score=88.0,
        coverage=0.375,  # 3 of 8 checks evaluated (< 50% minimum coverage gate)
        checks_evaluated=3,
        checks_total=8,
        fraud_probability=0.08,
        ocr_accuracy=0.95,
        field_extraction_completeness=0.90,
        is_duplicate=False,
        # QR, Blockchain, Tampering, Comparison, Image Quality were unrun
        qr_present=False,
        blockchain_status="unavailable",
        tampering_score=None,
        tampering_status="unavailable",
    )
    partial_result = predict(partial_inputs)
    print_verdict_card("2. PARTIAL-EVIDENCE DOCUMENT (3 OF 8 CHECKS -> INCONCLUSIVE GATE)", partial_result)

    assert partial_result.label == "inconclusive"
    assert "inconclusive" in partial_result.recommended_action.lower()
    assert len(partial_result.not_evaluated_checks) >= 4

    # =========================================================================
    # CASE 3: SUSPICIOUS / FORGED DOCUMENT (CRITICAL ANOMALIES & HARD OVERRIDES)
    # =========================================================================
    suspicious_inputs = PredictionInputs(
        trust_score=14.0,
        coverage=0.875,  # 7 of 8 checks
        checks_evaluated=7,
        checks_total=8,
        fraud_probability=0.88,
        ocr_accuracy=0.62,
        comparison_consistency_pct=35.0,
        qr_present=True,
        qr_valid=False,
        qr_warning="Cryptographic signature mismatch",
        blockchain_status="mismatch",
        blockchain_match=False,
        tampering_score=72.5,  # Severe tampering
        tampering_status="analyzed",
        tampering_risk_level="HIGH_RISK",
        is_duplicate=True,  # Duplicate collision
        duplicate_same_owner=False,
        duplicate_status="duplicate_found",
        duplicate_detail={"same_owner": False, "owner_distinction": "DIFFERENT_OWNER_DUPLICATE"},
        image_quality_score=42.0,
    )
    suspicious_result = predict(suspicious_inputs)
    print_verdict_card("3. SUSPICIOUS / FORGED DOCUMENT (COLLISION & TAMPERING)", suspicious_result)

    assert suspicious_result.label == "fake"
    assert suspicious_result.confidence >= 0.90
    assert len(suspicious_result.failed_checks) >= 3

    # =========================================================================
    # CASE 4: LIVE DATABASE PERSISTENCE & API ROUTE VERIFICATION
    # =========================================================================
    print("\n" + "=" * 95)
    print("4. LIVE DATABASE & GET /prediction ENDPOINT VERIFICATION")
    print("=" * 95)
    async with AsyncSessionLocal() as db:
        orig_cert_id = "b4d835cd6e81412692317d3854a156f5"
        cert_res = await db.execute(select(Certificate).where(Certificate.id == orig_cert_id))
        cert = cert_res.scalar_one_or_none()
        assert cert is not None, f"Certificate {orig_cert_id} not found!"

        user_res = await db.execute(select(User).where(User.id == cert.owner_id))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {cert.owner_id} not found!"

        # 1. Execute run_prediction (POST /{certificate_id}/predict)
        print(f"Executing run_prediction for certificate ID: {cert.id}...")
        api_post_res = await run_prediction(cert.id, user=user, db=db)
        print(f"POST Response: label={api_post_res.label}, confidence={api_post_res.confidence_score * 100:.1f}%")
        print(f"Action:        {api_post_res.recommended_action}")
        print(f"Explanation:   {api_post_res.explanation[:110]}...")

        # 2. Test GET /{certificate_id}/prediction endpoint
        print(f"\nCalling get_prediction for certificate ID: {cert.id}...")
        api_get_res = await get_prediction(cert.id, user=user, db=db)
        print(f"GET Response:  label={api_get_res.label}, confidence={api_get_res.confidence_score * 100:.1f}%")
        print(f"Advisory:      {api_get_res.decision_support_note}")

        assert api_post_res.label == api_get_res.label
        assert api_post_res.confidence_score == api_get_res.confidence_score
        assert api_get_res.evidence is not None
        assert api_get_res.reasons is not None
        assert len(api_get_res.reasons) > 0
        assert api_get_res.decision_support_note is not None

        # 3. Confirm database row in final_predictions table
        db_pred = (await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert.id))).scalar_one()
        assert db_pred.label.value == api_get_res.label
        assert db_pred.confidence_score == api_get_res.confidence_score
        assert db_pred.explanation is not None
        assert db_pred.recommended_action is not None
        print("✓ Verified final_predictions database row successfully!")

        # 4. Confirm verification_jobs stage state
        db_job = (await db.execute(select(VerificationJob).where(VerificationJob.certificate_id == cert.id).order_by(VerificationJob.id.desc()))).scalars().first()
        if db_job:
            assert "prediction" in db_job.stage_states
            assert db_job.stage_states["prediction"]["status"] == "COMPLETED"
            assert db_job.progress_percentage == 100
            print("✓ Verified verification_jobs stage_states (prediction=COMPLETED, progress=100%)!")

        # 5. Confirm audit_logs entry
        audit_res = await db.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == cert.id, AuditLog.action == "verification:final_prediction_completed")
            .order_by(AuditLog.id.desc())
        )
        audit_entry = audit_res.scalars().first()
        assert audit_entry is not None
        assert audit_entry.metadata_json["label"] == api_get_res.label
        print("✓ Verified audit_logs entry (action='verification:final_prediction_completed')!")

    print("\n" + "=" * 95)
    print("ALL MODULE 7 FINAL PREDICTION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 95 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
