"""
Cryptographic Utilities for CLI Security
Provides real signature verification for multisig operations
"""

import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from aitbc import ValidationError
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.validation import validate_address_strict

from eth_account import Account
from eth_utils import is_address, keccak, to_checksum_address

from .http_client import get_logger

logger = get_logger(__name__)


def create_signature_challenge(tx_data: dict, nonce: str) -> str:
    """
    Create a cryptographic challenge for transaction signing

    Args:
        tx_data: Transaction data to sign
        nonce: Unique nonce to prevent replay attacks

    Returns:
        Challenge string to be signed
    """
    # Create deterministic challenge from transaction data
    challenge_data = {
        "tx_id": tx_data.get("tx_id"),
        "to": tx_data.get("to"),
        "amount": tx_data.get("amount"),
        "nonce": nonce,
        "timestamp": tx_data.get("timestamp"),
    }

    # Sort keys for deterministic ordering
    challenge_str = json.dumps(challenge_data, sort_keys=True, separators=(",", ":"))
    challenge_hash = keccak(challenge_str.encode())

    return f"AITBC_MULTISIG_CHALLENGE:{challenge_hash.hex()}"


def verify_signature(challenge: str, signature: str, signer_address: str) -> bool:
    """
    Verify that a signature was created by the specified signer

    Args:
        challenge: Challenge string that was signed
        signature: Hex signature string
        signer_address: Expected signer address

    Returns:
        True if signature is valid
    """
    try:
        # Remove 0x prefix if present
        if signature.startswith("0x"):
            signature = signature[2:]

        # Convert to bytes
        signature_bytes = bytes.fromhex(signature)

        # Recover address from signature
        message_hash = keccak(challenge.encode())
        recovered_address = Account.recover_message(signable_hash=message_hash, signature=signature_bytes)

        # Compare with expected signer
        return to_checksum_address(recovered_address) == to_checksum_address(signer_address)

    except Exception:
        logger.warning("Signature verification failed", exc_info=True)
        return False


def sign_challenge(challenge: str, private_key: str) -> str:
    """
    Sign a challenge with a private key

    Args:
        challenge: Challenge string to sign
        private_key: Private key in hex format

    Returns:
        Signature as hex string
    """
    try:
        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]

        account = Account.from_key("0x" + private_key)
        message_hash = keccak(challenge.encode())
        signature = account.sign_message(message_hash)

        return "0x" + signature.signature.hex()  # type: ignore[no-any-return]

    except Exception as e:
        raise ValueError(f"Failed to sign challenge: {e}") from e


def generate_nonce() -> str:
    """Generate a secure nonce for transaction challenges"""
    return secrets.token_hex(16)


