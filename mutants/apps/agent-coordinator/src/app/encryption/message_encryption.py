"""
Message Encryption Module for AITBC Agent Coordinator
Implements end-to-end message encryption using agent public/private keys
"""

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from aitbc import get_logger

logger = get_logger(__name__)


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


@dataclass
class EncryptedMessage:
    """Encrypted message structure"""

    ciphertext: bytes
    session_key: bytes
    nonce: bytes
    signature: bytes
    sender_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for transmission"""
        import base64

        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode("utf-8"),
            "session_key": base64.b64encode(self.session_key).decode("utf-8"),
            "nonce": base64.b64encode(self.nonce).decode("utf-8"),
            "signature": base64.b64encode(self.signature).decode("utf-8"),
            "sender_id": self.sender_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EncryptedMessage":
        """Create from dictionary"""
        import base64

        return cls(
            ciphertext=base64.b64decode(data["ciphertext"]),
            session_key=base64.b64decode(data["session_key"]),
            nonce=base64.b64decode(data["nonce"]),
            signature=base64.b64decode(data["signature"]),
            sender_id=data["sender_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class AgentKeyPair:
    """Agent key pair for encryption"""

    agent_id: str
    public_key: bytes
    private_key: bytes | None = None
    key_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        import base64

        result = {
            "agent_id": self.agent_id,
            "public_key": base64.b64encode(self.public_key).decode("utf-8"),
            "key_id": self.key_id,
            "created_at": self.created_at.isoformat(),
        }
        if self.private_key:
            result["private_key"] = base64.b64encode(self.private_key).decode("utf-8")
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentKeyPair":
        """Create from dictionary"""
        import base64

        return cls(
            agent_id=data["agent_id"],
            public_key=base64.b64decode(data["public_key"]),
            private_key=base64.b64decode(data["private_key"]) if data.get("private_key") else None,
            key_id=data.get("key_id", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
mutants_xǁMessageEncryptorǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁget_public_key__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁregister_public_key__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁencrypt_message__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁverify_signature__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut: MutantDict = {}  # type: ignore
mutants_xǁMessageEncryptorǁ_load_keys__mutmut: MutantDict = {}  # type: ignore


class MessageEncryptor:
    """Message encryption and decryption handler"""

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁ__init____mutmut)
    def __init__(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_orig(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_1(self, keys_dir: str = "XX/var/lib/aitbc/agent_keysXX") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_2(self, keys_dir: str = "/VAR/LIB/AITBC/AGENT_KEYS") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_3(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = None
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_4(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = None
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_5(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(None, mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_6(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=None, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_7(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=None)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_8(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(mode=448, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_9(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_10(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, )
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_11(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=449, exist_ok=True)
        self._load_keys()

    def xǁMessageEncryptorǁ__init____mutmut_12(self, keys_dir: str = "/var/lib/aitbc/agent_keys") -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=False)
        self._load_keys()

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut)
    def generate_key_pair(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_orig(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_1(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = None
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_2(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=None, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_3(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=None, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_4(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=None)
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_5(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_6(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_7(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, )
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_8(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65538, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_9(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2049, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_10(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = None
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_11(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=None, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_12(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=None
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_13(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_14(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_15(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = None
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_16(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=None,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_17(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=None,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_18(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=None,
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_19(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_20(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_21(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_22(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = None
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_23(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime(None)}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_24(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(None).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_25(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('XX%Y%m%d%H%M%SXX')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_26(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%y%m%d%h%m%s')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_27(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%M%D%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_28(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = None
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_29(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=None, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_30(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=None, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_31(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_32(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=None)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_33(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_34(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_35(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_36(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, )
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_37(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = None
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_38(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(None)
        logger.info("Generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_39(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info(None, agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_40(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", None)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_41(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info(agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_42(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Generated key pair for agent %s", )
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_43(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("XXGenerated key pair for agent %sXX", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_44(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("generated key pair for agent %s", agent_id)
        return key_pair

    def xǁMessageEncryptorǁgenerate_key_pair__mutmut_45(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("GENERATED KEY PAIR FOR AGENT %S", agent_id)
        return key_pair

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁget_public_key__mutmut)
    def get_public_key(self, agent_id: str) -> bytes | None:
        """Get public key for an agent"""
        if agent_id in self.key_pairs:
            return self.key_pairs[agent_id].public_key
        return None

    def xǁMessageEncryptorǁget_public_key__mutmut_orig(self, agent_id: str) -> bytes | None:
        """Get public key for an agent"""
        if agent_id in self.key_pairs:
            return self.key_pairs[agent_id].public_key
        return None

    def xǁMessageEncryptorǁget_public_key__mutmut_1(self, agent_id: str) -> bytes | None:
        """Get public key for an agent"""
        if agent_id not in self.key_pairs:
            return self.key_pairs[agent_id].public_key
        return None

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁregister_public_key__mutmut)
    def register_public_key(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_orig(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_1(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = None
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_2(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime(None)}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_3(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(None).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_4(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('XX%Y%m%d%H%M%SXX')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_5(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%y%m%d%h%m%s')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_6(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%M%D%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_7(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = None
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_8(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=None, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_9(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=None, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_10(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=None)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_11(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_12(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_13(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_14(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, )
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_15(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = None
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_16(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(None)
        logger.info("Registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_17(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info(None, agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_18(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", None)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_19(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info(agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_20(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", )
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_21(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("XXRegistered public key for agent %sXX", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_22(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("registered public key for agent %s", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_23(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("REGISTERED PUBLIC KEY FOR AGENT %S", agent_id)
        return True

    def xǁMessageEncryptorǁregister_public_key__mutmut_24(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info("Registered public key for agent %s", agent_id)
        return False

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁencrypt_message__mutmut)
    def encrypt_message(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_orig(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_1(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_2(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error(None, recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_3(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", None)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_4(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error(recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_5(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", )
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_6(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("XXNo public key for recipient %sXX", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_7(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("no public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_8(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("NO PUBLIC KEY FOR RECIPIENT %S", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_9(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = None
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_10(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = None
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_11(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode(None)
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_12(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(None).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_13(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("XXutf-8XX")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_14(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("UTF-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_15(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = None
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_16(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(None)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_17(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(33)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_18(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = None
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_19(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(None)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_20(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = None
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_21(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(None)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_22(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(13)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_23(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = None
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_24(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(None, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_25(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, None, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_26(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_27(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_28(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, )
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_29(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = None
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_30(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(None, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_31(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=None)
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_32(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_33(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, )
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_34(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_35(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(None)
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_36(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(None)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_37(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = None
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_38(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                None, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_39(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, None
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_40(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_41(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_42(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=None, algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_43(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=None, label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_44(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_45(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_46(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), )
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_47(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=None), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_48(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs and not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_49(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_50(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_51(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error(None, sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_52(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", None)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_53(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error(sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_54(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", )
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_55(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("XXNo private key for sender %sXX", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_56(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("no private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_57(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("NO PRIVATE KEY FOR SENDER %S", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_58(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = None
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_59(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is not None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_60(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error(None, sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_61(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", None)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_62(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error(sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_63(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", )
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_64(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("XXNo private key for sender %sXX", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_65(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("no private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_66(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("NO PRIVATE KEY FOR SENDER %S", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_67(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = None
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_68(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                None, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_69(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=None
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_70(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_71(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_72(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_73(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_74(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(None)
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_75(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(None)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_76(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = None
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_77(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                None, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_78(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, None, hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_79(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), None
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_80(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_81(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_82(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_83(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=None, salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_84(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=None), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_85(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_86(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), ), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_87(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(None), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_88(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = None
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_89(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=None, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_90(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=None, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_91(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=None, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_92(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=None, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_93(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=None
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_94(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_95(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_96(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_97(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_98(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_99(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info(None, sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_100(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", None, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_101(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, None)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_102(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info(sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_103(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_104(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, )
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_105(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("XXEncrypted message from %s to %sXX", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_106(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_107(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("ENCRYPTED MESSAGE FROM %S TO %S", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_108(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error(None, e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_109(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", None)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_110(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error(e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_111(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("Error encrypting message: %s", )
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_112(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("XXError encrypting message: %sXX", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_113(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("error encrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁencrypt_message__mutmut_114(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error("No public key for recipient %s", recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode("utf-8")
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            if not isinstance(recipient_key, RSAPublicKey):
                raise TypeError(f"Encryption only supported for RSA keys, got {type(recipient_key)}")
            encrypted_session_key = recipient_key.encrypt(
                session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
            )
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key_bytes = self.key_pairs[sender_id].private_key
            if sender_private_key_bytes is None:
                logger.error("No private key for sender %s", sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(
                sender_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(sender_private_key, RSAPrivateKey):
                raise TypeError(f"Signing only supported for RSA keys, got {type(sender_private_key)}")
            signature = sender_private_key.sign(
                ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
            )
            encrypted_msg = EncryptedMessage(
                ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id
            )
            logger.info("Encrypted message from %s to %s", sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error("ERROR ENCRYPTING MESSAGE: %S", e)
            return None

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁdecrypt_message__mutmut)
    def decrypt_message(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_orig(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_1(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs and not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_2(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_3(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_4(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error(None, recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_5(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", None)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_6(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error(recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_7(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", )
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_8(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("XXNo private key for recipient %sXX", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_9(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("no private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_10(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("NO PRIVATE KEY FOR RECIPIENT %S", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_11(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = None
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_12(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is not None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_13(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error(None, recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_14(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", None)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_15(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error(recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_16(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", )
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_17(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("XXNo private key for recipient %sXX", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_18(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("no private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_19(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("NO PRIVATE KEY FOR RECIPIENT %S", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_20(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = None
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_21(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                None, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_22(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=None
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_23(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_24(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_25(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_26(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_27(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(None)
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_28(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(None)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_29(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = None
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_30(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                None,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_31(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                None,
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_32(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_33(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_34(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=None, algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_35(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=None, label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_36(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_37(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_38(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), ),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_39(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=None), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_40(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = None
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_41(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(None)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_42(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = None
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_43(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(None, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_44(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, None, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_45(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_46(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_47(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, )
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_48(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id not in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_49(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = None
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_50(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    None, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_51(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=None
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_52(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_53(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_54(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_55(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(None)
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_56(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(None)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_57(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        None,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_58(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        None,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_59(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        None,
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_60(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        None,
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_61(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_62(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_63(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_64(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_65(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=None, salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_66(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=None),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_67(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_68(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), ),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_69(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(None), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_70(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info(None, encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_71(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", None)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_72(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info(encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_73(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", )
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_74(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("XXSignature verified for message from %sXX", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_75(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_76(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("SIGNATURE VERIFIED FOR MESSAGE FROM %S", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_77(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning(None, e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_78(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", None)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_79(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning(e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_80(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", )
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_81(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("XXSignature verification failed: %sXX", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_82(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_83(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("SIGNATURE VERIFICATION FAILED: %S", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_84(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = None
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_85(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(None)
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_86(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode(None))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_87(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("XXutf-8XX"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_88(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("UTF-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_89(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info(None, encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_90(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", None, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_91(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, None)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_92(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info(encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_93(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_94(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, )
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_95(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("XXDecrypted message from %s to %sXX", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_96(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_97(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("DECRYPTED MESSAGE FROM %S TO %S", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_98(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error(None, e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_99(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", None)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_100(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error(e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_101(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("Error decrypting message: %s", )
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_102(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("XXError decrypting message: %sXX", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_103(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("error decrypting message: %s", e)
            return None

    def xǁMessageEncryptorǁdecrypt_message__mutmut_104(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key_bytes = self.key_pairs[recipient_id].private_key
            if recipient_private_key_bytes is None:
                logger.error("No private key for recipient %s", recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(
                recipient_private_key_bytes, password=None, backend=default_backend()
            )
            if not isinstance(recipient_private_key, RSAPrivateKey):
                raise TypeError(f"Decryption only supported for RSA keys, got {type(recipient_private_key)}")
            session_key = recipient_private_key.decrypt(
                encrypted_msg.session_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(
                    self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend()
                )
                try:
                    if not isinstance(sender_public_key, RSAPublicKey):
                        raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
                    sender_public_key.verify(
                        encrypted_msg.signature,
                        encrypted_msg.ciphertext,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                    logger.info("Signature verified for message from %s", encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning("Signature verification failed: %s", e)
            message: dict[str, Any] = json.loads(message_json.decode("utf-8"))
            logger.info("Decrypted message from %s to %s", encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error("ERROR DECRYPTING MESSAGE: %S", e)
            return None

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁverify_signature__mutmut)
    def verify_signature(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_orig(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_1(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_2(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error(None, sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_3(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", None)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_4(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error(sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_5(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", )
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_6(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("XXNo public key for sender %sXX", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_7(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("no public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_8(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("NO PUBLIC KEY FOR SENDER %S", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_9(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return True
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_10(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = None
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_11(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                None, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_12(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=None
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_13(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_14(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_15(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_16(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(None)
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_17(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(None)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_18(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                None,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_19(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                None,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_20(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                None,
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_21(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                None,
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_22(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_23(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_24(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_25(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_26(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=None, salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_27(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=None),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_28(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_29(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), ),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_30(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(None), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_31(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info(None, sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_32(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", None)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_33(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info(sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_34(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", )
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_35(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("XXSignature verified for message from %sXX", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_36(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_37(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("SIGNATURE VERIFIED FOR MESSAGE FROM %S", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_38(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return False
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_39(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning(None, e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_40(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", None)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_41(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning(e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_42(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", )
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_43(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("XXSignature verification failed: %sXX", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_44(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("signature verification failed: %s", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_45(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("SIGNATURE VERIFICATION FAILED: %S", e)
            return False

    def xǁMessageEncryptorǁverify_signature__mutmut_46(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error("No public key for sender %s", sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(
                self.key_pairs[sender_id].public_key, backend=default_backend()
            )
            if not isinstance(sender_public_key, RSAPublicKey):
                raise TypeError(f"Signature verification only supported for RSA keys, got {type(sender_public_key)}")
            sender_public_key.verify(
                encrypted_msg.signature,
                encrypted_msg.ciphertext,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            logger.info("Signature verified for message from %s", sender_id)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return True

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut)
    def rotate_key_pair(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_orig(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_1(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id not in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_2(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = None
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_3(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = None
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_4(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(None, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_5(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, None)
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_6(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_7(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, )
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_8(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(None, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_9(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, None) as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_10(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open("w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_11(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, ) as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_12(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "XXwXX") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_13(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "W") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_14(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(None, f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_15(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), None, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_16(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=None)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_17(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_18(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_19(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, )
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_20(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=3)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_21(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = None
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_22(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(None)
            logger.info("Rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_23(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info(None, agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_24(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", None)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_25(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info(agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_26(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("Rotated key pair for agent %s", )
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_27(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("XXRotated key pair for agent %sXX", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_28(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("rotated key pair for agent %s", agent_id)
            return new_key
        return None

    def xǁMessageEncryptorǁrotate_key_pair__mutmut_29(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f"{agent_id}_old_{old_key.key_id}.json")
            with open(backup_path, "w") as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info("ROTATED KEY PAIR FOR AGENT %S", agent_id)
            return new_key
        return None

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut)
    def _save_key_pair(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_orig(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_1(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = None
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_2(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(None, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_3(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, None)
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_4(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_5(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, )
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_6(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(None, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_7(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, None) as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_8(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open("w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_9(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, ) as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_10(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "XXwXX") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_11(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "W") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_12(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(None, f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_13(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), None, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_14(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=None)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_15(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(f, indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_16(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), indent=2)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_17(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, )
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_18(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=3)
        os.chmod(key_path, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_19(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(None, 384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_20(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, None)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_21(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(384)

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_22(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, )

    def xǁMessageEncryptorǁ_save_key_pair__mutmut_23(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f"{key_pair.agent_id}.json")
        with open(key_path, "w") as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 385)

    @_mutmut_mutated(mutants_xǁMessageEncryptorǁ_load_keys__mutmut)
    def _load_keys(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_orig(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_1(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(None):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_2(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") or (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_3(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(None) and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_4(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith("XX.jsonXX") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_5(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".JSON") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_6(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and filename.endswith("_old_"):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_7(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith(None)):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_8(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("XX_old_XX")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_9(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_OLD_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_10(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = None
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_11(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(None, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_12(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, None)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_13(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_14(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, )
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_15(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(None) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_16(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = None
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_17(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(None)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_18(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = None
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_19(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(None)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_20(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = None
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_21(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info(None, len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_22(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", None)
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_23(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info(len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_24(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", )
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_25(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("XXLoaded %s key pairsXX", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_26(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_27(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("LOADED %S KEY PAIRS", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_28(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error(None, e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_29(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", None)

    def xǁMessageEncryptorǁ_load_keys__mutmut_30(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error(e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_31(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("Error loading keys: %s", )

    def xǁMessageEncryptorǁ_load_keys__mutmut_32(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("XXError loading keys: %sXX", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_33(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("error loading keys: %s", e)

    def xǁMessageEncryptorǁ_load_keys__mutmut_34(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith(".json") and (not filename.endswith("_old_")):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info("Loaded %s key pairs", len(self.key_pairs))
        except Exception as e:
            logger.error("ERROR LOADING KEYS: %S", e)

mutants_xǁMessageEncryptorǁ__init____mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ__init____mutmut['xǁMessageEncryptorǁ__init____mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁ__init____mutmut_12 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_24 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_25'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_25 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_26'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_26 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_27'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_27 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_28'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_28 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_29'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_29 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_30'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_30 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_31'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_31 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_32'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_32 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_33'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_33 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_34'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_34 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_35'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_35 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_36'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_36 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_37'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_37 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_38'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_38 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_39'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_39 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_40'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_40 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_41'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_41 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_42'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_42 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_43'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_43 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_44'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_44 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁgenerate_key_pair__mutmut['xǁMessageEncryptorǁgenerate_key_pair__mutmut_45'] = MessageEncryptor.xǁMessageEncryptorǁgenerate_key_pair__mutmut_45 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁget_public_key__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁget_public_key__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁget_public_key__mutmut['xǁMessageEncryptorǁget_public_key__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁget_public_key__mutmut_1 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁregister_public_key__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁregister_public_key__mutmut['xǁMessageEncryptorǁregister_public_key__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁregister_public_key__mutmut_24 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁencrypt_message__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_24 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_25'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_25 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_26'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_26 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_27'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_27 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_28'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_28 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_29'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_29 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_30'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_30 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_31'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_31 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_32'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_32 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_33'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_33 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_34'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_34 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_35'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_35 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_36'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_36 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_37'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_37 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_38'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_38 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_39'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_39 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_40'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_40 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_41'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_41 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_42'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_42 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_43'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_43 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_44'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_44 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_45'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_45 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_46'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_46 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_47'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_47 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_48'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_48 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_49'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_49 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_50'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_50 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_51'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_51 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_52'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_52 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_53'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_53 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_54'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_54 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_55'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_55 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_56'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_56 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_57'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_57 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_58'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_58 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_59'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_59 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_60'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_60 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_61'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_61 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_62'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_62 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_63'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_63 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_64'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_64 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_65'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_65 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_66'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_66 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_67'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_67 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_68'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_68 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_69'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_69 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_70'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_70 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_71'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_71 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_72'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_72 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_73'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_73 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_74'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_74 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_75'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_75 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_76'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_76 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_77'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_77 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_78'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_78 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_79'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_79 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_80'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_80 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_81'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_81 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_82'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_82 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_83'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_83 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_84'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_84 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_85'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_85 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_86'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_86 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_87'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_87 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_88'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_88 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_89'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_89 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_90'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_90 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_91'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_91 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_92'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_92 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_93'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_93 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_94'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_94 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_95'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_95 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_96'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_96 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_97'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_97 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_98'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_98 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_99'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_99 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_100'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_100 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_101'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_101 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_102'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_102 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_103'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_103 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_104'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_104 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_105'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_105 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_106'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_106 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_107'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_107 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_108'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_108 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_109'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_109 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_110'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_110 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_111'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_111 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_112'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_112 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_113'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_113 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁencrypt_message__mutmut['xǁMessageEncryptorǁencrypt_message__mutmut_114'] = MessageEncryptor.xǁMessageEncryptorǁencrypt_message__mutmut_114 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_24 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_25'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_25 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_26'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_26 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_27'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_27 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_28'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_28 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_29'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_29 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_30'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_30 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_31'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_31 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_32'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_32 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_33'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_33 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_34'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_34 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_35'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_35 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_36'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_36 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_37'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_37 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_38'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_38 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_39'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_39 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_40'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_40 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_41'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_41 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_42'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_42 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_43'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_43 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_44'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_44 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_45'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_45 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_46'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_46 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_47'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_47 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_48'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_48 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_49'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_49 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_50'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_50 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_51'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_51 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_52'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_52 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_53'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_53 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_54'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_54 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_55'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_55 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_56'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_56 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_57'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_57 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_58'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_58 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_59'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_59 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_60'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_60 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_61'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_61 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_62'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_62 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_63'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_63 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_64'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_64 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_65'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_65 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_66'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_66 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_67'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_67 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_68'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_68 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_69'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_69 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_70'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_70 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_71'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_71 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_72'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_72 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_73'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_73 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_74'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_74 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_75'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_75 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_76'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_76 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_77'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_77 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_78'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_78 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_79'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_79 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_80'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_80 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_81'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_81 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_82'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_82 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_83'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_83 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_84'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_84 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_85'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_85 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_86'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_86 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_87'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_87 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_88'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_88 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_89'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_89 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_90'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_90 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_91'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_91 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_92'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_92 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_93'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_93 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_94'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_94 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_95'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_95 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_96'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_96 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_97'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_97 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_98'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_98 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_99'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_99 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_100'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_100 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_101'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_101 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_102'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_102 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_103'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_103 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁdecrypt_message__mutmut['xǁMessageEncryptorǁdecrypt_message__mutmut_104'] = MessageEncryptor.xǁMessageEncryptorǁdecrypt_message__mutmut_104 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁverify_signature__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_24 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_25'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_25 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_26'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_26 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_27'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_27 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_28'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_28 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_29'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_29 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_30'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_30 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_31'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_31 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_32'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_32 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_33'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_33 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_34'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_34 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_35'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_35 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_36'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_36 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_37'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_37 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_38'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_38 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_39'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_39 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_40'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_40 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_41'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_41 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_42'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_42 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_43'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_43 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_44'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_44 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_45'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_45 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁverify_signature__mutmut['xǁMessageEncryptorǁverify_signature__mutmut_46'] = MessageEncryptor.xǁMessageEncryptorǁverify_signature__mutmut_46 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_24 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_25'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_25 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_26'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_26 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_27'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_27 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_28'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_28 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁrotate_key_pair__mutmut['xǁMessageEncryptorǁrotate_key_pair__mutmut_29'] = MessageEncryptor.xǁMessageEncryptorǁrotate_key_pair__mutmut_29 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_save_key_pair__mutmut['xǁMessageEncryptorǁ_save_key_pair__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁ_save_key_pair__mutmut_23 # type: ignore # mutmut generated

mutants_xǁMessageEncryptorǁ_load_keys__mutmut['_mutmut_orig'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_orig # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_1'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_1 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_2'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_2 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_3'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_3 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_4'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_4 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_5'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_5 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_6'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_6 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_7'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_7 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_8'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_8 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_9'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_9 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_10'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_10 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_11'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_11 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_12'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_12 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_13'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_13 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_14'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_14 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_15'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_15 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_16'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_16 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_17'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_17 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_18'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_18 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_19'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_19 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_20'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_20 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_21'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_21 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_22'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_22 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_23'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_23 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_24'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_24 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_25'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_25 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_26'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_26 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_27'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_27 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_28'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_28 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_29'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_29 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_30'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_30 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_31'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_31 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_32'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_32 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_33'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_33 # type: ignore # mutmut generated
mutants_xǁMessageEncryptorǁ_load_keys__mutmut['xǁMessageEncryptorǁ_load_keys__mutmut_34'] = MessageEncryptor.xǁMessageEncryptorǁ_load_keys__mutmut_34 # type: ignore # mutmut generated


_encryptor: MessageEncryptor | None = None
mutants_x_get_encryptor__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_encryptor__mutmut)
def get_encryptor() -> MessageEncryptor:
    """Get global encryptor instance"""
    global _encryptor
    if _encryptor is None:
        _encryptor = MessageEncryptor()
    return _encryptor


def x_get_encryptor__mutmut_orig() -> MessageEncryptor:
    """Get global encryptor instance"""
    global _encryptor
    if _encryptor is None:
        _encryptor = MessageEncryptor()
    return _encryptor


def x_get_encryptor__mutmut_1() -> MessageEncryptor:
    """Get global encryptor instance"""
    global _encryptor
    if _encryptor is not None:
        _encryptor = MessageEncryptor()
    return _encryptor


def x_get_encryptor__mutmut_2() -> MessageEncryptor:
    """Get global encryptor instance"""
    global _encryptor
    if _encryptor is None:
        _encryptor = None
    return _encryptor

mutants_x_get_encryptor__mutmut['_mutmut_orig'] = x_get_encryptor__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_encryptor__mutmut['x_get_encryptor__mutmut_1'] = x_get_encryptor__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_encryptor__mutmut['x_get_encryptor__mutmut_2'] = x_get_encryptor__mutmut_2 # type: ignore # mutmut generated
