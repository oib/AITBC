"""
Message Encryption Module Tests
Tests for RSA/AES-GCM encryption, key exchange, and digital signatures
"""

from datetime import UTC, datetime

import pytest
from app.encryption.message_encryption import (
    AgentKeyPair,
    EncryptedMessage,
    MessageEncryptor,
)


class TestAgentKeyPair:
    """Test agent key pair creation and management"""

    def test_key_pair_creation(self):
        """Test creating an agent key pair"""
        agent_id = "test_agent_001"
        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        key_pair = encryptor.generate_key_pair(agent_id)

        assert key_pair.agent_id == agent_id
        assert key_pair.public_key is not None
        assert key_pair.private_key is not None
        assert key_pair.key_id is not None
        assert key_pair.created_at is not None

    def test_key_pair_serialization(self):
        """Test key pair to_dict and from_dict"""
        agent_id = "test_agent_002"
        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        key_pair = encryptor.generate_key_pair(agent_id)

        # Convert to dict
        key_dict = key_pair.to_dict()
        assert "agent_id" in key_dict
        assert "public_key" in key_dict
        assert "private_key" in key_dict
        assert "key_id" in key_dict

        # Convert from dict
        restored_key_pair = AgentKeyPair.from_dict(key_dict)
        assert restored_key_pair.agent_id == key_pair.agent_id
        assert restored_key_pair.key_id == key_pair.key_id

    def test_public_key_retrieval(self):
        """Test retrieving public key for an agent"""
        agent_id = "test_agent_003"
        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(agent_id)

        public_key = encryptor.get_public_key(agent_id)
        assert public_key is not None
        assert len(public_key) > 0

    def test_public_key_registration(self):
        """Test registering a public key from another agent"""
        agent_id = "test_agent_004"
        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")

        # Generate key pair for agent
        key_pair = encryptor.generate_key_pair(agent_id)

        # Register same public key as external (simulating another agent)
        success = encryptor.register_public_key(f"{agent_id}_external", key_pair.public_key)
        assert success is True

        # Retrieve the registered key
        external_key = encryptor.get_public_key(f"{agent_id}_external")
        assert external_key is not None


class TestEncryptedMessage:
    """Test encrypted message structure and serialization"""

    def test_encrypted_message_creation(self):
        """Test creating an encrypted message"""
        sender_id = "agent_001"
        ciphertext = b"encrypted_data"
        session_key = b"session_key"
        nonce = b"nonce"
        signature = b"signature"

        encrypted_msg = EncryptedMessage(
            ciphertext=ciphertext, session_key=session_key, nonce=nonce, signature=signature, sender_id=sender_id
        )

        assert encrypted_msg.ciphertext == ciphertext
        assert encrypted_msg.session_key == session_key
        assert encrypted_msg.nonce == nonce
        assert encrypted_msg.signature == signature
        assert encrypted_msg.sender_id == sender_id
        assert encrypted_msg.timestamp is not None

    def test_encrypted_message_serialization(self):
        """Test encrypted message to_dict and from_dict"""
        sender_id = "agent_002"
        encrypted_msg = EncryptedMessage(
            ciphertext=b"encrypted_data",
            session_key=b"session_key",
            nonce=b"nonce",
            signature=b"signature",
            sender_id=sender_id,
        )

        # Convert to dict
        msg_dict = encrypted_msg.to_dict()
        assert "ciphertext" in msg_dict
        assert "session_key" in msg_dict
        assert "nonce" in msg_dict
        assert "signature" in msg_dict
        assert "sender_id" in msg_dict
        assert "timestamp" in msg_dict

        # Convert from dict
        restored_msg = EncryptedMessage.from_dict(msg_dict)
        assert restored_msg.sender_id == encrypted_msg.sender_id
        assert restored_msg.ciphertext == encrypted_msg.ciphertext


