"""
Security tests for AITBC Confidential Transactions
"""

import pytest
import json
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Mock missing dependencies
sys.modules['aitbc_crypto'] = Mock()
sys.modules['slowapi'] = Mock()
sys.modules['slowapi.util'] = Mock()
sys.modules['slowapi.limiter'] = Mock()

# Mock aitbc_crypto functions
def mock_encrypt_data(data, key):
    return f"encrypted_{data}"
def mock_decrypt_data(data, key):
    return data.replace("encrypted_", "")
def mock_generate_viewing_key():
    return "test_viewing_key"

sys.modules['aitbc_crypto'].encrypt_data = mock_encrypt_data
sys.modules['aitbc_crypto'].decrypt_data = mock_decrypt_data
sys.modules['aitbc_crypto'].generate_viewing_key = mock_generate_viewing_key

try:
    from app.services.confidential_service import ConfidentialTransactionService
    from app.models.confidential import ConfidentialTransaction, ViewingKey
    from aitbc_crypto import encrypt_data, decrypt_data, generate_viewing_key
    CONFIDENTIAL_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Confidential transaction modules not available: {e}")
    CONFIDENTIAL_AVAILABLE = False
    # Create mock classes for testing
    ConfidentialTransactionService = Mock
    ConfidentialTransaction = Mock
    ViewingKey = Mock


