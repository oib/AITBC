"""
Cryptographic Utilities for CLI Security
Provides real signature verification for multisig operations
"""

import json
import secrets

from eth_account import Account
from eth_utils import keccak, to_checksum_address


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

        return "0x" + signature.signature.hex()

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

    # Validate address format (0x-prefixed Ethereum-style, or legacy ait1/aitbc1)
    to_address = tx_data["to"]
    if to_address.startswith("0x"):
        if len(to_address) != 42:
            return False, "Invalid recipient address format: 0x address must be 42 chars"
        if not all(c.lower() in "0123456789abcdef" for c in to_address[2:]):
            return False, "Invalid recipient address format: invalid characters"
    elif to_address.startswith("ait"):
        if len(to_address) < 50 or len(to_address) > 70:
            return False, "Invalid recipient address format: invalid length"
        if not all(c.lower() in "0123456789abcdef" for c in to_address[3:]):
            return False, "Invalid recipient address format: invalid characters"
    else:
        return False, "Invalid recipient address format: must start with '0x' or 'ait'"

    # Validate amount
    try:
        amount = float(tx_data["amount"])
        if amount <= 0:
            return False, "Amount must be positive"
    except Exception:
        return False, "Invalid amount format"

    return True, ""


class MultisigSecurityManager:
    """Security manager for multisig operations"""

    def __init__(self):
        self.pending_challenges: dict[str, dict] = {}

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

        # Store challenge for verification
        self.pending_challenges[tx_data["tx_id"]] = {
            "challenge": challenge,
            "tx_data": tx_data,
            "multisig_wallet": multisig_wallet,
            "nonce": nonce,
            "created_at": secrets.token_hex(8),
        }

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
        if tx_id not in self.pending_challenges:
            return False, "Transaction not found or expired"

        challenge_data = self.pending_challenges[tx_id]
        challenge = challenge_data["challenge"]

        # Verify signature
        if not verify_signature(challenge, signature, signer_address):
            return False, f"Invalid signature for signer {signer_address}"

        # Check if signer is authorized
        tx_data = challenge_data["tx_data"]
        authorized_signers = tx_data.get("required_signers", [])

        if signer_address not in authorized_signers:
            return False, f"Signer {signer_address} is not authorized"

        return True, "Signature verified successfully"

    def cleanup_challenge(self, tx_id: str):
        """Clean up challenge after transaction completion"""
        if tx_id in self.pending_challenges:
            del self.pending_challenges[tx_id]


def bech32_to_hex(bech32_address: str) -> str:
    """
    Convert AITBC address to hex (0x) address format.

    AITBC now uses Ethereum-style 0x checksum addresses natively.
    Legacy aitbc1/ait1 prefixed addresses are stripped and converted
    to 0x format for backward compatibility.

    Args:
        bech32_address: AITBC address (e.g., "0xc10f0e4f..." or legacy "aitbc1c10f0e4f...")

    Returns:
        Hex address (e.g., "0xc10f0e4f...")
    """
    if not bech32_address:
        raise ValueError("Address cannot be empty")

    # Already in 0x format — return as-is
    if bech32_address.startswith("0x"):
        return bech32_address

    # Legacy aitbc1 prefix (backward compat)
    if bech32_address.startswith("aitbc1"):
        hex_part = bech32_address[6:]
    elif bech32_address.startswith("ait1"):
        hex_part = bech32_address[4:]
    else:
        hex_part = bech32_address

    return "0x" + hex_part


def hex_to_bech32(hex_address: str) -> str:
    """
    Convert hex address to AITBC address format.

    AITBC now uses 0x-prefixed addresses natively. This function
    returns the 0x format directly. Legacy aitbc1 prefix is no longer used.

    Args:
        hex_address: Hex address (e.g., "0xc10f0e4f..." or "c10f0e4f...")

    Returns:
        AITBC address in 0x format (e.g., "0xc10f0e4f...")
    """
    if not hex_address:
        raise ValueError("Address cannot be empty")

    if hex_address.startswith("0x"):
        return hex_address

    return "0x" + hex_address


# Global security manager instance
multisig_security = MultisigSecurityManager()
