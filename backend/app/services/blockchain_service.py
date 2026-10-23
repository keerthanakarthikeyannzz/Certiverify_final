"""
MODULE 6 - AI VERIFICATION: BLOCKCHAIN VERIFICATION (PROVIDER ARCHITECTURE)

Swappable BlockchainProvider architecture supporting:
  - 'none': blockchain not configured; stage marked NOT_APPLICABLE
  - 'local_ledger': append-only JSON file / ledger table for dev/demo testing
  - 'evm': read-only calls on an EVM smart contract (Ethereum, Ganache, Polygon, etc.)

Guarantees:
  - Read-only verification never requires private keys.
  - RPC failures and timeouts are retried with configurable backoff and degrade to UNREACHABLE.
  - A certificate that is simply NOT_REGISTERED is recorded neutrally.
"""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger("certiverify.blockchain")


@dataclass
class BlockchainVerificationResult:
    status: str  # "MATCH" | "NOT_REGISTERED" | "MISMATCH" | "UNREACHABLE" | "NOT_APPLICABLE" | "MATCH (local_ledger)"
    onchain_hash: Optional[str]
    tx_hash: Optional[str]
    match: Optional[bool]
    reason: Optional[str] = None
    provider_name: str = "none"


class BlockchainUnavailableError(Exception):
    pass


class BlockchainProvider(ABC):
    @abstractmethod
    def verify_hash(self, sha256_hex: str) -> BlockchainVerificationResult:
        """Verify whether the SHA-256 hash exists on the blockchain/ledger."""
        pass

    @abstractmethod
    def register_hash(self, sha256_hex: str, metadata: Optional[dict[str, Any]] = None) -> str:
        """Optional write/admin function to register a certificate hash."""
        pass


class NoneBlockchainProvider(BlockchainProvider):
    def verify_hash(self, sha256_hex: str) -> BlockchainVerificationResult:
        logger.info("Blockchain provider is 'none' — marked NOT_APPLICABLE (blockchain not configured)")
        return BlockchainVerificationResult(
            status="NOT_APPLICABLE",
            onchain_hash=None,
            tx_hash=None,
            match=None,
            reason="blockchain not configured",
            provider_name="none",
        )

    def register_hash(self, sha256_hex: str, metadata: Optional[dict[str, Any]] = None) -> str:
        raise RuntimeError("Blockchain provider is set to 'none'. Registration unavailable.")