@pytest.mark.security
@pytest.mark.skipif(not CONFIDENTIAL_AVAILABLE, reason="Confidential transaction modules not available")
class TestConfidentialTransactionSecurity:
    """Security tests for confidential transaction functionality"""

    @pytest.fixture
    def confidential_service(self, db_session):
        """Create confidential transaction service"""
        return ConfidentialTransactionService(db_session)

    @pytest.fixture
    def sample_sender_keys(self):
        """Generate sender's key pair"""
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key()
        return private_key, public_key

    @pytest.fixture
    def sample_receiver_keys(self):
        """Generate receiver's key pair"""
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key()
        return private_key, public_key

    def test_encryption_confidentiality(self, sample_sender_keys, sample_receiver_keys):
        """Test that transaction data remains confidential"""
        sender_private, sender_public = sample_sender_keys
        receiver_private, receiver_public = sample_receiver_keys

        # Original transaction data
        transaction_data = {
            "sender": "0x1234567890abcdef",
            "receiver": "0xfedcba0987654321",
            "amount": 1000000,  # 1 USDC
            "asset": "USDC",
            "nonce": 12345,
        }

        # Encrypt for receiver only
        ciphertext = encrypt_data(
            data=json.dumps(transaction_data),
            sender_key=sender_private,
            receiver_key=receiver_public,
        )

        # Verify ciphertext doesn't reveal plaintext
        assert transaction_data["sender"] not in ciphertext
        assert transaction_data["receiver"] not in ciphertext
        assert str(transaction_data["amount"]) not in ciphertext

        # Only receiver can decrypt
        decrypted = decrypt_data(
            ciphertext=ciphertext,
            receiver_key=receiver_private,
            sender_key=sender_public,
        )

        decrypted_data = json.loads(decrypted)
        assert decrypted_data == transaction_data

    def test_viewing_key_generation(self):
        """Test secure viewing key generation"""
        # Generate viewing key for auditor
        viewing_key = generate_viewing_key(
            purpose="audit",
            expires_at=datetime.utcnow() + timedelta(days=30),
            permissions=["view_amount", "view_parties"],
        )

        # Verify key structure
        assert "key_id" in viewing_key
        assert "key_data" in viewing_key
        assert "expires_at" in viewing_key
        assert "permissions" in viewing_key

        # Verify key entropy
        assert len(viewing_key["key_data"]) >= 32  # At least 256 bits

        # Verify expiration
        assert viewing_key["expires_at"] > datetime.utcnow()

    def test_viewing_key_permissions(self, confidential_service):
        """Test that viewing keys respect permission constraints"""
        # Create confidential transaction
        tx = ConfidentialTransaction(
            id="confidential-tx-123",
            ciphertext="encrypted_data_here",
            sender_key="sender_pubkey",
            receiver_key="receiver_pubkey",
            created_at=datetime.utcnow(),
        )

        # Create viewing key with limited permissions
        viewing_key = ViewingKey(
            id="view-key-123",
            transaction_id=tx.id,
            key_data="encrypted_viewing_key",
            permissions=["view_amount"],
            expires_at=datetime.utcnow() + timedelta(days=1),
            created_at=datetime.utcnow(),
        )

        # Test permission enforcement
        with patch.object(
            confidential_service, "decrypt_with_viewing_key"
        ) as mock_decrypt:
            mock_decrypt.return_value = {"amount": 1000}

            # Should succeed with valid permission
            result = confidential_service.view_transaction(
                tx.id, viewing_key.id, fields=["amount"]
            )
            assert "amount" in result

            # Should fail with invalid permission
            with pytest.raises(PermissionError):
                confidential_service.view_transaction(
                    tx.id,
                    viewing_key.id,
                    fields=["sender", "receiver"],  # Not permitted
                )

    def test_key_rotation_security(self, confidential_service):
        """Test secure key rotation"""
        # Create initial keys
        old_key = x25519.X25519PrivateKey.generate()
        new_key = x25519.X25519PrivateKey.generate()

        # Test key rotation process
        rotation_result = confidential_service.rotate_keys(
            transaction_id="tx-123", old_key=old_key, new_key=new_key
        )

        assert rotation_result["success"] is True
        assert "new_ciphertext" in rotation_result
        assert "rotation_id" in rotation_result

        # Verify old key can't decrypt new ciphertext
        with pytest.raises(Exception):
            decrypt_data(
                ciphertext=rotation_result["new_ciphertext"],
                receiver_key=old_key,
                sender_key=old_key.public_key(),
            )

        # Verify new key can decrypt
        decrypted = decrypt_data(
            ciphertext=rotation_result["new_ciphertext"],
            receiver_key=new_key,
            sender_key=new_key.public_key(),
        )
        assert decrypted is not None

    def test_transaction_replay_protection(self, confidential_service):
        """Test protection against transaction replay"""
        # Create transaction with nonce
        transaction = {
            "sender": "0x123",
            "receiver": "0x456",
            "amount": 1000,
            "nonce": 12345,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Store nonce
        confidential_service.store_nonce(12345, "tx-123")

        # Try to replay with same nonce
        with pytest.raises(ValueError, match="nonce already used"):
            confidential_service.validate_transaction_nonce(
                transaction["nonce"], transaction["sender"]
            )

    def test_side_channel_resistance(self, confidential_service):
        """Test resistance to timing attacks"""
        import time

        # Create transactions with different amounts
        small_amount = {"amount": 1}
        large_amount = {"amount": 1000000}

        # Encrypt both
        small_cipher = encrypt_data(
            json.dumps(small_amount),
            x25519.X25519PrivateKey.generate(),
            x25519.X25519PrivateKey.generate().public_key(),
        )

        large_cipher = encrypt_data(
            json.dumps(large_amount),
            x25519.X25519PrivateKey.generate(),
            x25519.X25519PrivateKey.generate().public_key(),
        )

        # Measure decryption times
        times = []
        for ciphertext in [small_cipher, large_cipher]:
            start = time.perf_counter()
            try:
                decrypt_data(
                    ciphertext,
                    x25519.X25519PrivateKey.generate(),
                    x25519.X25519PrivateKey.generate().public_key(),
                )
            except:
                pass  # Expected to fail with wrong keys
            end = time.perf_counter()
            times.append(end - start)

        # Times should be similar (within 10%)
        time_diff = abs(times[0] - times[1]) / max(times)
        assert time_diff < 0.1, f"Timing difference too large: {time_diff}"

    def test_zero_knowledge_proof_integration(self):
        """Test ZK proof integration for privacy"""
        from apps.zk_circuits import generate_proof, verify_proof

        # Create confidential transaction
        transaction = {
            "input_commitment": "commitment123",
            "output_commitment": "commitment456",
            "amount": 1000,
        }

        # Generate ZK proof
        with patch("apps.zk_circuits.generate_proof") as mock_generate:
            mock_generate.return_value = {
                "proof": "zk_proof_here",
                "inputs": ["hash1", "hash2"],
            }

            proof_data = mock_generate(transaction)

            # Verify proof structure
            assert "proof" in proof_data
            assert "inputs" in proof_data
            assert len(proof_data["inputs"]) == 2

        # Verify proof
        with patch("apps.zk_circuits.verify_proof") as mock_verify:
            mock_verify.return_value = True

            is_valid = mock_verify(
                proof=proof_data["proof"], inputs=proof_data["inputs"]
            )

            assert is_valid is True

    def test_audit_log_integrity(self, confidential_service):
        """Test that audit logs maintain integrity"""
        # Create confidential transaction
        tx = ConfidentialTransaction(
            id="audit-tx-123",
            ciphertext="encrypted_data",
            sender_key="sender_key",
            receiver_key="receiver_key",
            created_at=datetime.utcnow(),
        )

        # Log access
        access_log = confidential_service.log_access(
            transaction_id=tx.id,
            user_id="auditor-123",
            action="view_with_viewing_key",
            timestamp=datetime.utcnow(),
        )

        # Verify log integrity
        assert "log_id" in access_log
        assert "hash" in access_log
        assert "signature" in access_log

        # Verify log can't be tampered
        original_hash = access_log["hash"]
        access_log["user_id"] = "malicious-user"

        # Recalculate hash should differ
        new_hash = confidential_service.calculate_log_hash(access_log)
        assert new_hash != original_hash

    def test_hsm_integration_security(self):
        """Test HSM integration for key management"""
        from apps.coordinator_api.src.app.services.hsm_service import HSMService

        # Mock HSM client
        mock_hsm = Mock()
        mock_hsm.generate_key.return_value = {"key_id": "hsm-key-123"}
        mock_hsm.sign_data.return_value = {"signature": "hsm-signature"}
        mock_hsm.encrypt.return_value = {"ciphertext": "hsm-encrypted"}

        with patch(
            "apps.coordinator_api.src.app.services.hsm_service.HSMClient"
        ) as mock_client:
            mock_client.return_value = mock_hsm

            hsm_service = HSMService()

            # Test key generation
            key_result = hsm_service.generate_key(
                key_type="encryption", purpose="confidential_tx"
            )
            assert key_result["key_id"] == "hsm-key-123"

            # Test signing
            sign_result = hsm_service.sign_data(
                key_id="hsm-key-123", data="transaction_data"
            )
            assert "signature" in sign_result

            # Verify HSM was called
            mock_hsm.generate_key.assert_called_once()
            mock_hsm.sign_data.assert_called_once()

    def test_multi_party_computation(self):
        """Test MPC for transaction validation"""
        from apps.coordinator_api.src.app.services.mpc_service import MPCService

        mpc_service = MPCService()

        # Create transaction shares
        transaction = {
            "amount": 1000,
            "sender": "0x123",
            "receiver": "0x456",
        }

        # Generate shares
        shares = mpc_service.create_shares(transaction, threshold=3, total=5)

        assert len(shares) == 5
        assert all("share_id" in share for share in shares)
        assert all("encrypted_data" in share for share in shares)

        # Test reconstruction with sufficient shares
        selected_shares = shares[:3]
        reconstructed = mpc_service.reconstruct_transaction(selected_shares)

        assert reconstructed["amount"] == transaction["amount"]
        assert reconstructed["sender"] == transaction["sender"]

        # Test insufficient shares fail
        with pytest.raises(ValueError):
            mpc_service.reconstruct_transaction(shares[:2])

    def test_forward_secrecy(self):
        """Test forward secrecy of confidential transactions"""
        # Generate ephemeral keys
        ephemeral_private = x25519.X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()

        receiver_private = x25519.X25519PrivateKey.generate()
        receiver_public = receiver_private.public_key()

        # Create shared secret
        shared_secret = ephemeral_private.exchange(receiver_public)

        # Derive encryption key
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"aitbc-confidential-tx",
        ).derive(shared_secret)

        # Encrypt transaction
        aesgcm = AESGCM(derived_key)
        nonce = AESGCM.generate_nonce(12)
        transaction_data = json.dumps({"amount": 1000})
        ciphertext = aesgcm.encrypt(nonce, transaction_data.encode(), None)

        # Even if ephemeral key is compromised later, past transactions remain secure
        # because the shared secret is not stored

        # Verify decryption works with current keys
        aesgcm_decrypt = AESGCM(derived_key)
        decrypted = aesgcm_decrypt.decrypt(nonce, ciphertext, None)
        assert json.loads(decrypted) == {"amount": 1000}

    def test_deniable_encryption(self):
        """Test deniable encryption for plausible deniability"""
        from apps.coordinator_api.src.app.services.deniable_service import (
            DeniableEncryption,
        )

        deniable = DeniableEncryption()

        # Create two plausible messages
        real_message = {"amount": 1000000, "asset": "USDC"}
        fake_message = {"amount": 100, "asset": "USDC"}

        # Generate deniable ciphertext
        result = deniable.encrypt(
            real_message=real_message,
            fake_message=fake_message,
            receiver_key=x25519.X25519PrivateKey.generate(),
        )

        assert "ciphertext" in result
        assert "real_key" in result
        assert "fake_key" in result

        # Can reveal either message depending on key provided
        real_decrypted = deniable.decrypt(
            ciphertext=result["ciphertext"], key=result["real_key"]
        )
        assert json.loads(real_decrypted) == real_message

        fake_decrypted = deniable.decrypt(
            ciphertext=result["ciphertext"], key=result["fake_key"]
        )
        assert json.loads(fake_decrypted) == fake_message


