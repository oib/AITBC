"""
Utility functions for blockchain RPC endpoints.
"""

import json
from typing import Any

from fastapi import HTTPException

from ..config import settings
from ..logger import get_logger

_logger = get_logger(__name__)

_poa_proposers: dict[str, Any] = {}


def verify_transaction_signature(tx_data: dict[str, Any], signature: str, sender: str) -> bool:
    """Verify that a transaction was signed by the claimed sender.

    Uses Ethereum-style signature recovery (secp256k1) to recover the
    signer's address from the signature and compare it to the sender field.

    The signed message is the keccak256 hash of the canonical JSON encoding
    of the transaction fields (excluding the signature field itself).
    """
    if not signature or not sender:
        return False

    # Build the message that was signed: canonical JSON of tx fields without signature
    tx_without_sig = {k: v for k, v in tx_data.items() if k != "signature"}
    message = json.dumps(tx_without_sig, sort_keys=True, separators=(",", ":")).encode()

    try:
        from eth_keys import keys
        from eth_utils import keccak

        msg_hash = keccak(message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        if len(sig_bytes) != 65:
            _logger.warning("Invalid signature length: %d bytes", len(sig_bytes))
            return False

        sig = keys.Signature(sig_bytes)
        pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
        recovered_address = pub_key.to_checksum_address()
        return recovered_address.lower() == sender.lower()
    except Exception as e:
        _logger.warning("Signature verification failed: %s", e)
        return False


def verify_request_signature(sender: str, signature: str, message_data: dict[str, Any]) -> bool:
    """Verify a generic request signature (for bridge, staking, etc.).

    The signed message is the keccak256 hash of the canonical JSON encoding
    of the provided message_data dict.
    """
    if not signature or not sender:
        return False

    message = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode()

    try:
        from eth_keys import keys
        from eth_utils import keccak

        msg_hash = keccak(message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        if len(sig_bytes) != 65:
            _logger.warning("Invalid signature length: %d bytes", len(sig_bytes))
            return False

        sig = keys.Signature(sig_bytes)
        pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
        recovered_address = pub_key.to_checksum_address()
        return recovered_address.lower() == sender.lower()
    except Exception as e:
        _logger.warning("Request signature verification failed: %s", e)
        return False


def set_poa_proposer(proposer: Any, chain_id: str | None = None) -> None:
    """Set the global PoA proposer instance"""
    if chain_id is None:
        chain_id = getattr(getattr(proposer, "_config", None), "chain_id", None) or get_chain_id(None)
    _poa_proposers[chain_id] = proposer


def get_poa_proposer(chain_id: str | None = None) -> Any:
    """Get the global PoA proposer instance"""
    chain_id = get_chain_id(chain_id)
    return _poa_proposers.get(chain_id)


def get_chain_id(chain_id: str | None = None) -> str:
    """Get chain_id from parameter or use default from settings"""
    if chain_id is None:
        return settings.chain_id or "ait-mainnet"
    return chain_id


def validate_chain_id(chain_id: str) -> bool:
    """Validate that chain_id is in supported_chains list"""
    supported_chains = [c.strip() for c in settings.supported_chains.split(",")]
    return chain_id in supported_chains


def get_supported_chains() -> list[str]:
    """Get list of supported chain IDs"""
    chains = [chain.strip() for chain in settings.supported_chains.split(",") if chain.strip()]
    if not chains and settings.chain_id:
        return [settings.chain_id]
    return chains


def get_chain_db(chain_id: str | None = None) -> Any:
    """Get chain-specific database engine"""
    from ..database import get_engine

    resolved_chain_id = get_chain_id(chain_id)
    if not validate_chain_id(resolved_chain_id):
        raise HTTPException(status_code=400, detail=f"Chain {resolved_chain_id} not in supported_chains")
    return get_engine(resolved_chain_id)


def normalize_transaction_data(tx_data: dict[str, Any], chain_id: str) -> dict[str, Any]:
    """Normalize and validate transaction data"""
    sender = tx_data.get("from")
    recipient = tx_data.get("to")
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("transaction.from is required")
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("transaction.to is required")

    try:
        amount = int(tx_data["amount"])
    except KeyError as exc:
        raise ValueError("transaction.amount is required") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.amount must be an integer") from exc

    try:
        fee = int(tx_data.get("fee", 36))
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.fee must be an integer") from exc

    try:
        nonce = int(tx_data.get("nonce", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.nonce must be an integer") from exc

    if amount < 0:
        raise ValueError("transaction.amount must be non-negative")
    if fee < 0:
        raise ValueError("transaction.fee must be non-negative")
    if nonce < 0:
        raise ValueError("transaction.nonce must be non-negative")

    payload = tx_data.get("payload", {})
    if payload is None:
        payload = {}

    tx_type = tx_data.get("type", "TRANSFER")
    if tx_type:
        tx_type = tx_type.upper()

    # Ensure payload is a dict
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except Exception:
            payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return {
        "chain_id": chain_id,
        "type": tx_type,
        "from": sender.strip(),
        "to": recipient.strip(),
        "amount": amount,
        "value": amount,  # Add value field for state transition compatibility
        "fee": fee,
        "nonce": nonce,
        "payload": payload,
        "signature": tx_data.get("signature"),
    }


def get_bridge_admin_addresses() -> set[str]:
    """Return the configured bridge admin addresses as a lowercase set."""
    return {a.strip().lower() for a in settings.bridge_admin_addresses.split(",") if a.strip()}


def verify_admin_signature(payload: dict[str, Any], admin_address: str, admin_signature: str) -> bool:
    """Verify that an administrative request was signed by a configured bridge admin.

    The signed message is the canonical JSON of ``payload`` excluding the
    ``admin_signature`` field. The recovered signer must match
    ``admin_address`` and that address must appear in ``bridge_admin_addresses``.
    """
    if not admin_address or not admin_signature:
        return False

    admins = get_bridge_admin_addresses()
    if not admins:
        _logger.warning("No bridge_admin_addresses configured; rejecting admin request")
        return False

    if admin_address.lower() not in admins:
        _logger.warning("Admin address %s is not in bridge_admin_addresses", admin_address)
        return False

    sign_payload = {k: v for k, v in payload.items() if k != "admin_signature"}
    return verify_request_signature(admin_address, admin_signature, sign_payload)
