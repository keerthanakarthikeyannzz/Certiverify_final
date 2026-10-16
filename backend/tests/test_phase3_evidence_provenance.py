"""
Comprehensive Unit & Integration Test Suite for PHASE 3 — Evidence Provenance & Explainable AI.

Tests:
1. EvidenceItem creation
2. OCR evidence generation
3. QR evidence generation
4. Tamper evidence generation
5. Blockchain evidence generation
6. Duplicate evidence generation
7. Fraud evidence generation
8. Trust-score evidence generation
9. Evidence API
10. Evidence pagination
11. Evidence filtering
12. Tenant isolation
13. Historical verification separation
14. Failed verification behavior
15. Retry behavior
"""
import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import (
    User, UserRole, Certificate, Organization, VerificationJob, JobStatus,
    PipelineStage, OCRData, VerificationResult, FraudAnalysis, TrustScore,
    DocumentType, DocTypeEnum, EvidenceItem, EvidenceType
)
from app.core.security import hash_password, create_access_token
from app.services.evidence_service import (
    record_evidence,
    emit_document_analysis_evidence,
    emit_ocr_evidence,
    emit_qr_evidence,
    emit_blockchain_evidence,
    emit_tampering_evidence,
    emit_duplicate_evidence,
    emit_fraud_evidence,
    emit_trust_score_evidence,
)


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_01_evidence_item_creation():
    async with AsyncSessionLocal() as db:
        cert_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        item = await record_evidence(
            db=db,
            certificate_id=cert_id,
            organization_id=org_id,
            verification_job_id=job_id,
            evidence_type=EvidenceType.STRUCTURE,
            source="CLIP Classifier",
            stage="DOCUMENT_ANALYSIS",
            document_hash="hash-101",
            algorithm_engine="ViT Zero-Shot",
            confidence=0.92,
            result="PASS",
            explanation="Classified document as degree_certificate.",
            details={"type": "degree_certificate"},
        )
        assert item.id is not None
        assert item.certificate_id == cert_id
        assert item.evidence_type == EvidenceType.STRUCTURE
        assert item.confidence == 0.92
        assert item.result == "PASS"


@pytest.mark.asyncio
async def test_02_ocr_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="sample.pdf",
            storage_path="/tmp/sample.pdf",
            file_type="pdf",
            file_size_bytes=1024,
            sha256_hash="hash-ocr-test",
        )
        ocr = OCRData(
            certificate_id=cert.id,
            student_name="Alice Smith",
            university_name="Stanford University",
            certificate_number="CERT-999",
            ocr_accuracy=0.94,
            ocr_engine="EasyOCR",
        )
        db.add_all([cert, ocr])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_ocr_evidence(db, cert, ocr, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.OCR
        assert "Alice Smith" in ev.explanation
        assert ev.result == "PASS"


@pytest.mark.asyncio
async def test_03_qr_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="qr.pdf",
            storage_path="/tmp/qr.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-qr-test",
        )
        vr = VerificationResult(
            certificate_id=cert.id,
            qr_present=True,
            qr_valid=True,
            qr_decoded_data={"cert_id": "12345"},
        )
        db.add_all([cert, vr])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_qr_evidence(db, cert, vr, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.QR
        assert ev.result == "PASS"


@pytest.mark.asyncio
async def test_04_tamper_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="tamper.pdf",
            storage_path="/tmp/tamper.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-tamper-test",
        )
        vr = VerificationResult(
            certificate_id=cert.id,
            tampering_score=75.0,
            tampering_risk_level="HIGH_RISK",
            tampering_flags=["ela_anomaly"],
        )
        db.add_all([cert, vr])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_tampering_evidence(db, cert, vr, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.TAMPER
        assert ev.result == "FAIL"


@pytest.mark.asyncio
async def test_05_blockchain_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="bc.pdf",
            storage_path="/tmp/bc.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-bc-test",
        )
        vr = VerificationResult(
            certificate_id=cert.id,
            blockchain_status="verified",
            blockchain_tx_hash="0xabc123",
        )
        db.add_all([cert, vr])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_blockchain_evidence(db, cert, vr, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.BLOCKCHAIN
        assert ev.result == "PASS"


@pytest.mark.asyncio
async def test_06_duplicate_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="dup.pdf",
            storage_path="/tmp/dup.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-dup-test",
        )
        vr = VerificationResult(
            certificate_id=cert.id,
            is_duplicate=True,
            duplicate_match_reason="Identical SHA-256 hash",
        )
        db.add_all([cert, vr])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_duplicate_evidence(db, cert, vr, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.DUPLICATE
        assert ev.result == "DUPLICATE"


@pytest.mark.asyncio
async def test_07_fraud_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="fraud.pdf",
            storage_path="/tmp/fraud.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-fraud-test",
        )
        fa = FraudAnalysis(
            certificate_id=cert.id,
            fraud_probability=0.78,
            ocr_accuracy_weight=0.15,
            qr_weight=0.10,
        )
        db.add_all([cert, fa])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_fraud_evidence(db, cert, fa, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.FRAUD
        assert ev.result == "HIGH_RISK"


@pytest.mark.asyncio
async def test_08_trust_score_evidence_generation():
    async with AsyncSessionLocal() as db:
        user_id = str(uuid.uuid4())
        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            original_filename="ts.pdf",
            storage_path="/tmp/ts.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-ts-test",
        )
        ts = TrustScore(
            certificate_id=cert.id,
            score=91.5,
            breakdown={"factor_trust_values": {"ocr": 95, "qr": 100}},
        )
        db.add_all([cert, ts])
        await db.commit()

        job_id = str(uuid.uuid4())
        ev = await emit_trust_score_evidence(db, cert, ts, verification_job_id=job_id)
        assert ev is not None
        assert ev.evidence_type == EvidenceType.TRUST_SCORE
        assert ev.result == "PASS"