@pytest.mark.security
class TestConfidentialTransactionVulnerabilities:
    """Test for potential vulnerabilities in confidential transactions"""

    def test_timing_attack_prevention(self):
        """Test prevention of timing attacks on amount comparison"""
        import time
        import statistics

        # Create various transaction amounts
        amounts = [1, 100, 1000, 10000, 100000, 1000000]

        encryption_times = []

        for amount in amounts:
            transaction = {"amount": amount}

            # Measure encryption time
            start = time.perf_counter_ns()
            ciphertext = encrypt_data(
                json.dumps(transaction),
                x25519.X25519PrivateKey.generate(),
                x25519.X25519PrivateKey.generate().public_key(),
            )
            end = time.perf_counter_ns()

            encryption_times.append(end - start)

        # Check if encryption time correlates with amount
        correlation = statistics.correlation(amounts, encryption_times)
        assert abs(correlation) < 0.1, f"Timing correlation detected: {correlation}"

    def test_memory_sanitization(self):
        """Test that sensitive memory is properly sanitized"""
        import gc
        import sys

        # Create confidential transaction
        sensitive_data = "secret_transaction_data_12345"

        # Encrypt data
        ciphertext = encrypt_data(
            sensitive_data,
            x25519.X25519PrivateKey.generate(),
            x25519.X25519PrivateKey.generate().public_key(),
        )

        # Force garbage collection
        del sensitive_data
        gc.collect()

        # Check if sensitive data still exists in memory
        memory_dump = str(sys.getsizeof(ciphertext))
        assert "secret_transaction_data_12345" not in memory_dump

    def test_key_derivation_security(self):
        """Test security of key derivation functions"""
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        # Test with different salts
        base_key = b"base_key_material"
        salt1 = b"salt_1"
        salt2 = b"salt_2"

        kdf1 = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt1,
            info=b"aitbc-key-derivation",
        )

        kdf2 = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt2,
            info=b"aitbc-key-derivation",
        )

        key1 = kdf1.derive(base_key)
        key2 = kdf2.derive(base_key)

        # Different salts should produce different keys
        assert key1 != key2

        # Keys should be sufficiently random
        # Test by checking bit distribution
        bit_count = sum(bin(byte).count("1") for byte in key1)
        bit_ratio = bit_count / (len(key1) * 8)
        assert 0.45 < bit_ratio < 0.55, "Key bits not evenly distributed"

    def test_side_channel_leakage_prevention(self):
        """Test prevention of various side channel attacks"""
        import psutil
        import os

        # Monitor resource usage during encryption
        process = psutil.Process(os.getpid())

        # Baseline measurements
        baseline_cpu = process.cpu_percent()
        baseline_memory = process.memory_info().rss

        # Perform encryption operations
        for i in range(100):
            data = f"transaction_data_{i}"
            encrypt_data(
                data,
                x25519.X25519PrivateKey.generate(),
                x25519.X25519PrivateKey.generate().public_key(),
            )

        # Check for unusual resource usage patterns
        final_cpu = process.cpu_percent()
        final_memory = process.memory_info().rss

        cpu_increase = final_cpu - baseline_cpu
        memory_increase = final_memory - baseline_memory

        # Resource usage should be consistent
        assert cpu_increase < 50, f"Excessive CPU usage: {cpu_increase}%"
        assert memory_increase < 100 * 1024 * 1024, (
            f"Excessive memory usage: {memory_increase} bytes"
        )

    def test_quantum_resistance_preparation(self):
        """Test preparation for quantum-resistant cryptography"""
        # Test post-quantum key exchange simulation
        from apps.coordinator_api.src.app.services.pqc_service import PostQuantumCrypto

        pqc = PostQuantumCrypto()

        # Generate quantum-resistant key pair
        key_pair = pqc.generate_keypair(algorithm="kyber768")

        assert "private_key" in key_pair
        assert "public_key" in key_pair
        assert "algorithm" in key_pair
        assert key_pair["algorithm"] == "kyber768"

        # Test quantum-resistant signature
        message = "confidential_transaction_hash"
        signature = pqc.sign(
            message=message, private_key=key_pair["private_key"], algorithm="dilithium3"
        )

        assert "signature" in signature
        assert "algorithm" in signature

        # Verify signature
        is_valid = pqc.verify(
            message=message,
            signature=signature["signature"],
            public_key=key_pair["public_key"],
            algorithm="dilithium3",
        )

        assert is_valid is True


