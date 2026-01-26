"""
Comprehensive security tests for AITBC
"""

import pytest
import json
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from web3 import Web3


@pytest.mark.security
class TestAuthenticationSecurity:
    """Test authentication security measures"""
    
    def test_password_strength_validation(self, coordinator_client):
        """Test password strength requirements"""
        weak_passwords = [
            "123456",
            "password",
            "qwerty",
            "abc123",
            "password123",
            "Aa1!"  # Too short
        ]
        
        for password in weak_passwords:
            response = coordinator_client.post(
                "/v1/auth/register",
                json={
                    "email": "test@example.com",
                    "password": password,
                    "organization": "Test Org"
                }
            )
            assert response.status_code == 400
            assert "password too weak" in response.json()["detail"].lower()
    
    def test_account_lockout_after_failed_attempts(self, coordinator_client):
        """Test account lockout after multiple failed attempts"""
        email = "lockout@test.com"
        
        # Attempt 5 failed logins
        for i in range(5):
            response = coordinator_client.post(
                "/v1/auth/login",
                json={
                    "email": email,
                    "password": f"wrong_password_{i}"
                }
            )
            assert response.status_code == 401
        
        # 6th attempt should lock account
        response = coordinator_client.post(
            "/v1/auth/login",
            json={
                "email": email,
                "password": "correct_password"
            }
        )
        assert response.status_code == 423
        assert "account locked" in response.json()["detail"].lower()
    
    def test_session_timeout(self, coordinator_client):
        """Test session timeout functionality"""
        # Login
        response = coordinator_client.post(
            "/v1/auth/login",
            json={
                "email": "session@test.com",
                "password": "SecurePass123!"
            }
        )
        token = response.json()["access_token"]
        
        # Use expired session
        with patch('time.time') as mock_time:
            mock_time.return_value = time.time() + 3600 * 25  # 25 hours later
            
            response = coordinator_client.get(
                "/v1/jobs",
                headers={"Authorization": f"Bearer {token}"}
            )
        
        assert response.status_code == 401
        assert "session expired" in response.json()["detail"].lower()
    
    def test_jwt_token_validation(self, coordinator_client):
        """Test JWT token validation"""
        # Test malformed token
        response = coordinator_client.get(
            "/v1/jobs",
            headers={"Authorization": "Bearer invalid.jwt.token"}
        )
        assert response.status_code == 401
        
        # Test token with invalid signature
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": "user123", "exp": time.time() + 3600}
        
        # Create token with wrong secret
        token_parts = [
            json.dumps(header).encode(),
            json.dumps(payload).encode()
        ]
        
        encoded = [base64.urlsafe_b64encode(part).rstrip(b'=') for part in token_parts]
        signature = hmac.digest(b"wrong_secret", b".".join(encoded), hashlib.sha256)
        encoded.append(base64.urlsafe_b64encode(signature).rstrip(b'='))
        
        invalid_token = b".".join(encoded).decode()
        
        response = coordinator_client.get(
            "/v1/jobs",
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        assert response.status_code == 401


@pytest.mark.security
class TestAuthorizationSecurity:
    """Test authorization and access control"""
    
    def test_tenant_data_isolation(self, coordinator_client):
        """Test strict tenant data isolation"""
        # Create job for tenant A
        response = coordinator_client.post(
            "/v1/jobs",
            json={"job_type": "test", "parameters": {}},
            headers={"X-Tenant-ID": "tenant-a"}
        )
        job_id = response.json()["id"]
        
        # Try to access with tenant B's context
        response = coordinator_client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-Tenant-ID": "tenant-b"}
        )
        assert response.status_code == 404
        
        # Try to access with no tenant
        response = coordinator_client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 401
        
        # Try to modify with wrong tenant
        response = coordinator_client.patch(
            f"/v1/jobs/{job_id}",
            json={"status": "completed"},
            headers={"X-Tenant-ID": "tenant-b"}
        )
        assert response.status_code == 404
    
    def test_role_based_access_control(self, coordinator_client):
        """Test RBAC permissions"""
        # Test with viewer role (read-only)
        viewer_token = "viewer_jwt_token"
        response = coordinator_client.get(
            "/v1/jobs",
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 200
        
        # Viewer cannot create jobs
        response = coordinator_client.post(
            "/v1/jobs",
            json={"job_type": "test"},
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403
        assert "insufficient permissions" in response.json()["detail"].lower()
        
        # Test with admin role
        admin_token = "admin_jwt_token"
        response = coordinator_client.post(
            "/v1/jobs",
            json={"job_type": "test"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201
    
    def test_api_key_security(self, coordinator_client):
        """Test API key authentication"""
        # Test without API key
        response = coordinator_client.get("/v1/api-keys")
        assert response.status_code == 401
        
        # Test with invalid API key
        response = coordinator_client.get(
            "/v1/api-keys",
            headers={"X-API-Key": "invalid_key_123"}
        )
        assert response.status_code == 401
        
        # Test with valid API key
        response = coordinator_client.get(
            "/v1/api-keys",
            headers={"X-API-Key": "valid_key_456"}
        )
        assert response.status_code == 200


@pytest.mark.security
class TestInputValidationSecurity:
    """Test input validation and sanitization"""
    
    def test_sql_injection_prevention(self, coordinator_client):
        """Test SQL injection protection"""
        malicious_inputs = [
            "'; DROP TABLE jobs; --",
            "' OR '1'='1",
            "1; DELETE FROM users WHERE '1'='1",
            "'; INSERT INTO jobs VALUES ('hack'); --",
            "' UNION SELECT * FROM users --"
        ]
        
        for payload in malicious_inputs:
            # Test in job ID parameter
            response = coordinator_client.get(f"/v1/jobs/{payload}")
            assert response.status_code == 404
            assert response.status_code != 500
            
            # Test in query parameters
            response = coordinator_client.get(
                f"/v1/jobs?search={payload}"
            )
            assert response.status_code != 500
            
            # Test in JSON body
            response = coordinator_client.post(
                "/v1/jobs",
                json={"job_type": payload, "parameters": {}}
            )
            assert response.status_code == 422
    
    def test_xss_prevention(self, coordinator_client):
        """Test XSS protection"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//",
            "<svg onload=alert('xss')>"
        ]
        
        for payload in xss_payloads:
            # Test in job name
            response = coordinator_client.post(
                "/v1/jobs",
                json={
                    "job_type": "test",
                    "parameters": {},
                    "name": payload
                }
            )
            
            if response.status_code == 201:
                # Verify XSS is sanitized in response
                assert "<script>" not in response.text
                assert "javascript:" not in response.text.lower()
    
    def test_command_injection_prevention(self, coordinator_client):
        """Test command injection protection"""
        malicious_commands = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "`whoami`",
            "$(id)",
            "&& ls -la"
        ]
        
        for cmd in malicious_commands:
            response = coordinator_client.post(
                "/v1/jobs",
                json={
                    "job_type": "test",
                    "parameters": {"command": cmd}
                }
            )
            # Should be rejected or sanitized
            assert response.status_code in [400, 422, 500]
    
    def test_file_upload_security(self, coordinator_client):
        """Test file upload security"""
        malicious_files = [
            ("malicious.php", "<?php system($_GET['cmd']); ?>"),
            ("script.js", "<script>alert('xss')</script>"),
            ("../../etc/passwd", "root:x:0:0:root:/root:/bin/bash"),
            ("huge_file.txt", "x" * 100_000_000)  # 100MB
        ]
        
        for filename, content in malicious_files:
            response = coordinator_client.post(
                "/v1/upload",
                files={"file": (filename, content)}
            )
            # Should reject dangerous files
            assert response.status_code in [400, 413, 422]


@pytest.mark.security
class TestCryptographicSecurity:
    """Test cryptographic implementations"""
    
    def test_https_enforcement(self, coordinator_client):
        """Test HTTPS is enforced"""
        # Test HTTP request should be redirected to HTTPS
        response = coordinator_client.get(
            "/v1/jobs",
            headers={"X-Forwarded-Proto": "http"}
        )
        assert response.status_code == 301
        assert "https" in response.headers.get("location", "")
    
    def test_sensitive_data_encryption(self, coordinator_client):
        """Test sensitive data is encrypted at rest"""
        # Create job with sensitive data
        sensitive_data = {
            "job_type": "confidential",
            "parameters": {
                "api_key": "secret_key_123",
                "password": "super_secret",
                "private_data": "confidential_info"
            }
        }
        
        response = coordinator_client.post(
            "/v1/jobs",
            json=sensitive_data,
            headers={"X-Tenant-ID": "test-tenant"}
        )
        assert response.status_code == 201
        
        # Verify data is encrypted in database
        job_id = response.json()["id"]
        with patch('apps.coordinator_api.src.app.services.encryption_service.decrypt') as mock_decrypt:
            mock_decrypt.return_value = sensitive_data["parameters"]
            
            response = coordinator_client.get(
                f"/v1/jobs/{job_id}",
                headers={"X-Tenant-ID": "test-tenant"}
            )
        
        # Should call decrypt function
        mock_decrypt.assert_called_once()
    
    def test_signature_verification(self, coordinator_client):
        """Test request signature verification"""
        # Test without signature
        response = coordinator_client.post(
            "/v1/webhooks/job-update",
            json={"job_id": "123", "status": "completed"}
        )
        assert response.status_code == 401
        
        # Test with invalid signature
        response = coordinator_client.post(
            "/v1/webhooks/job-update",
            json={"job_id": "123", "status": "completed"},
            headers={"X-Signature": "invalid_signature"}
        )
        assert response.status_code == 401
        
        # Test with valid signature
        payload = json.dumps({"job_id": "123", "status": "completed"})
        signature = hmac.new(
            b"webhook_secret",
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        with patch('apps.coordinator_api.src.app.webhooks.verify_signature') as mock_verify:
            mock_verify.return_value = True
            
            response = coordinator_client.post(
                "/v1/webhooks/job-update",
                json={"job_id": "123", "status": "completed"},
                headers={"X-Signature": signature}
            )
        
        assert response.status_code == 200


@pytest.mark.security
class TestRateLimitingSecurity:
    """Test rate limiting and DoS protection"""
    
    def test_api_rate_limiting(self, coordinator_client):
        """Test API rate limiting"""
        # Make rapid requests
        responses = []
        for i in range(100):
            response = coordinator_client.get("/v1/jobs")
            responses.append(response)
            if response.status_code == 429:
                break
        
        # Should hit rate limit
        assert any(r.status_code == 429 for r in responses)
        
        # Check rate limit headers
        rate_limited = next(r for r in responses if r.status_code == 429)
        assert "X-RateLimit-Limit" in rate_limited.headers
        assert "X-RateLimit-Remaining" in rate_limited.headers
        assert "X-RateLimit-Reset" in rate_limited.headers
    
    def test_burst_protection(self, coordinator_client):
        """Test burst request protection"""
        # Send burst of requests
        start_time = time.time()
        responses = []
        
        for i in range(50):
            response = coordinator_client.post(
                "/v1/jobs",
                json={"job_type": "test"}
            )
            responses.append(response)
        
        end_time = time.time()
        
        # Should be throttled
        assert end_time - start_time > 1.0  # Should take at least 1 second
        assert any(r.status_code == 429 for r in responses)
    
    def test_ip_based_blocking(self, coordinator_client):
        """Test IP-based blocking for abuse"""
        malicious_ip = "192.168.1.100"
        
        # Simulate abuse from IP
        with patch('apps.coordinator_api.src.app.services.security_service.SecurityService.check_ip_reputation') as mock_check:
            mock_check.return_value = {"blocked": True, "reason": "malicious_activity"}
            
            response = coordinator_client.get(
                "/v1/jobs",
                headers={"X-Real-IP": malicious_ip}
            )
        
        assert response.status_code == 403
        assert "blocked" in response.json()["detail"].lower()


@pytest.mark.security
class TestAuditLoggingSecurity:
    """Test audit logging and monitoring"""
    
    def test_security_event_logging(self, coordinator_client):
        """Test security events are logged"""
        # Failed login
        coordinator_client.post(
            "/v1/auth/login",
            json={"email": "test@example.com", "password": "wrong"}
        )
        
        # Privilege escalation attempt
        coordinator_client.get(
            "/v1/admin/users",
            headers={"Authorization": "Bearer user_token"}
        )
        
        # Verify events were logged
        with patch('apps.coordinator_api.src.app.services.audit_service.AuditService.get_events') as mock_events:
            mock_events.return_value = [
                {
                    "event": "login_failed",
                    "ip": "127.0.0.1",
                    "timestamp": datetime.utcnow().isoformat()
                },
                {
                    "event": "privilege_escalation_attempt",
                    "user": "user123",
                    "timestamp": datetime.utcnow().isoformat()
                }
            ]
            
            response = coordinator_client.get(
                "/v1/audit/security-events",
                headers={"Authorization": "Bearer admin_token"}
            )
        
        assert response.status_code == 200
        events = response.json()
        assert len(events) >= 2
    
    def test_data_access_logging(self, coordinator_client):
        """Test data access is logged"""
        # Access sensitive data
        response = coordinator_client.get(
            "/v1/jobs/sensitive-job-123",
            headers={"X-Tenant-ID": "tenant-a"}
        )
        
        # Verify access logged
        with patch('apps.coordinator_api.src.app.services.audit_service.AuditService.check_access_log') as mock_check:
            mock_check.return_value = {
                "accessed": True,
                "timestamp": datetime.utcnow().isoformat(),
                "user": "user123",
                "resource": "job:sensitive-job-123"
            }
            
            response = coordinator_client.get(
                "/v1/audit/data-access/sensitive-job-123",
                headers={"Authorization": "Bearer admin_token"}
            )
        
        assert response.status_code == 200
        assert response.json()["accessed"] is True


@pytest.mark.security
class TestBlockchainSecurity:
    """Test blockchain-specific security"""
    
    def test_transaction_signature_validation(self, blockchain_client):
        """Test transaction signature validation"""
        unsigned_tx = {
            "from": "0x1234567890abcdef",
            "to": "0xfedcba0987654321",
            "value": "1000",
            "nonce": 1
        }
        
        # Test without signature
        response = blockchain_client.post(
            "/v1/transactions",
            json=unsigned_tx
        )
        assert response.status_code == 400
        assert "signature required" in response.json()["detail"].lower()
        
        # Test with invalid signature
        response = blockchain_client.post(
            "/v1/transactions",
            json={**unsigned_tx, "signature": "0xinvalid"}
        )
        assert response.status_code == 400
        assert "invalid signature" in response.json()["detail"].lower()
    
    def test_replay_attack_prevention(self, blockchain_client):
        """Test replay attack prevention"""
        valid_tx = {
            "from": "0x1234567890abcdef",
            "to": "0xfedcba0987654321",
            "value": "1000",
            "nonce": 1,
            "signature": "0xvalid_signature"
        }
        
        # First transaction succeeds
        response = blockchain_client.post(
            "/v1/transactions",
            json=valid_tx
        )
        assert response.status_code == 201
        
        # Replay same transaction fails
        response = blockchain_client.post(
            "/v1/transactions",
            json=valid_tx
        )
        assert response.status_code == 400
        assert "nonce already used" in response.json()["detail"].lower()
    
    def test_smart_contract_security(self, blockchain_client):
        """Test smart contract security checks"""
        malicious_contract = {
            "bytecode": "0x6001600255",  # Self-destruct pattern
            "abi": []
        }
        
        response = blockchain_client.post(
            "/v1/contracts/deploy",
            json=malicious_contract
        )
        assert response.status_code == 400
        assert "dangerous opcode" in response.json()["detail"].lower()


@pytest.mark.security
class TestZeroKnowledgeProofSecurity:
    """Test zero-knowledge proof security"""
    
    def test_zk_proof_validation(self, coordinator_client):
        """Test ZK proof validation"""
        # Test without proof
        response = coordinator_client.post(
            "/v1/confidential/verify",
            json={
                "statement": "x > 18",
                "witness": {"x": 21}
            }
        )
        assert response.status_code == 400
        assert "proof required" in response.json()["detail"].lower()
        
        # Test with invalid proof
        response = coordinator_client.post(
            "/v1/confidential/verify",
            json={
                "statement": "x > 18",
                "witness": {"x": 21},
                "proof": "invalid_proof"
            }
        )
        assert response.status_code == 400
        assert "invalid proof" in response.json()["detail"].lower()
    
    def test_confidential_data_protection(self, coordinator_client):
        """Test confidential data remains protected"""
        confidential_job = {
            "job_type": "confidential_inference",
            "encrypted_data": "encrypted_payload",
            "commitment": "data_commitment_hash"
        }
        
        response = coordinator_client.post(
            "/v1/jobs",
            json=confidential_job,
            headers={"X-Tenant-ID": "secure-tenant"}
        )
        assert response.status_code == 201
        
        # Verify raw data is not exposed
        job = response.json()
        assert "encrypted_data" not in job
        assert "commitment" in job
        assert job["confidential"] is True