def validate_multisig_transaction(tx_data: dict) -> tuple[bool, str]:
    """
    Validate multisig transaction structure

    Args:
        tx_data: Transaction data to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["tx_id", "to", "amount", "timestamp", "nonce"]

    for field in required_fields:
        if field not in tx_data:
            return False, f"Missing required field: {field}"

    # Validate address format (canonical 0x-prefixed secp256k1/EVM only)
    to_address = tx_data["to"]
    try:
        validate_address_strict(to_address)
    except ValidationError as exc:
        return False, f"Invalid recipient address format: {exc}"

    # Validate amount
    try:
        amount = Decimal(str(tx_data["amount"]))
        if amount <= 0:
            return False, "Amount must be positive"
    except Exception:
        logger.warning("Invalid amount format for transaction: %s", tx_data.get("amount"), exc_info=True)
        return False, "Invalid amount format"

    return True, ""


# Multisig signing spans CLI invocations: one process creates the challenge, another
# verifies a signature against it. A dict on a module-level singleton cannot do that --
# each invocation is a fresh process, so the store was always empty by the time
# verify_and_add_signature ran, and every signature returned "Transaction not found or
# expired". Challenges are persisted instead, with a real expiry.
_CHALLENGE_TTL = timedelta(hours=1)
_DEFAULT_CHALLENGE_STORE = Path.home() / ".aitbc" / "multisig_challenges.json"


class MultisigSecurityManager:
    """Security manager for multisig operations.

    Challenges persist across CLI invocations in a 0600 JSON store and expire after
    ``_CHALLENGE_TTL``.
    """

    def __init__(self, store_path: Path | None = None):
        self.store_path = store_path or _DEFAULT_CHALLENGE_STORE

    @property
    def pending_challenges(self) -> dict[str, dict]:
        """Non-expired challenges, read from the store."""
        return self._load()

    def _load(self) -> dict[str, dict]:
        try:
            with open(self.store_path) as f:
                stored = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

        now = datetime.now(UTC)
        live: dict[str, dict] = {}
        for tx_id, entry in stored.items():
            created_raw = entry.get("created_at")
            if not created_raw:
                continue
            try:
                created = datetime.fromisoformat(created_raw)
            except ValueError:
                continue
            if now - created < _CHALLENGE_TTL:
                live[tx_id] = entry
        return live

    def _save(self, challenges: dict[str, dict]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        # Challenge payloads carry transaction data; create 0600 rather than chmod'ing
        # after, which would leave a readable window.
        fd = os.open(self.store_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(challenges, f, indent=2)

    def create_signing_request(self, tx_data: dict, multisig_wallet: str) -> dict[str, str]:
        """
        Create a signing request with cryptographic challenge

        Args:
            tx_data: Transaction data
            multisig_wallet: Multisig wallet identifier

        Returns:
            Signing request with challenge
        """
        # Validate transaction
        is_valid, error = validate_multisig_transaction(tx_data)
        if not is_valid:
            raise ValueError(f"Invalid transaction: {error}")

        # Generate nonce and challenge
        nonce = generate_nonce()
        challenge = create_signature_challenge(tx_data, nonce)

        # Store challenge for verification. created_at is a real timestamp: it was
        # secrets.token_hex(8), random bytes in a field named and consumed as a time, so
        # expiry could never be computed.
        challenges = self._load()
        challenges[tx_data["tx_id"]] = {
            "challenge": challenge,
            "tx_data": tx_data,
            "multisig_wallet": multisig_wallet,
            "nonce": nonce,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._save(challenges)

        return {
            "tx_id": tx_data["tx_id"],
            "challenge": challenge,
            "nonce": nonce,
            "signers_required": len(tx_data.get("required_signers", [])),
            "message": f"Please sign this challenge to authorize transaction {tx_data['tx_id']}",
        }

    def verify_and_add_signature(self, tx_id: str, signature: str, signer_address: str) -> tuple[bool, str]:
        """
        Verify signature and add to transaction

        Args:
            tx_id: Transaction ID
            signature: Signature to verify
            signer_address: Address of signer

        Returns:
            Tuple of (success, message)
        """
        challenges = self._load()
        if tx_id not in challenges:
            return False, "Transaction not found or expired"

        challenge_data = challenges[tx_id]
        challenge = challenge_data["challenge"]

        # Verify signature
        if not verify_signature(challenge, signature, signer_address):
            return False, f"Invalid signature for signer {signer_address}"

        # Check if signer is authorized (compare canonical addresses)
        tx_data = challenge_data["tx_data"]
        authorized_signers = tx_data.get("required_signers", [])
        canonical_signer = canonical_address(signer_address)

        if canonical_signer not in {canonical_address(addr) for addr in authorized_signers}:
            return False, f"Signer {signer_address} is not authorized"

        return True, "Signature verified successfully"

    def cleanup_challenge(self, tx_id: str):
        """Clean up challenge after transaction completion"""
        challenges = self._load()
        if tx_id in challenges:
            del challenges[tx_id]
            self._save(challenges)


def _canonical_address(address: str) -> str:
    """
    Return the canonical 0x address unchanged.

    AITBC now uses Ethereum-style 0x checksum addresses natively.
    Legacy non-0x prefixes are rejected.

    Args:
        address: AITBC address in 0x format (e.g., "0xc10f0e4f...")

    Returns:
        The same 0x address.

    Raises:
        ValueError: If the address is empty, legacy-prefixed, or not a valid 0x address.
    """
    if not address:
        raise ValueError("Address cannot be empty")

    if not address.startswith("0x"):
        raise ValueError(f"Legacy address format is not supported: {address}")

    try:
        if not is_address(address):
            raise ValueError(f"Invalid 0x address: {address}")
    except ImportError:
        import re

        if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
            raise ValueError(f"Invalid 0x address: {address}") from None

    return address


def bech32_to_hex(address: str) -> str:
    """Backward-compatible alias for :func:`_canonical_address`."""
    return _canonical_address(address)


def hex_to_bech32(address: str) -> str:
    """Backward-compatible alias for :func:`_canonical_address`."""
    return _canonical_address(address)


# Global security manager instance
multisig_security = MultisigSecurityManager()