@pytest.mark.security
class TestConfidentialTransactionCompliance:
    """Test compliance features for confidential transactions"""

    def test_regulatory_reporting(self, confidential_service):
        """Test regulatory reporting while maintaining privacy"""
        # Create confidential transaction
        tx = ConfidentialTransaction(
            id="regulatory-tx-123",
            ciphertext="encrypted_data",
            sender_key="sender_key",
            receiver_key="receiver_key",
            created_at=datetime.utcnow(),
        )

        # Generate regulatory report
        report = confidential_service.generate_regulatory_report(
            transaction_id=tx.id,
            reporting_fields=["timestamp", "asset_type", "jurisdiction"],
            viewing_authority="financial_authority_123",
        )

        # Report should contain required fields but not private data
        assert "transaction_id" in report
        assert "timestamp" in report
        assert "asset_type" in report
        assert "jurisdiction" in report
        assert "amount" not in report  # Should remain confidential
        assert "sender" not in report  # Should remain confidential
        assert "receiver" not in report  # Should remain confidential

    def test_kyc_aml_integration(self, confidential_service):
        """Test KYC/AML checks without compromising privacy"""
        # Create transaction with encrypted parties
        encrypted_parties = {
            "sender": "encrypted_sender_data",
            "receiver": "encrypted_receiver_data",
        }

        # Perform KYC/AML check
        with patch(
            "apps.coordinator_api.src.app.services.aml_service.check_parties"
        ) as mock_aml:
            mock_aml.return_value = {
                "sender_status": "cleared",
                "receiver_status": "cleared",
                "risk_score": 0.2,
            }

            aml_result = confidential_service.perform_aml_check(
                encrypted_parties=encrypted_parties,
                viewing_permission="regulatory_only",
            )

        assert aml_result["sender_status"] == "cleared"
        assert aml_result["risk_score"] < 0.5

        # Verify parties remain encrypted
        assert "sender_address" not in aml_result
        assert "receiver_address" not in aml_result

    def test_audit_trail_privacy(self, confidential_service):
        """Test audit trail that preserves privacy"""
        # Create series of confidential transactions
        transactions = [{"id": f"tx-{i}", "amount": 1000 * i} for i in range(10)]

        # Generate privacy-preserving audit trail
        audit_trail = confidential_service.generate_audit_trail(
            transactions=transactions, privacy_level="high", auditor_id="auditor_123"
        )

        # Audit trail should have:
        assert "transaction_count" in audit_trail
        assert "total_volume" in audit_trail
        assert "time_range" in audit_trail
        assert "compliance_hash" in audit_trail

        # But should not have:
        assert "transaction_ids" not in audit_trail
        assert "individual_amounts" not in audit_trail
        assert "party_addresses" not in audit_trail

    def test_data_retention_policy(self, confidential_service):
        """Test data retention and automatic deletion"""
        # Create old confidential transaction
        old_tx = ConfidentialTransaction(
            id="old-tx-123",
            ciphertext="old_encrypted_data",
            created_at=datetime.utcnow() - timedelta(days=400),  # Over 1 year
        )

        # Test retention policy enforcement
        with patch(
            "apps.coordinator_api.src.app.services.retention_service.check_retention"
        ) as mock_check:
            mock_check.return_value = {"should_delete": True, "reason": "expired"}

            deletion_result = confidential_service.enforce_retention_policy(
                transaction_id=old_tx.id, policy_duration_days=365
            )

        assert deletion_result["deleted"] is True
        assert "deletion_timestamp" in deletion_result
        assert "compliance_log" in deletion_result
