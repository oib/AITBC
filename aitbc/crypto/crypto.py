"""
Cryptographic utilities for AITBC
Provides Ethereum-specific cryptographic operations and security functions
"""

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from aitbc.aitbc_logging import get_logger
from eth_keys.exceptions import BadSignature, ValidationError

_logger = get_logger(__name__)

#: Order of the secp256k1 group. A valid private key is a scalar in [1, n-1]; eth-account
#: does not enforce this and will happily sign with 0.
_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def derive_ethereum_address(private_key: str) -> str:
    """Derive Ethereum address from private key using eth-account"""
    try:
        from eth_account import Account

        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]

        account = Account.from_key(private_key)
        return str(account.address)
    except ImportError:
        raise ImportError(
            "eth-account is required for Ethereum address derivation. Install with: pip install eth-account"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to derive address from private key: {e}") from e


def sign_transaction_hash(transaction_hash: str, private_key: str) -> str:
    """Sign an already-computed 32-byte hash with a private key.

    Signs the digest directly, with no EIP-191 prefix -- the caller has already decided
    what the hash covers. :func:`verify_signature` recovers the same way, and the two must
    stay symmetric.

    This called ``account.sign_hash``, which eth-account removed in 0.13; every call
    raised ``'LocalAccount' object has no attribute 'sign_hash'``. The property test that
    would have caught it was skipped with the reason "sign_transaction_hash API may have
    changed in eth-account" -- it had, and the skip left consensus (poa.py) and the bridge
    CLI calling a function that could not succeed.
    """
    try:
        from eth_account import Account

        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]
        if transaction_hash.startswith("0x"):
            transaction_hash = transaction_hash[2:]

        # eth-account accepts a key of 0 (and other out-of-range scalars) and returns a
        # signature that no one can recover from. Signing must fail loudly instead: in
        # consensus a validator would otherwise produce blocks whose signatures silently
        # do not verify.
        key_int = int(private_key, 16)
        if not 1 <= key_int < _SECP256K1_ORDER:
            raise ValueError("private key is out of range for secp256k1")

        account = Account.from_key(private_key)
        # "unsafe" here refers to signing a bare digest rather than a prefixed message;
        # that is exactly this function's contract.
        signed_message = account.unsafe_sign_hash(bytes.fromhex(transaction_hash))
        return str(signed_message.signature.hex())
    except ImportError:
        raise ImportError("eth-account is required for signing. Install with: pip install eth-account") from None
    except Exception as e:
        raise ValueError(f"Failed to sign transaction hash: {e}") from e