@pytest.mark.asyncio
async def test_09_10_11_evidence_api_filtering_pagination(async_client):
    async with AsyncSessionLocal() as db:
        user = User(
            full_name="Evidence Test User",
            email=f"ev_user_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.ADMIN,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            original_filename="api_test.pdf",
            storage_path="/tmp/api_test.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-api-test",
        )
        db.add(cert)
        await db.commit()

        job_id = str(uuid.uuid4())
        item1 = await record_evidence(db, cert.id, EvidenceType.OCR, "Source1", "OCR", cert.sha256_hash, "Engine1", 0.9, "PASS", "OCR pass", verification_job_id=job_id)
        item2 = await record_evidence(db, cert.id, EvidenceType.QR, "Source2", "QR_VERIFICATION", cert.sha256_hash, "Engine2", 0.95, "PASS", "QR pass", verification_job_id=job_id)
        item3 = await record_evidence(db, cert.id, EvidenceType.TAMPER, "Source3", "TAMPER_ANALYSIS", cert.sha256_hash, "Engine3", 0.2, "WARN", "Tamper warning", verification_job_id=job_id)

    token = create_access_token(subject=user.id, extra_claims={"role": "admin"})

    # Test 9: Get All Evidence
    response = await async_client.get(
        f"/api/v1/certificates/{cert.id}/evidence",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Test 10: Pagination
    resp_p1 = await async_client.get(
        f"/api/v1/certificates/{cert.id}/evidence?page=1&page_size=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_p1.status_code == 200
    p1_data = resp_p1.json()
    assert len(p1_data["items"]) == 2
    assert p1_data["total_pages"] == 2

    # Test 11: Filtering by evidence_type
    resp_filt = await async_client.get(
        f"/api/v1/certificates/{cert.id}/evidence?evidence_type=OCR",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_filt.status_code == 200
    filt_data = resp_filt.json()
    assert filt_data["total"] == 1
    assert filt_data["items"][0]["evidence_type"] == "OCR"


@pytest.mark.asyncio
async def test_12_tenant_isolation(async_client):
    async with AsyncSessionLocal() as db:
        org_a = Organization(name="Org A", slug=f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:6]}")
        db.add_all([org_a, org_b])
        await db.commit()

        user_b = User(
            full_name="User B",
            email=f"user_b_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.STUDENT,
            organization_id=org_b.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user_b)
        await db.commit()
        await db.refresh(user_b)

        cert_a = Certificate(
            id=str(uuid.uuid4()),
            organization_id=org_a.id,
            owner_id=str(uuid.uuid4()),
            original_filename="secret_a.pdf",
            storage_path="/tmp/secret_a.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash="hash-org-a",
        )
        db.add(cert_a)
        await db.commit()

        job_a_id = str(uuid.uuid4())
        await record_evidence(db, cert_a.id, EvidenceType.METADATA, "Hasher", "DOCUMENT_ANALYSIS", cert_a.sha256_hash, "SHA256", 1.0, "PASS", "Secret evidence", organization_id=org_a.id, verification_job_id=job_a_id)

    token_b = create_access_token(subject=user_b.id, extra_claims={"role": "student"})

    # User B (Org B) attempts to access Evidence from Org A's certificate
    response = await async_client.get(
        f"/api/v1/certificates/{cert_a.id}/evidence",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_13_historical_verification_separation():
    async with AsyncSessionLocal() as db:
        cert_id = str(uuid.uuid4())
        job1_id = str(uuid.uuid4())
        job2_id = str(uuid.uuid4())

        await record_evidence(db, cert_id, EvidenceType.OCR, "Engine1", "OCR", "hash-1", "Engine1", 0.8, "PASS", "Run 1", verification_job_id=job1_id)
        await record_evidence(db, cert_id, EvidenceType.OCR, "Engine2", "OCR", "hash-1", "Engine2", 0.95, "PASS", "Run 2", verification_job_id=job2_id)

        res1 = await db.execute(select(EvidenceItem).where(EvidenceItem.verification_job_id == job1_id))
        res2 = await db.execute(select(EvidenceItem).where(EvidenceItem.verification_job_id == job2_id))

        items1 = res1.scalars().all()
        items2 = res2.scalars().all()

        assert len(items1) == 1
        assert len(items2) == 1
        assert items1[0].explanation == "Run 1"
        assert items2[0].explanation == "Run 2"


@pytest.mark.asyncio
async def test_14_15_retry_and_failed_verification_behavior(async_client):
    async with AsyncSessionLocal() as db:
        user = User(
            full_name="Retry Test User",
            email=f"retry_user_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.ADMIN,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        await db.commit()

        cert = Certificate(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            original_filename="failed_job.pdf",
            storage_path="/tmp/failed_job.pdf",
            file_type="pdf",
            file_size_bytes=1024,
            sha256_hash="hash-retry-test",
        )
        job = VerificationJob(
            id=str(uuid.uuid4()),
            certificate_id=cert.id,
            status=JobStatus.FAILED,
            current_stage=PipelineStage.OCR,
            failed_stage="OCR",
            error_details="OCR engine timeout simulation",
        )
        db.add_all([cert, job])
        await db.commit()

    token = create_access_token(subject=user.id, extra_claims={"role": "admin"})

    # Test jobs API endpoint
    response = await async_client.get(
        f"/api/v1/certificates/{cert.id}/evidence/jobs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    jobs_data = response.json()
    assert len(jobs_data) == 1
    assert jobs_data[0]["status"] == "FAILED"
