"""
Comprehensive tests for Module 1 (QR Verification) and Module 2 (Blockchain Verification).
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.services.qr_verification import (
    verify_qr,
    classify_and_parse_payload,
    evaluate_domain_trust,
    perform_live_check,
)
from app.services.blockchain_service import (
    get_blockchain_provider,
    NoneBlockchainProvider,
    LocalLedgerBlockchainProvider,
    EVMBlockchainProvider,
    verify_hash_onchain,
    register_hash_onchain,
)


# ============================================================================
# MODULE 1 TESTS: QR VERIFICATION
# ============================================================================

def test_qr_not_present_marks_not_applicable():
    result = verify_qr(None)
    assert result.present is False
    assert result.valid is None
    assert result.status == "not_applicable"
    assert "No QR code detected" in result.reason
    assert result.cross_validation_status == "NOT_APPLICABLE"


def test_classify_and_parse_url():
    url = "https://certverify.tndge.org/ceti-verify/11bf553a59666b9a8ca524f7bf40f262/7256086/ba34736f1ed890f5558bd2b79fb8eecf?cert_id=7256086"
    classified = classify_and_parse_payload(url)
    assert classified["type"] == "URL"
    assert classified["host"] == "certverify.tndge.org"
    assert classified["scheme"] == "https"
    assert "ceti-verify" in classified["path_segments"]
    assert "7256086" in classified["extracted_ids"]
    assert "11bf553a59666b9a8ca524f7bf40f262" in classified["extracted_ids"]
    assert "ba34736f1ed890f5558bd2b79fb8eecf" in classified["extracted_ids"]


def test_classify_and_parse_json():
    raw_json = json.dumps({
        "certificate_id": "CERT-9988",
        "student_name": "Alice Smith",
        "register_number": "REG-12345",
        "expiry": "2035-12-31"
    })
    classified = classify_and_parse_payload(raw_json)
    assert classified["type"] == "JSON"
    assert "CERT-9988" in classified["extracted_ids"]
    assert "REG-12345" in classified["extracted_ids"]


def test_classify_and_parse_token():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token123456"
    classified = classify_and_parse_payload(token)
    assert classified["type"] == "token"
    assert classified["token"] == token
    assert token in classified["extracted_ids"]


def test_classify_and_parse_unknown():
    garbage = "hello world this is just random text with spaces and words"
    classified = classify_and_parse_payload(garbage)
    assert classified["type"] == "unknown"


def test_domain_trust_policy():
    with patch.object(settings, "QR_TRUSTED_DOMAINS", "university.edu,tndge.org"):
        status1, ok1, _ = evaluate_domain_trust("certverify.tndge.org")
        assert status1 == "trusted"
        assert ok1 is True

        status2, ok2, warn2 = evaluate_domain_trust("phishing-fake.com")
        assert status2 == "untrusted"
        assert ok2 is False
        assert "not in configured trusted domain allowlist" in warn2

    with patch.object(settings, "QR_TRUSTED_DOMAINS", ""):
        status3, ok3, _ = evaluate_domain_trust("anydomain.com")
        assert status3 == "unknown"
        assert ok3 is True


@pytest.mark.asyncio
async def test_live_check_captcha_handling():
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "<html><body>Attention Required! Cloudflare Turnstile CAPTCHA challenge</body></html>"

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        live_meta, warning = await perform_live_check("https://portal.example.edu/verify/123")
        assert live_meta["status"] == "blocked_or_captcha"
        assert warning is not None
        assert "CAPTCHA" in warning


@pytest.mark.asyncio
async def test_live_check_network_error_resilience():
    with patch("httpx.AsyncClient.get", side_effect=ConnectionError("DNS resolution failed")):
        live_meta, warning = await perform_live_check("https://unreachable-host.example.edu/test")
        assert live_meta["status"] == "network_error"
        assert warning is not None
        assert "unreachable" in warning.lower()


# ============================================================================
# MODULE 2 TESTS: BLOCKCHAIN VERIFICATION
# ============================================================================

def test_blockchain_provider_none():
    with patch.object(settings, "BLOCKCHAIN_PROVIDER", "none"):
        provider = get_blockchain_provider()
        assert isinstance(provider, NoneBlockchainProvider)
        res = provider.verify_hash("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        assert res.status == "NOT_APPLICABLE"
        assert res.reason == "blockchain not configured"
        assert res.match is None


def test_blockchain_provider_local_ledger(tmp_path):
    test_ledger = str(tmp_path / "test_ledger.json")
    with patch.object(settings, "BLOCKCHAIN_PROVIDER", "local_ledger"), \
         patch.object(settings, "BLOCKCHAIN_LOCAL_LEDGER_PATH", test_ledger):

        provider = get_blockchain_provider()
        assert isinstance(provider, LocalLedgerBlockchainProvider)

        test_hash = "a" * 64
        # 1. Verify before registration -> NOT_REGISTERED
        unreg_res = provider.verify_hash(test_hash)
        assert unreg_res.status == "NOT_REGISTERED"
        assert unreg_res.match is False

        # 2. Register hash -> returns tx hash
        tx_hash = provider.register_hash(test_hash, metadata={"cert": "123"})
        assert tx_hash.startswith("0xlocal_")

        # 3. Verify after registration -> MATCH (local_ledger)
        match_res = provider.verify_hash(test_hash)
        assert "MATCH" in match_res.status
        assert match_res.match is True
        assert match_res.tx_hash == tx_hash
        assert match_res.onchain_hash == test_hash

        # 4. Verify modified hash -> NOT_REGISTERED
        diff_hash = "b" * 64
        diff_res = provider.verify_hash(diff_hash)
        assert diff_res.status == "NOT_REGISTERED"
        assert diff_res.match is False