def verify_signature(message_hash: str, signature: str, address: str) -> bool:
    """Verify a signature produced by :func:`sign_transaction_hash`.

    Recovers from the raw digest, matching how the signature was produced. This used
    ``Account.recover_message``, which expects an EIP-191 ``SignableMessage`` rather than
    a bare hash -- so it was both broken on its own terms and asymmetric with the signer.
    Neither showed up while the round-trip property test was skipped.

    It then used ``Account._recover_hash``, which worked but was a second recovery
    implementation reached through a different library, and so invisible to the
    ``keys.Signature(`` grep that V23-05's centralisation check greps for. Being private,
    it is also the same shape as the breakage that preceded it: eth-account 0.13 removed
    ``sign_hash`` and left signing broken for a release. It now calls
    :func:`_recover_address` like every other recovery path.
    """
    try:
        from eth_utils import to_bytes

        message_bytes = to_bytes(hexstr=message_hash.removeprefix("0x"))
        signature_bytes = to_bytes(hexstr=signature.removeprefix("0x"))

        recovered_address = _recover_address(message_bytes, signature_bytes)
        # Compare on the 0x-prefixed form both sides normalise to, case-insensitively:
        # recovery returns an EIP-55 checksummed address, and callers pass whatever they
        # hold. Stripping "0x" from only one side, as this did, made every comparison
        # false even once recovery worked.
        if not address.startswith("0x"):
            address = "0x" + address
        return bool(recovered_address.lower() == address.lower())
    except ImportError:
        # eth-account is no longer reached from here; recovery uses eth-keys via
        # _recover_address. Naming the packages actually required makes the error
        # actionable rather than sending the reader after the wrong dependency.
        raise ImportError(
            "eth-keys and eth-utils are required for signature verification. Install with: pip install eth-keys eth-utils"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to verify signature: {e}") from e


def _recover_address(msg_hash: bytes, sig_bytes: bytes) -> str:
    """Recover the Ethereum address from a 65-byte secp256k1 signature.

    Normalizes an Ethereum-encoded recovery id (27/28) to the canonical 0/1
    before constructing ``eth_keys.Signature``. Raises ``BadSignature`` (or
    ``ValidationError``) for malformed signatures so callers can distinguish
    parse errors from unexpected runtime errors.
    """
    from eth_keys import keys

    if len(sig_bytes) != 65:
        raise BadSignature("Invalid signature length")
    recovery_id = sig_bytes[64]
    if recovery_id >= 27:
        recovery_id -= 27
    if recovery_id not in (0, 1):
        raise BadSignature("Invalid recovery id")
    sig = keys.Signature(sig_bytes[:64] + bytes([recovery_id]))
    pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
    return pub_key.to_checksum_address()


def recover_signer(message_data: dict[str, Any], signature: str) -> str | None:
    """Recover the signer's checksum address from a canonical-JSON signature.

    This is the single canonical implementation that all AITBC services should
    use for request/proof signature verification. It replaces the duplicated
    ``verify_transaction_signature`` / ``verify_request_signature`` /
    ``_verify_proposer_signature`` copies in the blockchain node.

    The signed message is ``keccak256(json.dumps(message_data, sort_keys=True,
    separators=(",", ":")))`` and the signature is a 65-byte secp256k1
    ``r‖s‖v`` hex string (optionally ``0x``-prefixed).

    Args:
        message_data: The dict that was signed (without any ``signature`` key).
        signature: The 65-byte hex signature.

    Returns:
        The recovered checksum address (str) on success, or ``None`` on any
        failure (invalid signature, wrong length, recovery error).
    """
    if not signature:
        return None
    try:
        from eth_utils import keccak

        message = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode()
        msg_hash = keccak(message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        return _recover_address(msg_hash, sig_bytes)
    except (BadSignature, ValidationError, ValueError) as e:
        _logger.warning("Signature could not be parsed: %s", e)
        return None
    except Exception as e:
        _logger.error("Unexpected error during signature recovery: %s", e)
        return None


def encrypt_private_key(private_key: str, password: str) -> str:
    """Encrypt private key using Fernet symmetric encryption"""
    try:
        # Derive key from password
        password_bytes = password.encode("utf-8")
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))

        # Encrypt private key
        fernet = Fernet(key)
        encrypted_key = fernet.encrypt(private_key.encode("utf-8"))

        # Combine salt and encrypted key
        combined = salt + encrypted_key
        return base64.urlsafe_b64encode(combined).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to encrypt private key: {e}") from e


def decrypt_private_key(encrypted_key: str, password: str) -> str:
    """Decrypt private key using Fernet symmetric encryption"""
    try:
        # Decode combined salt + encrypted data
        combined = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))

        # Extract salt (first 16 bytes) and encrypted data (remaining bytes)
        salt = combined[:16]
        encrypted_data = combined[16:]

        # Derive same encryption key from password using stored salt
        # Must use identical parameters as encryption for successful decryption
        password_bytes = password.encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))

        # Decrypt private key using derived key
        fernet = Fernet(key)
        decrypted_key = fernet.decrypt(encrypted_data)
        return decrypted_key.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to decrypt private key: {e}") from e


def generate_secure_random_bytes(length: int = 32) -> str:
    """Generate cryptographically secure random bytes as hex string"""
    return os.urandom(length).hex()


def keccak256_hash(data: str | bytes) -> str:
    """Compute Keccak-256 hash of data"""
    try:
        from eth_hash.auto import keccak

        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        return keccak(data_bytes).hex()
    except ImportError:
        raise ImportError("eth-hash is required for Keccak-256 hashing. Install with: pip install eth-hash") from None
    except Exception as e:
        raise ValueError(f"Failed to compute Keccak-256 hash: {e}") from e


def sha256_hash(data: str | bytes) -> str:
    """Compute SHA-256 hash of data"""
    try:
        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        return hashlib.sha256(data_bytes).hexdigest()
    except Exception as e:
        raise ValueError(f"Failed to compute SHA-256 hash: {e}") from e


def validate_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format and checksum.

    Delegates to :func:`aitbc.utils.validation.validate_address` which
    supports EIP-55 checksum validation via eth_utils (with a regex
    fallback when eth_utils is unavailable) and legacy ait1/aitbc1
    prefixed addresses.
    """
    from ..utils.validation import validate_address

    return validate_address(address)


def generate_ethereum_private_key() -> str:
    """Generate a new Ethereum private key"""
    try:
        from eth_account import Account

        account = Account.create()
        return str(account.key.hex())
    except ImportError:
        raise ImportError(
            "eth-account is required for private key generation. Install with: pip install eth-account"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to generate private key: {e}") from e