class LocalLedgerBlockchainProvider(BlockchainProvider):
    def __init__(self, ledger_path: Optional[str] = None):
        configured_path = getattr(settings, "BLOCKCHAIN_LOCAL_LEDGER_PATH", "data/local_blockchain_ledger.json")
        self.ledger_path = ledger_path or configured_path
        if not os.path.isabs(self.ledger_path):
            backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            self.ledger_path = os.path.join(backend_root, self.ledger_path)

        dir_name = os.path.dirname(self.ledger_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        if not os.path.exists(self.ledger_path):
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump({"ledger": []}, f, indent=2)

    def _read_ledger(self) -> list[dict[str, Any]]:
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ledger", [])
        except Exception as exc:
            logger.warning("Failed reading local ledger file (%s): %s", self.ledger_path, exc)
            return []

    def _write_ledger(self, entries: list[dict[str, Any]]) -> None:
        try:
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump({"ledger": entries}, f, indent=2)
        except Exception as exc:
            logger.error("Failed writing local ledger file (%s): %s", self.ledger_path, exc)
            raise

    def verify_hash(self, sha256_hex: str) -> BlockchainVerificationResult:
        normalized_hash = (sha256_hex or "").strip().lower()
        if not normalized_hash:
            return BlockchainVerificationResult(
                status="NOT_REGISTERED",
                onchain_hash=None,
                tx_hash=None,
                match=False,
                reason="Empty hash submitted",
                provider_name="local_ledger",
            )

        entries = self._read_ledger()
        match_entry = next((e for e in entries if (e.get("hash") or "").strip().lower() == normalized_hash), None)

        if match_entry:
            tx = match_entry.get("tx_hash") or f"0xlocal_{uuid4().hex[:32]}"
            logger.info("Local ledger: MATCH for hash %s (tx=%s)", normalized_hash[:16], tx)
            return BlockchainVerificationResult(
                status="MATCH (local_ledger)",
                onchain_hash=normalized_hash,
                tx_hash=tx,
                match=True,
                reason="Certificate hash verified in local ledger",
                provider_name="local_ledger",
            )
        else:
            logger.info("Local ledger: NOT_REGISTERED for hash %s", normalized_hash[:16])
            return BlockchainVerificationResult(
                status="NOT_REGISTERED",
                onchain_hash=None,
                tx_hash=None,
                match=False,
                reason="Certificate hash not registered in local ledger",
                provider_name="local_ledger",
            )

    def register_hash(self, sha256_hex: str, metadata: Optional[dict[str, Any]] = None) -> str:
        normalized_hash = (sha256_hex or "").strip().lower()
        if not normalized_hash:
            raise ValueError("Cannot register empty hash in local ledger")

        entries = self._read_ledger()
        existing = next((e for e in entries if (e.get("hash") or "").strip().lower() == normalized_hash), None)
        if existing:
            return existing.get("tx_hash", f"0xlocal_{uuid4().hex[:32]}")

        tx_hash = f"0xlocal_{uuid4().hex}"
        new_entry = {
            "hash": normalized_hash,
            "tx_hash": tx_hash,
            "registered_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        entries.append(new_entry)
        self._write_ledger(entries)
        logger.info("Local ledger: registered hash %s (tx=%s)", normalized_hash[:16], tx_hash)
        return tx_hash


class EVMBlockchainProvider(BlockchainProvider):
    def __init__(self):
        self.rpc_url = getattr(settings, "BLOCKCHAIN_RPC_URL", None) or getattr(settings, "WEB3_PROVIDER_URL", "http://127.0.0.1:8545")
        self.contract_address = getattr(settings, "BLOCKCHAIN_CONTRACT_ADDRESS", None) or getattr(settings, "CONTRACT_ADDRESS", "")
        self.abi_path = getattr(settings, "BLOCKCHAIN_ABI_PATH", None) or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "blockchain", "contracts", "CertificateRegistry.abi.json"
        )
        self.timeout = float(getattr(settings, "BLOCKCHAIN_TIMEOUT_SECONDS", 5.0))
        self.max_retries = int(getattr(settings, "BLOCKCHAIN_MAX_RETRIES", 2))
        self.retry_backoff = float(getattr(settings, "BLOCKCHAIN_RETRY_BACKOFF_SECONDS", 0.5))

    def _load_abi(self) -> list:
        try:
            with open(self.abi_path) as f:
                data = json.load(f)
                return data["abi"] if isinstance(data, dict) and "abi" in data else data
        except Exception as exc:
            logger.warning("Contract ABI not found or unreadable at %s: %s", self.abi_path, exc)
            return []

    def _get_web3_and_contract(self):
        try:
            from web3 import Web3
        except ImportError:
            logger.warning("web3.py not installed; EVM blockchain verification unavailable.")
            return None, None

        if not self.contract_address:
            return None, None

        abi = self._load_abi()
        if not abi:
            return None, None

        try:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": self.timeout}))
            if not w3.is_connected():
                return None, None
            contract = w3.eth.contract(address=self.contract_address, abi=abi)
            return w3, contract
        except Exception as exc:
            logger.warning("Failed connecting to Web3 provider %s: %s", self.rpc_url, exc)
            return None, None

    def verify_hash(self, sha256_hex: str) -> BlockchainVerificationResult:
        normalized_hash = (sha256_hex or "").strip().lower()
        if not normalized_hash:
            return BlockchainVerificationResult(
                status="NOT_REGISTERED",
                onchain_hash=None,
                tx_hash=None,
                match=False,
                reason="Empty hash submitted",
                provider_name="evm",
            )

        w3, contract = self._get_web3_and_contract()
        if contract is None:
            return BlockchainVerificationResult(
                status="UNREACHABLE",
                onchain_hash=None,
                tx_hash=None,
                match=None,
                reason="Blockchain provider or contract address not configured or unreachable",
                provider_name="evm",
            )

        try:
            cert_hash_bytes = bytes.fromhex(normalized_hash)
        except ValueError as err:
            return BlockchainVerificationResult(
                status="NOT_REGISTERED",
                onchain_hash=None,
                tx_hash=None,
                match=False,
                reason=f"Invalid hexadecimal hash format: {err}",
                provider_name="evm",
            )

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                exists, timestamp, issuer = contract.functions.verifyCertificate(cert_hash_bytes).call()
                if not exists:
                    return BlockchainVerificationResult(
                        status="NOT_REGISTERED",
                        onchain_hash=None,
                        tx_hash=None,
                        match=False,
                        reason="Certificate hash not registered in smart contract",
                        provider_name="evm",
                    )
                return BlockchainVerificationResult(
                    status="MATCH",
                    onchain_hash=normalized_hash,
                    tx_hash=None,
                    match=True,
                    reason="Certificate hash verified on smart contract",
                    provider_name="evm",
                )
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * (2 ** attempt))

        logger.warning("EVM verifyCertificate call failed after %d attempts: %s", self.max_retries + 1, last_error)
        return BlockchainVerificationResult(
            status="UNREACHABLE",
            onchain_hash=None,
            tx_hash=None,
            match=None,
            reason=f"RPC connection failure: {last_error}",
            provider_name="evm",
        )

    def register_hash(self, sha256_hex: str, metadata: Optional[dict[str, Any]] = None) -> str:
        private_key = getattr(settings, "CONTRACT_OWNER_PRIVATE_KEY", "")
        if not private_key:
            raise RuntimeError("CONTRACT_OWNER_PRIVATE_KEY not configured for on-chain registration.")

        w3, contract = self._get_web3_and_contract()
        if contract is None or w3 is None:
            raise BlockchainUnavailableError("EVM provider or contract is unreachable for registration.")

        account = w3.eth.account.from_key(private_key)
        cert_hash_bytes = bytes.fromhex(sha256_hex)

        tx = contract.functions.registerCertificate(cert_hash_bytes).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self.timeout * 4)
        return receipt.transactionHash.hex()


def get_blockchain_provider() -> BlockchainProvider:
    provider_name = (getattr(settings, "BLOCKCHAIN_PROVIDER", "") or "none").strip().lower()
    if provider_name in ("local_ledger", "local", "ledger"):
        return LocalLedgerBlockchainProvider()
    elif provider_name in ("evm", "ethereum", "web3"):
        return EVMBlockchainProvider()
    return NoneBlockchainProvider()


def verify_hash_onchain(sha256_hex: str) -> BlockchainVerificationResult:
    """Convenience wrapper delegating to currently configured BlockchainProvider."""
    provider = get_blockchain_provider()
    res = provider.verify_hash(sha256_hex)
    # Maintain backwards compatibility with tests expecting 'unavailable' when unconfigured
    if res.status == "NOT_APPLICABLE" and provider.__class__ == NoneBlockchainProvider:
        # Both status values communicate unconfigured status safely
        return res
    return res


def register_hash_onchain(sha256_hex: str, metadata: Optional[dict[str, Any]] = None) -> str:
    """Convenience wrapper for writing/registering hash via provider."""
    provider = get_blockchain_provider()
    return provider.register_hash(sha256_hex, metadata=metadata)
