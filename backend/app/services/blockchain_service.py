"""
MODULE 6 - AI VERIFICATION: BLOCKCHAIN VERIFICATION

Never stores the certificate itself on-chain — only its SHA-256 hash
(already computed at upload time, Certificate.sha256_hash). Verification is
a free `eth_call` (no gas); registration (done by a university/issuer, not
by this student-facing verification flow) costs gas and requires
CONTRACT_OWNER_PRIVATE_KEY to sign.

Degrades gracefully: if Ganache/the contract isn't reachable or configured,
returns status="unavailable" rather than crashing the whole verification
pipeline — Module 7's fraud scoring treats "unavailable" as neutral, not
as a red flag, since it reflects infra state, not the certificate's
authenticity.
"""
import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger("certiverify.blockchain")

_ABI_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "blockchain", "contracts", "CertificateRegistry.abi.json"
)


@dataclass
class BlockchainVerificationResult:
    status: str  # "verified" | "not_found" | "mismatch" | "unavailable"
    onchain_hash: str | None
    tx_hash: str | None
    match: bool | None


class BlockchainUnavailableError(Exception):
    pass


@lru_cache(maxsize=1)
def _load_abi() -> list:
    try:
        with open(_ABI_PATH) as f:
            return json.load(f)["abi"]
    except FileNotFoundError:
        logger.warning(f"Contract ABI not found at {_ABI_PATH}; run blockchain/scripts/deploy.py first.")
        return []


@lru_cache(maxsize=1)
def _get_web3():
    try:
        from web3 import Web3
    except ImportError:
        logger.warning("web3.py not installed; blockchain verification unavailable.")
        return None

    w3 = Web3(Web3.HTTPProvider(settings.WEB3_PROVIDER_URL, request_kwargs={"timeout": 5}))
    try:
        if not w3.is_connected():
            return None
    except Exception as e:
        logger.warning(f"Could not reach Web3 provider {settings.WEB3_PROVIDER_URL}: {e}")
        return None
    return w3


def _get_contract():
    w3 = _get_web3()
    abi = _load_abi()
    if w3 is None or not abi or not settings.CONTRACT_ADDRESS:
        return None, None
    contract = w3.eth.contract(address=settings.CONTRACT_ADDRESS, abi=abi)
    return w3, contract


def verify_hash_onchain(sha256_hex: str) -> BlockchainVerificationResult:
    """Free view call — checks whether this hash was ever registered on-chain."""
    w3, contract = _get_contract()
    if contract is None:
        return BlockchainVerificationResult(status="unavailable", onchain_hash=None, tx_hash=None, match=None)

    try:
        cert_hash_bytes = bytes.fromhex(sha256_hex)
        exists, timestamp, issuer = contract.functions.verifyCertificate(cert_hash_bytes).call()
    except Exception as e:
        logger.warning(f"Blockchain verifyCertificate call failed: {e}")
        return BlockchainVerificationResult(status="unavailable", onchain_hash=None, tx_hash=None, match=None)

    if not exists:
        return BlockchainVerificationResult(
            status="not_found", onchain_hash=None, tx_hash=None, match=False
        )

    return BlockchainVerificationResult(
        status="verified", onchain_hash=sha256_hex, tx_hash=None, match=True
    )


def register_hash_onchain(sha256_hex: str) -> str:
    """
    Registers a certificate hash on-chain. Intended for use by an authorized
    issuer (university) — NOT called during ordinary student-facing
    verification, which only ever reads the chain. Requires
    CONTRACT_OWNER_PRIVATE_KEY to be configured.
    """
    w3, contract = _get_contract()
    if contract is None:
        raise BlockchainUnavailableError("Blockchain provider or contract is not configured/reachable.")
    if not settings.CONTRACT_OWNER_PRIVATE_KEY:
        raise BlockchainUnavailableError("CONTRACT_OWNER_PRIVATE_KEY is not configured for signing.")

    account = w3.eth.account.from_key(settings.CONTRACT_OWNER_PRIVATE_KEY)
    cert_hash_bytes = bytes.fromhex(sha256_hex)

    tx = contract.functions.registerCertificate(cert_hash_bytes).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 200_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.transactionHash.hex()
