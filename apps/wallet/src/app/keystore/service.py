from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from secrets import token_bytes

from nacl.signing import SigningKey

from ..crypto.encryption import EncryptionSuite, EncryptionError
from ..security import validate_password_rules, wipe_buffer


@dataclass
class WalletRecord:
    wallet_id: str
    public_key: str
    salt: bytes
    nonce: bytes
    ciphertext: bytes
    metadata: Dict[str, str]


class KeystoreService:
    """In-memory keystore with Argon2id + XChaCha20-Poly1305 encryption."""

    def __init__(self, encryption: Optional[EncryptionSuite] = None) -> None:
        self._wallets: Dict[str, WalletRecord] = {}
        self._encryption = encryption or EncryptionSuite()

    def list_wallets(self) -> List[str]:
        return list(self._wallets.keys())

    def list_records(self) -> Iterable[WalletRecord]:
        return list(self._wallets.values())

    def get_wallet(self, wallet_id: str) -> Optional[WalletRecord]:
        return self._wallets.get(wallet_id)

    def create_wallet(
        self,
        wallet_id: str,
        password: str,
        secret: Optional[bytes] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> WalletRecord:
        if wallet_id in self._wallets:
            raise ValueError("wallet already exists")

        validate_password_rules(password)

        metadata_map = {str(k): str(v) for k, v in (metadata or {}).items()}

        if secret is None:
            signing_key = SigningKey.generate()
            secret_bytes = signing_key.encode()
        else:
            if len(secret) != SigningKey.seed_size:
                raise ValueError("secret key must be 32 bytes")
            secret_bytes = secret
            signing_key = SigningKey(secret_bytes)

        salt = token_bytes(self._encryption.salt_bytes)
        nonce = token_bytes(self._encryption.nonce_bytes)
        ciphertext = self._encryption.encrypt(password=password, plaintext=secret_bytes, salt=salt, nonce=nonce)
        record = WalletRecord(
            wallet_id=wallet_id,
            public_key=signing_key.verify_key.encode().hex(),
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext,
            metadata=metadata_map,
        )
        self._wallets[wallet_id] = record
        return record

    def unlock_wallet(self, wallet_id: str, password: str) -> bytes:
        record = self._wallets.get(wallet_id)
        if record is None:
            raise KeyError("wallet not found")
        try:
            return self._encryption.decrypt(password=password, ciphertext=record.ciphertext, salt=record.salt, nonce=record.nonce)
        except EncryptionError as exc:
            raise ValueError("failed to decrypt wallet") from exc

    def delete_wallet(self, wallet_id: str) -> bool:
        return self._wallets.pop(wallet_id, None) is not None

    def sign_message(self, wallet_id: str, password: str, message: bytes) -> bytes:
        secret_bytes = bytearray(self.unlock_wallet(wallet_id, password))
        try:
            signing_key = SigningKey(bytes(secret_bytes))
            signed = signing_key.sign(message)
            return signed.signature
        finally:
            wipe_buffer(secret_bytes)