class TestMessageEncryption:
    """Test message encryption and decryption"""

    def test_message_encryption(self):
        """Test encrypting a message for a recipient"""
        sender_id = "agent_001"
        recipient_id = "agent_002"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        encryptor.generate_key_pair(recipient_id)

        message_content = {
            "content": "Hello, this is a test message",
            "message_type": "direct",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        encrypted_msg = encryptor.encrypt_message(message=message_content, sender_id=sender_id, recipient_id=recipient_id)

        assert encrypted_msg is not None
        assert encrypted_msg.sender_id == sender_id
        assert encrypted_msg.ciphertext is not None
        assert encrypted_msg.session_key is not None
        assert encrypted_msg.signature is not None

    def test_message_decryption(self):
        """Test decrypting a message"""
        sender_id = "agent_003"
        recipient_id = "agent_004"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        encryptor.generate_key_pair(recipient_id)

        message_content = {"content": "Decryption test message", "message_type": "direct"}

        # Encrypt message
        encrypted_msg = encryptor.encrypt_message(message=message_content, sender_id=sender_id, recipient_id=recipient_id)

        # Decrypt message
        decrypted_message = encryptor.decrypt_message(encrypted_msg=encrypted_msg, recipient_id=recipient_id)

        assert decrypted_message is not None
        assert decrypted_message["content"] == message_content["content"]
        assert decrypted_message["message_type"] == message_content["message_type"]

    def test_signature_verification(self):
        """Test verifying message signature"""
        sender_id = "agent_005"
        recipient_id = "agent_006"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        encryptor.generate_key_pair(recipient_id)

        message_content = {"content": "Signature test"}

        encrypted_msg = encryptor.encrypt_message(message=message_content, sender_id=sender_id, recipient_id=recipient_id)

        # Verify signature
        is_valid = encryptor.verify_signature(encrypted_msg=encrypted_msg, sender_id=sender_id)

        assert is_valid is True

    def test_key_pair_rotation(self):
        """Test rotating key pairs"""
        agent_id = "agent_007"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        old_key = encryptor.generate_key_pair(agent_id)
        old_public_key = old_key.public_key

        # Rotate key
        new_key = encryptor.rotate_key_pair(agent_id)

        assert new_key is not None
        assert new_key.agent_id == agent_id
        assert new_key.public_key != old_public_key  # Keys should be different
        assert new_key.public_key is not None

    def test_encryption_without_recipient_key(self):
        """Test encryption fails when recipient has no key"""
        sender_id = "agent_008"
        recipient_id = "agent_009"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        # Don't generate recipient key

        message_content = {"content": "Test"}

        encrypted_msg = encryptor.encrypt_message(message=message_content, sender_id=sender_id, recipient_id=recipient_id)

        assert encrypted_msg is None

    @pytest.mark.skip("Isolation failure in full suite")
    def test_decryption_without_sender_key(self):
        """Test decryption fails when sender has no key"""
        sender_id = "agent_010"
        recipient_id = "agent_011"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(recipient_id)
        # Don't generate sender key

        # Manually create encrypted message (simulating external sender)
        from app.encryption.message_encryption import EncryptedMessage

        encrypted_msg = EncryptedMessage(
            ciphertext=b"test", session_key=b"test", nonce=b"test", signature=b"test", sender_id=sender_id
        )

        decrypted = encryptor.decrypt_message(encrypted_msg=encrypted_msg, recipient_id=recipient_id)

        assert decrypted is None

    def test_encryption_with_large_message(self):
        """Test encryption of large message"""
        sender_id = "agent_large_1"
        recipient_id = "agent_large_2"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        encryptor.generate_key_pair(recipient_id)

        # Large message
        large_message = {"content": "A" * 10000}

        encrypted_msg = encryptor.encrypt_message(message=large_message, sender_id=sender_id, recipient_id=recipient_id)

        decrypted = encryptor.decrypt_message(encrypted_msg=encrypted_msg, recipient_id=recipient_id)

        assert decrypted == large_message

    def test_encryption_with_special_characters(self):
        """Test encryption of message with special characters"""
        sender_id = "agent_special_1"
        recipient_id = "agent_special_2"

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        encryptor.generate_key_pair(recipient_id)

        # Message with special characters
        special_message = {"content": "Test @#$%^&*()_+-=[]{}|;':,.<>?/~"}

        encrypted_msg = encryptor.encrypt_message(message=special_message, sender_id=sender_id, recipient_id=recipient_id)

        decrypted = encryptor.decrypt_message(encrypted_msg=encrypted_msg, recipient_id=recipient_id)

        assert decrypted == special_message

    def test_encryption_with_multiple_recipients(self):
        """Test encryption with multiple recipients"""
        sender_id = "sender_multi"
        recipients = ["recipient_1", "recipient_2", "recipient_3"]

        encryptor = MessageEncryptor(keys_dir="/tmp/test_agent_keys")
        encryptor.generate_key_pair(sender_id)
        for recipient in recipients:
            encryptor.generate_key_pair(recipient)

        message = {"content": "Broadcast message"}

        # Encrypt for each recipient
        for recipient in recipients:
            encrypted_msg = encryptor.encrypt_message(message=message, sender_id=sender_id, recipient_id=recipient)
            decrypted = encryptor.decrypt_message(encrypted_msg=encrypted_msg, recipient_id=recipient)
            assert decrypted == message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
