from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from secrets import token_bytes

from ..crypto.encryption import EncryptionSuite, EncryptionError


@dataclass
class WalletRecord:
    wallet_id: str
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

    def get_wallet(self, wallet_id: str) -> Optional[WalletRecord]:
        return self._wallets.get(wallet_id)

    def create_wallet(self, wallet_id: str, password: str, plaintext: bytes, metadata: Optional[Dict[str, str]] = None) -> WalletRecord:
        salt = token_bytes(self._encryption.salt_bytes)
        nonce = token_bytes(self._encryption.nonce_bytes)
        ciphertext = self._encryption.encrypt(password=password, plaintext=plaintext, salt=salt, nonce=nonce)
        record = WalletRecord(wallet_id=wallet_id, salt=salt, nonce=nonce, ciphertext=ciphertext, metadata=metadata or {})
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
