"""
End-to-end tests for AITBC Wallet Daemon
"""

import pytest
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
import requests
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from packages.py.aitbc_crypto import sign_receipt, verify_receipt
from packages.py.aitbc_sdk import AITBCClient


@pytest.mark.e2e
class TestWalletDaemonE2E:
    """End-to-end tests for wallet daemon functionality"""
    
    @pytest.fixture
    def wallet_base_url(self):
        """Wallet daemon base URL"""
        return "http://localhost:8002"
    
    @pytest.fixture
    def coordinator_base_url(self):
        """Coordinator API base URL"""
        return "http://localhost:8001"
    
    @pytest.fixture
    def test_wallet_data(self, temp_directory):
        """Create test wallet data"""
        wallet_path = Path(temp_directory) / "test_wallet.json"
        wallet_data = {
            "id": "test-wallet-123",
            "name": "Test Wallet",
            "created_at": datetime.utcnow().isoformat(),
            "accounts": [
                {
                    "address": "0x1234567890abcdef",
                    "public_key": "test-public-key",
                    "encrypted_private_key": "encrypted-key-here",
                }
            ],
        }
        
        with open(wallet_path, "w") as f:
            json.dump(wallet_data, f)
        
        return wallet_path
    
    def test_wallet_creation_flow(self, wallet_base_url, temp_directory):
        """Test complete wallet creation flow"""
        # Step 1: Create new wallet
        create_data = {
            "name": "E2E Test Wallet",
            "password": "test-password-123",
            "keystore_path": str(temp_directory),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets", json=create_data)
        assert response.status_code == 201
        
        wallet = response.json()
        assert wallet["name"] == "E2E Test Wallet"
        assert "id" in wallet
        assert "accounts" in wallet
        assert len(wallet["accounts"]) == 1
        
        account = wallet["accounts"][0]
        assert "address" in account
        assert "public_key" in account
        assert "encrypted_private_key" not in account  # Should not be exposed
        
        # Step 2: List wallets
        response = requests.get(f"{wallet_base_url}/v1/wallets")
        assert response.status_code == 200
        
        wallets = response.json()
        assert any(w["id"] == wallet["id"] for w in wallets)
        
        # Step 3: Get wallet details
        response = requests.get(f"{wallet_base_url}/v1/wallets/{wallet['id']}")
        assert response.status_code == 200
        
        wallet_details = response.json()
        assert wallet_details["id"] == wallet["id"]
        assert len(wallet_details["accounts"]) == 1
    
    def test_wallet_unlock_flow(self, wallet_base_url, test_wallet_data):
        """Test wallet unlock and session management"""
        # Step 1: Unlock wallet
        unlock_data = {
            "password": "test-password-123",
            "keystore_path": str(test_wallet_data),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        assert response.status_code == 200
        
        unlock_result = response.json()
        assert "session_token" in unlock_result
        assert "expires_at" in unlock_result
        
        session_token = unlock_result["session_token"]
        
        # Step 2: Use session for signing
        headers = {"Authorization": f"Bearer {session_token}"}
        
        sign_data = {
            "message": "Test message to sign",
            "account_address": "0x1234567890abcdef",
        }
        
        response = requests.post(
            f"{wallet_base_url}/v1/sign",
            json=sign_data,
            headers=headers
        )
        assert response.status_code == 200
        
        signature = response.json()
        assert "signature" in signature
        assert "public_key" in signature
        
        # Step 3: Lock wallet
        response = requests.post(
            f"{wallet_base_url}/v1/wallets/lock",
            headers=headers
        )
        assert response.status_code == 200
        
        # Step 4: Verify session is invalid
        response = requests.post(
            f"{wallet_base_url}/v1/sign",
            json=sign_data,
            headers=headers
        )
        assert response.status_code == 401
    
    def test_receipt_verification_flow(self, wallet_base_url, coordinator_base_url, signed_receipt):
        """Test receipt verification workflow"""
        # Step 1: Submit receipt to wallet for verification
        verify_data = {
            "receipt": signed_receipt,
        }
        
        response = requests.post(
            f"{wallet_base_url}/v1/receipts/verify",
            json=verify_data
        )
        assert response.status_code == 200
        
        verification = response.json()
        assert "valid" in verification
        assert verification["valid"] is True
        assert "verifications" in verification
        
        # Check verification details
        verifications = verification["verifications"]
        assert "miner_signature" in verifications
        assert "coordinator_signature" in verifications
        assert verifications["miner_signature"]["valid"] is True
        assert verifications["coordinator_signature"]["valid"] is True
        
        # Step 2: Get receipt history
        response = requests.get(f"{wallet_base_url}/v1/receipts")
        assert response.status_code == 200
        
        receipts = response.json()
        assert len(receipts) > 0
        assert any(r["id"] == signed_receipt["id"] for r in receipts)
    
    def test_cross_component_integration(self, wallet_base_url, coordinator_base_url):
        """Test integration between wallet and coordinator"""
        # Step 1: Create job via coordinator
        job_data = {
            "job_type": "ai_inference",
            "parameters": {
                "model": "gpt-3.5-turbo",
                "prompt": "Test prompt",
            },
        }
        
        response = requests.post(
            f"{coordinator_base_url}/v1/jobs",
            json=job_data,
            headers={"X-Tenant-ID": "test-tenant"}
        )
        assert response.status_code == 201
        
        job = response.json()
        job_id = job["id"]
        
        # Step 2: Mock job completion and receipt creation
        # In real test, this would involve actual miner execution
        receipt_data = {
            "id": f"receipt-{job_id}",
            "job_id": job_id,
            "miner_id": "test-miner",
            "coordinator_id": "test-coordinator",
            "timestamp": datetime.utcnow().isoformat(),
            "result": {"output": "Test result"},
        }
        
        # Sign receipt
        private_key = ed25519.Ed25519PrivateKey.generate()
        receipt_json = json.dumps({k: v for k, v in receipt_data.items() if k != "signature"})
        signature = private_key.sign(receipt_json.encode())
        receipt_data["signature"] = signature.hex()
        
        # Step 3: Submit receipt to coordinator
        response = requests.post(
            f"{coordinator_base_url}/v1/receipts",
            json=receipt_data
        )
        assert response.status_code == 201
        
        # Step 4: Fetch and verify receipt via wallet
        response = requests.get(
            f"{wallet_base_url}/v1/receipts/{receipt_data['id']}"
        )
        assert response.status_code == 200
        
        fetched_receipt = response.json()
        assert fetched_receipt["id"] == receipt_data["id"]
        assert fetched_receipt["job_id"] == job_id
    
    def test_error_handling_flows(self, wallet_base_url):
        """Test error handling in various scenarios"""
        # Test invalid password
        unlock_data = {
            "password": "wrong-password",
            "keystore_path": "/nonexistent/path",
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        assert response.status_code == 400
        assert "error" in response.json()
        
        # Test invalid session token
        headers = {"Authorization": "Bearer invalid-token"}
        
        sign_data = {
            "message": "Test",
            "account_address": "0x123",
        }
        
        response = requests.post(
            f"{wallet_base_url}/v1/sign",
            json=sign_data,
            headers=headers
        )
        assert response.status_code == 401
        
        # Test invalid receipt format
        response = requests.post(
            f"{wallet_base_url}/v1/receipts/verify",
            json={"receipt": {"invalid": "data"}}
        )
        assert response.status_code == 400
    
    def test_concurrent_operations(self, wallet_base_url, test_wallet_data):
        """Test concurrent wallet operations"""
        import threading
        import queue
        
        # Unlock wallet first
        unlock_data = {
            "password": "test-password-123",
            "keystore_path": str(test_wallet_data),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        session_token = response.json()["session_token"]
        headers = {"Authorization": f"Bearer {session_token}"}
        
        # Concurrent signing operations
        results = queue.Queue()
        
        def sign_message(message_id):
            sign_data = {
                "message": f"Test message {message_id}",
                "account_address": "0x1234567890abcdef",
            }
            
            response = requests.post(
                f"{wallet_base_url}/v1/sign",
                json=sign_data,
                headers=headers
            )
            results.put((message_id, response.status_code, response.json()))
        
        # Start 10 concurrent signing operations
        threads = []
        for i in range(10):
            thread = threading.Thread(target=sign_message, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all operations succeeded
        success_count = 0
        while not results.empty():
            msg_id, status, result = results.get()
            assert status == 200, f"Message {msg_id} failed"
            success_count += 1
        
        assert success_count == 10
    
    def test_performance_limits(self, wallet_base_url, test_wallet_data):
        """Test performance limits and rate limiting"""
        # Unlock wallet
        unlock_data = {
            "password": "test-password-123",
            "keystore_path": str(test_wallet_data),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        session_token = response.json()["session_token"]
        headers = {"Authorization": f"Bearer {session_token}"}
        
        # Test rapid signing requests
        start_time = time.time()
        success_count = 0
        
        for i in range(100):
            sign_data = {
                "message": f"Performance test {i}",
                "account_address": "0x1234567890abcdef",
            }
            
            response = requests.post(
                f"{wallet_base_url}/v1/sign",
                json=sign_data,
                headers=headers
            )
            
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                # Rate limited
                break
        
        elapsed_time = time.time() - start_time
        
        # Should handle at least 50 requests per second
        assert success_count > 50
        assert success_count / elapsed_time > 50
    
    def test_wallet_backup_and_restore(self, wallet_base_url, temp_directory):
        """Test wallet backup and restore functionality"""
        # Step 1: Create wallet with multiple accounts
        create_data = {
            "name": "Backup Test Wallet",
            "password": "backup-password-123",
            "keystore_path": str(temp_directory),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets", json=create_data)
        wallet = response.json()
        
        # Add additional account
        unlock_data = {
            "password": "backup-password-123",
            "keystore_path": str(temp_directory),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        session_token = response.json()["session_token"]
        headers = {"Authorization": f"Bearer {session_token}"}
        
        response = requests.post(
            f"{wallet_base_url}/v1/accounts",
            headers=headers
        )
        assert response.status_code == 201
        
        # Step 2: Create backup
        backup_path = Path(temp_directory) / "wallet_backup.json"
        
        response = requests.post(
            f"{wallet_base_url}/v1/wallets/{wallet['id']}/backup",
            json={"backup_path": str(backup_path)},
            headers=headers
        )
        assert response.status_code == 200
        
        # Verify backup exists
        assert backup_path.exists()
        
        # Step 3: Restore wallet to new location
        restore_dir = Path(temp_directory) / "restored"
        restore_dir.mkdir()
        
        response = requests.post(
            f"{wallet_base_url}/v1/wallets/restore",
            json={
                "backup_path": str(backup_path),
                "restore_path": str(restore_dir),
                "new_password": "restored-password-456",
            }
        )
        assert response.status_code == 200
        
        restored_wallet = response.json()
        assert len(restored_wallet["accounts"]) == 2
        
        # Step 4: Verify restored wallet works
        unlock_data = {
            "password": "restored-password-456",
            "keystore_path": str(restore_dir),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        assert response.status_code == 200


@pytest.mark.e2e
class TestWalletSecurityE2E:
    """End-to-end security tests for wallet daemon"""
    
    def test_session_security(self, wallet_base_url, test_wallet_data):
        """Test session token security"""
        # Unlock wallet to get session
        unlock_data = {
            "password": "test-password-123",
            "keystore_path": str(test_wallet_data),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        session_token = response.json()["session_token"]
        
        # Test session expiration
        # In real test, this would wait for actual expiration
        # For now, test invalid token format
        invalid_tokens = [
            "",
            "invalid",
            "Bearer invalid",
            "Bearer ",
            "Bearer " + "A" * 1000,  # Too long
        ]
        
        for token in invalid_tokens:
            headers = {"Authorization": token}
            response = requests.get(f"{wallet_base_url}/v1/wallets", headers=headers)
            assert response.status_code == 401
    
    def test_input_validation(self, wallet_base_url):
        """Test input validation and sanitization"""
        # Test malicious inputs
        malicious_inputs = [
            {"name": "<script>alert('xss')</script>"},
            {"password": "../../etc/passwd"},
            {"keystore_path": "/etc/shadow"},
            {"message": "\x00\x01\x02\x03"},
            {"account_address": "invalid-address"},
        ]
        
        for malicious_input in malicious_inputs:
            response = requests.post(
                f"{wallet_base_url}/v1/wallets",
                json=malicious_input
            )
            # Should either reject or sanitize
            assert response.status_code in [400, 422]
    
    def test_rate_limiting(self, wallet_base_url):
        """Test rate limiting on sensitive operations"""
        # Test unlock rate limiting
        unlock_data = {
            "password": "test",
            "keystore_path": "/nonexistent",
        }
        
        # Send rapid requests
        rate_limited = False
        for i in range(100):
            response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
            if response.status_code == 429:
                rate_limited = True
                break
        
        assert rate_limited, "Rate limiting should be triggered"
    
    def test_encryption_strength(self, wallet_base_url, temp_directory):
        """Test wallet encryption strength"""
        # Create wallet with strong password
        create_data = {
            "name": "Security Test Wallet",
            "password": "VeryStr0ngP@ssw0rd!2024#SpecialChars",
            "keystore_path": str(temp_directory),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets", json=create_data)
        assert response.status_code == 201
        
        # Verify keystore file is encrypted
        keystore_path = Path(temp_directory) / "security-test-wallet.json"
        assert keystore_path.exists()
        
        with open(keystore_path, "r") as f:
            keystore_data = json.load(f)
        
        # Check that private keys are encrypted
        for account in keystore_data.get("accounts", []):
            assert "encrypted_private_key" in account
            encrypted_key = account["encrypted_private_key"]
            # Should not contain plaintext key material
            assert "BEGIN PRIVATE KEY" not in encrypted_key
            assert "-----END" not in encrypted_key


@pytest.mark.e2e
@pytest.mark.slow
class TestWalletPerformanceE2E:
    """Performance tests for wallet daemon"""
    
    def test_large_wallet_performance(self, wallet_base_url, temp_directory):
        """Test performance with large number of accounts"""
        # Create wallet
        create_data = {
            "name": "Large Wallet Test",
            "password": "test-password-123",
            "keystore_path": str(temp_directory),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets", json=create_data)
        wallet = response.json()
        
        # Unlock wallet
        unlock_data = {
            "password": "test-password-123",
            "keystore_path": str(temp_directory),
        }
        
        response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
        session_token = response.json()["session_token"]
        headers = {"Authorization": f"Bearer {session_token}"}
        
        # Create 100 accounts
        start_time = time.time()
        
        for i in range(100):
            response = requests.post(
                f"{wallet_base_url}/v1/accounts",
                headers=headers
            )
            assert response.status_code == 201
        
        creation_time = time.time() - start_time
        
        # Should create accounts quickly
        assert creation_time < 10.0, f"Account creation too slow: {creation_time}s"
        
        # Test listing performance
        start_time = time.time()
        
        response = requests.get(
            f"{wallet_base_url}/v1/wallets/{wallet['id']}",
            headers=headers
        )
        
        listing_time = time.time() - start_time
        assert response.status_code == 200
        
        wallet_data = response.json()
        assert len(wallet_data["accounts"]) == 101
        assert listing_time < 1.0, f"Wallet listing too slow: {listing_time}s"
    
    def test_concurrent_wallet_operations(self, wallet_base_url, temp_directory):
        """Test concurrent operations on multiple wallets"""
        import concurrent.futures
        
        def create_and_use_wallet(wallet_id):
            wallet_dir = Path(temp_directory) / f"wallet_{wallet_id}"
            wallet_dir.mkdir()
            
            # Create wallet
            create_data = {
                "name": f"Concurrent Wallet {wallet_id}",
                "password": f"password-{wallet_id}",
                "keystore_path": str(wallet_dir),
            }
            
            response = requests.post(f"{wallet_base_url}/v1/wallets", json=create_data)
            assert response.status_code == 201
            
            # Unlock and sign
            unlock_data = {
                "password": f"password-{wallet_id}",
                "keystore_path": str(wallet_dir),
            }
            
            response = requests.post(f"{wallet_base_url}/v1/wallets/unlock", json=unlock_data)
            session_token = response.json()["session_token"]
            headers = {"Authorization": f"Bearer {session_token}"}
            
            sign_data = {
                "message": f"Message from wallet {wallet_id}",
                "account_address": "0x1234567890abcdef",
            }
            
            response = requests.post(
                f"{wallet_base_url}/v1/sign",
                json=sign_data,
                headers=headers
            )
            
            return response.status_code == 200
        
        # Run 20 concurrent wallet operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(create_and_use_wallet, i) for i in range(20)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All operations should succeed
        assert all(results), "Some concurrent wallet operations failed"
