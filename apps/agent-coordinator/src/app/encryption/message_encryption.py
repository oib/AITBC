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

from aitbc import get_logger

logger = get_logger(__name__)

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
        return {'ciphertext': base64.b64encode(self.ciphertext).decode('utf-8'), 'session_key': base64.b64encode(self.session_key).decode('utf-8'), 'nonce': base64.b64encode(self.nonce).decode('utf-8'), 'signature': base64.b64encode(self.signature).decode('utf-8'), 'sender_id': self.sender_id, 'timestamp': self.timestamp.isoformat()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'EncryptedMessage':
        """Create from dictionary"""
        import base64
        return cls(ciphertext=base64.b64decode(data['ciphertext']), session_key=base64.b64decode(data['session_key']), nonce=base64.b64decode(data['nonce']), signature=base64.b64decode(data['signature']), sender_id=data['sender_id'], timestamp=datetime.fromisoformat(data['timestamp']))

@dataclass
class AgentKeyPair:
    """Agent key pair for encryption"""
    agent_id: str
    public_key: bytes
    private_key: bytes | None = None
    key_id: str = ''
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        import base64
        result = {'agent_id': self.agent_id, 'public_key': base64.b64encode(self.public_key).decode('utf-8'), 'key_id': self.key_id, 'created_at': self.created_at.isoformat()}
        if self.private_key:
            result['private_key'] = base64.b64encode(self.private_key).decode('utf-8')
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'AgentKeyPair':
        """Create from dictionary"""
        import base64
        return cls(agent_id=data['agent_id'], public_key=base64.b64decode(data['public_key']), private_key=base64.b64decode(data['private_key']) if data.get('private_key') else None, key_id=data.get('key_id', ''), created_at=datetime.fromisoformat(data['created_at']))

class MessageEncryptor:
    """Message encryption and decryption handler"""

    def __init__(self, keys_dir: str = '/var/lib/aitbc/agent_keys') -> None:
        self.keys_dir = keys_dir
        self.key_pairs: dict[str, AgentKeyPair] = {}
        os.makedirs(keys_dir, mode=448, exist_ok=True)
        self._load_keys()

    def generate_key_pair(self, agent_id: str) -> AgentKeyPair:
        """Generate RSA key pair for an agent"""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        public_key = private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
        private_key_bytes = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption())
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=private_key_bytes, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info('Generated key pair for agent %s', agent_id)
        return key_pair

    def get_public_key(self, agent_id: str) -> bytes | None:
        """Get public key for an agent"""
        if agent_id in self.key_pairs:
            return self.key_pairs[agent_id].public_key
        return None

    def register_public_key(self, agent_id: str, public_key: bytes) -> bool:
        """Register a public key for an agent (from other agents)"""
        key_id = f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        key_pair = AgentKeyPair(agent_id=agent_id, public_key=public_key, private_key=None, key_id=key_id)
        self.key_pairs[agent_id] = key_pair
        self._save_key_pair(key_pair)
        logger.info('Registered public key for agent %s', agent_id)
        return True

    def encrypt_message(self, message: dict[str, Any], sender_id: str, recipient_id: str) -> EncryptedMessage | None:
        """Encrypt a message for a recipient"""
        try:
            if recipient_id not in self.key_pairs:
                logger.error('No public key for recipient %s', recipient_id)
                return None
            recipient_public_key = self.key_pairs[recipient_id].public_key
            message_json = json.dumps(message).encode('utf-8')
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            session_key = os.urandom(32)
            aesgcm = AESGCM(session_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, message_json, None)
            recipient_key = serialization.load_pem_public_key(recipient_public_key, backend=default_backend())
            encrypted_session_key = recipient_key.encrypt(session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))  # type: ignore[union-attr]
            if sender_id not in self.key_pairs or not self.key_pairs[sender_id].private_key:
                logger.error('No private key for sender %s', sender_id)
                return None
            sender_private_key = serialization.load_pem_private_key(self.key_pairs[sender_id].private_key, password=None, backend=default_backend())  # type: ignore[arg-type]
            signature = sender_private_key.sign(ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())  # type: ignore[union-attr,call-arg,arg-type]
            encrypted_msg = EncryptedMessage(ciphertext=ciphertext, session_key=encrypted_session_key, nonce=nonce, signature=signature, sender_id=sender_id)
            logger.info('Encrypted message from %s to %s', sender_id, recipient_id)
            return encrypted_msg
        except Exception as e:
            logger.error('Error encrypting message: %s', e)
            return None

    def decrypt_message(self, encrypted_msg: EncryptedMessage, recipient_id: str) -> dict[str, Any] | None:
        """Decrypt a message"""
        try:
            if recipient_id not in self.key_pairs or not self.key_pairs[recipient_id].private_key:
                logger.error('No private key for recipient %s', recipient_id)
                return None
            recipient_private_key = serialization.load_pem_private_key(self.key_pairs[recipient_id].private_key, password=None, backend=default_backend())  # type: ignore[arg-type]
            session_key = recipient_private_key.decrypt(encrypted_msg.session_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))  # type: ignore[union-attr]
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            aesgcm = AESGCM(session_key)
            message_json = aesgcm.decrypt(encrypted_msg.nonce, encrypted_msg.ciphertext, None)
            if encrypted_msg.sender_id in self.key_pairs:
                sender_public_key = serialization.load_pem_public_key(self.key_pairs[encrypted_msg.sender_id].public_key, backend=default_backend())
                try:
                    sender_public_key.verify(encrypted_msg.signature, encrypted_msg.ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())  # type: ignore[union-attr,call-arg,arg-type]
                    logger.info('Signature verified for message from %s', encrypted_msg.sender_id)
                except Exception as e:
                    logger.warning('Signature verification failed: %s', e)
            message: dict[str, Any] = json.loads(message_json.decode('utf-8'))
            logger.info('Decrypted message from %s to %s', encrypted_msg.sender_id, recipient_id)
            return message
        except Exception as e:
            logger.error('Error decrypting message: %s', e)
            return None

    def verify_signature(self, encrypted_msg: EncryptedMessage, sender_id: str) -> bool:
        """Verify message signature without decrypting"""
        try:
            if sender_id not in self.key_pairs:
                logger.error('No public key for sender %s', sender_id)
                return False
            sender_public_key = serialization.load_pem_public_key(self.key_pairs[sender_id].public_key, backend=default_backend())
            sender_public_key.verify(encrypted_msg.signature, encrypted_msg.ciphertext, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())  # type: ignore[union-attr,call-arg,arg-type]
            logger.info('Signature verified for message from %s', sender_id)
            return True
        except Exception as e:
            logger.warning('Signature verification failed: %s', e)
            return False

    def rotate_key_pair(self, agent_id: str) -> AgentKeyPair | None:
        """Rotate key pair for an agent"""
        if agent_id in self.key_pairs:
            old_key = self.key_pairs[agent_id]
            backup_path = os.path.join(self.keys_dir, f'{agent_id}_old_{old_key.key_id}.json')
            with open(backup_path, 'w') as f:
                json.dump(old_key.to_dict(), f, indent=2)
            new_key = self.generate_key_pair(agent_id)
            logger.info('Rotated key pair for agent %s', agent_id)
            return new_key
        return None

    def _save_key_pair(self, key_pair: AgentKeyPair) -> None:
        """Save key pair to disk"""
        key_path = os.path.join(self.keys_dir, f'{key_pair.agent_id}.json')
        with open(key_path, 'w') as f:
            json.dump(key_pair.to_dict(), f, indent=2)
        os.chmod(key_path, 384)

    def _load_keys(self) -> None:
        """Load key pairs from disk"""
        try:
            for filename in os.listdir(self.keys_dir):
                if filename.endswith('.json') and (not filename.endswith('_old_')):
                    filepath = os.path.join(self.keys_dir, filename)
                    with open(filepath) as f:
                        data = json.load(f)
                        key_pair = AgentKeyPair.from_dict(data)
                        self.key_pairs[key_pair.agent_id] = key_pair
            logger.info('Loaded %s key pairs', len(self.key_pairs))
        except Exception as e:
            logger.error('Error loading keys: %s', e)
_encryptor: MessageEncryptor | None = None

def get_encryptor() -> MessageEncryptor:
    """Get global encryptor instance"""
    global _encryptor
    if _encryptor is None:
        _encryptor = MessageEncryptor()
    return _encryptor
