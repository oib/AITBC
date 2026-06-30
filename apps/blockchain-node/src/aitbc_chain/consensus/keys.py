"""
Validator Key Management (v0.7.5 rewrite — RSA → secp256k1)

Handles cryptographic key operations for validators using secp256k1
via ``eth_keys``, matching the PoA block signing pattern. Key persistence
is file-based (JSON), storing hex-encoded private/public keys.

Uses Agent A's ``aitbc.crypto.consensus_signing`` utilities for
signing/verification, which wrap ``eth_keys`` secp256k1 operations.
"""

import json
import os
import time
from dataclasses import dataclass

from eth_keys import keys

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.consensus_signing import (
    sign_block_hash,
    sign_consensus_message,
    verify_block_signature,
    verify_consensus_message,
)

logger = get_logger(__name__)


@dataclass
class ValidatorKeyPair:
    """secp256k1 key pair for a validator."""

    address: str  # Ethereum-style checksummed address
    private_key_hex: str  # hex-encoded secp256k1 private key (no 0x prefix)
    public_key_hex: str  # hex-encoded secp256k1 public key (no 0x prefix)
    created_at: float
    last_rotated: float


class KeyManager:
    """Manages validator secp256k1 cryptographic keys."""

    def __init__(self, keys_dir: str = "/opt/aitbc/dev"):
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, ValidatorKeyPair] = {}
        self._ensure_keys_directory()
        self._load_existing_keys()

    def _ensure_keys_directory(self) -> None:
        """Ensure keys directory exists and has proper permissions."""
        os.makedirs(self.keys_dir, mode=0o700, exist_ok=True)

    def _load_existing_keys(self) -> None:
        """Load existing key pairs from disk."""
        keys_file = os.path.join(self.keys_dir, "validator_keys.json")
        if os.path.exists(keys_file):
            try:
                with open(keys_file) as f:
                    keys_data = json.load(f)
                for address, key_data in keys_data.items():
                    # Support both old PEM format (skip) and new hex format
                    if "private_key_hex" not in key_data:
                        logger.warning("Skipping legacy RSA key for %s — regenerate with secp256k1", address)
                        continue
                    self.key_pairs[address] = ValidatorKeyPair(
                        address=address,
                        private_key_hex=key_data["private_key_hex"],
                        public_key_hex=key_data["public_key_hex"],
                        created_at=key_data["created_at"],
                        last_rotated=key_data["last_rotated"],
                    )
            except Exception as e:
                logger.error("Error loading keys: %s", e)

    def generate_key_pair(self, address: str | None = None) -> ValidatorKeyPair:
        """Generate a new secp256k1 key pair for a validator.

        Args:
            address: Optional address to associate with the key. If not
                provided, the address is derived from the generated public key.

        Returns:
            ValidatorKeyPair with hex-encoded keys and derived address.
        """
        import secrets

        # Generate a random secp256k1 private key
        private_key_bytes = secrets.token_bytes(32)
        pk = keys.PrivateKey(private_key_bytes)
        derived_address = pk.public_key.to_checksum_address()
        final_address = address or derived_address

        private_key_hex = private_key_bytes.hex()
        public_key_hex = pk.public_key.to_bytes().hex()

        current_time = time.time()
        key_pair = ValidatorKeyPair(
            address=final_address,
            private_key_hex=private_key_hex,
            public_key_hex=public_key_hex,
            created_at=current_time,
            last_rotated=current_time,
        )
        self.key_pairs[final_address] = key_pair
        self._save_keys()
        return key_pair

    def get_key_pair(self, address: str) -> ValidatorKeyPair | None:
        """Get key pair for validator."""
        return self.key_pairs.get(address)

    def rotate_key(self, address: str) -> ValidatorKeyPair | None:
        """Rotate validator keys — generates a new key pair, preserving created_at."""
        if address not in self.key_pairs:
            return None
        old_created = self.key_pairs[address].created_at
        new_key_pair = self.generate_key_pair(address)
        new_key_pair.created_at = old_created
        new_key_pair.last_rotated = time.time()
        self.key_pairs[address] = new_key_pair
        self._save_keys()
        return new_key_pair

    def sign_message(self, address: str, message: str) -> str | None:
        """Sign a message with the validator's secp256k1 private key.

        Uses ``sign_consensus_message()`` from Agent A's consensus_signing
        module, which keccak256-hashes the message and signs with secp256k1.
        """
        key_pair = self.key_pairs.get(address)
        if not key_pair:
            return None
        try:
            return sign_consensus_message({"message": message}, key_pair.private_key_hex)
        except Exception as e:
            logger.error("Error signing message for %s: %s", address, e)
            return None

    def verify_signature(self, address: str, message: str, signature: str) -> bool:
        """Verify a message signature against the validator's address.

        Uses ``verify_consensus_message()`` from Agent A's consensus_signing
        module, which recovers the signer from the signature and compares
        to the expected address.
        """
        key_pair = self.key_pairs.get(address)
        if not key_pair:
            return False
        try:
            return verify_consensus_message({"message": message}, signature, address)
        except Exception:
            return False

    def sign_block_hash(self, address: str, block_hash: str) -> str | None:
        """Sign a block hash with the validator's secp256k1 private key.

        Uses ``sign_block_hash()`` from Agent A's consensus_signing module.
        """
        key_pair = self.key_pairs.get(address)
        if not key_pair:
            return None
        try:
            return sign_block_hash(block_hash, key_pair.private_key_hex)
        except Exception as e:
            logger.error("Error signing block hash for %s: %s", address, e)
            return None

    def verify_block_signature(self, address: str, block_hash: str, signature: str) -> bool:
        """Verify a block signature against the validator's address.

        Uses ``verify_block_signature()`` from Agent A's consensus_signing module.
        """
        try:
            return verify_block_signature(block_hash, signature, address)
        except Exception:
            return False

    def get_public_key_hex(self, address: str) -> str | None:
        """Get the hex-encoded public key for a validator."""
        key_pair = self.get_key_pair(address)
        return key_pair.public_key_hex if key_pair else None

    def _save_keys(self) -> None:
        """Save key pairs to disk."""
        keys_file = os.path.join(self.keys_dir, "validator_keys.json")
        keys_data = {}
        for address, key_pair in self.key_pairs.items():
            keys_data[address] = {
                "private_key_hex": key_pair.private_key_hex,
                "public_key_hex": key_pair.public_key_hex,
                "created_at": key_pair.created_at,
                "last_rotated": key_pair.last_rotated,
            }
        try:
            with open(keys_file, "w") as f:
                json.dump(keys_data, f, indent=2)
            os.chmod(keys_file, 0o600)
        except Exception as e:
            logger.error("Error saving keys: %s", str(e))

    def should_rotate_key(self, address: str, rotation_interval: int = 86400) -> bool:
        """Check if key should be rotated (default: 24 hours)."""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return True
        return time.time() - key_pair.last_rotated >= rotation_interval

    def get_key_age(self, address: str) -> float | None:
        """Get age of key in seconds."""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return None
        return time.time() - key_pair.created_at


key_manager = KeyManager()
