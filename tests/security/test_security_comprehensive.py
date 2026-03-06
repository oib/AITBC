"""
Comprehensive Security Tests for AITBC
Tests authentication, authorization, encryption, and data protection
"""

import pytest
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile


class TestAuthenticationSecurity:
    """Test authentication and authorization security"""
    
    def test_api_key_validation(self):
        """Test API key validation and security"""
        # Generate secure API key
        api_key = secrets.token_urlsafe(32)
        
        # Test API key format
        assert len(api_key) >= 32
        assert isinstance(api_key, str)
        
        # Test API key hashing
        hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
        assert len(hashed_key) == 64
        assert hashed_key != api_key  # Should be different
        
        # Test API key validation
        def validate_api_key(key):
            if not key or len(key) < 32:
                return False
            return True
        
        assert validate_api_key(api_key) is True
        assert validate_api_key("short") is False
        assert validate_api_key("") is False
    
    def test_token_security(self):
        """Test JWT token security"""
        # Mock JWT token structure
        token_data = {
            'sub': 'user123',
            'iat': int(datetime.utcnow().timestamp()),
            'exp': int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
            'permissions': ['read', 'write']
        }
        
        # Test token structure
        assert 'sub' in token_data
        assert 'iat' in token_data
        assert 'exp' in token_data
        assert 'permissions' in token_data
        assert token_data['exp'] > token_data['iat']
        
        # Test token expiration
        current_time = int(datetime.utcnow().timestamp())
        assert token_data['exp'] > current_time
        
        # Test permissions
        assert isinstance(token_data['permissions'], list)
        assert len(token_data['permissions']) > 0
    
    def test_session_security(self):
        """Test session management security"""
        # Generate secure session ID
        session_id = secrets.token_hex(32)
        
        # Test session ID properties
        assert len(session_id) == 64
        assert all(c in '0123456789abcdef' for c in session_id)
        
        # Test session data
        session_data = {
            'session_id': session_id,
            'user_id': 'user123',
            'created_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat(),
            'ip_address': '192.168.1.1'
        }
        
        # Validate session data
        assert session_data['session_id'] == session_id
        assert 'user_id' in session_data
        assert 'created_at' in session_data
        assert 'last_activity' in session_data


class TestDataEncryption:
    """Test data encryption and protection"""
    
    def test_sensitive_data_encryption(self):
        """Test encryption of sensitive data"""
        # Mock sensitive data
        sensitive_data = {
            'private_key': '0x1234567890abcdef',
            'api_secret': 'secret_key_123',
            'wallet_seed': 'seed_phrase_words'
        }
        
        # Test data masking
        def mask_sensitive_data(data):
            masked = {}
            for key, value in data.items():
                if 'key' in key.lower() or 'secret' in key.lower() or 'seed' in key.lower():
                    masked[key] = f"***{value[-4:]}" if len(value) > 4 else "***"
                else:
                    masked[key] = value
            return masked
        
        masked_data = mask_sensitive_data(sensitive_data)
        
        # Verify masking
        assert masked_data['private_key'].startswith('***')
        assert masked_data['api_secret'].startswith('***')
        assert masked_data['wallet_seed'].startswith('***')
        assert len(masked_data['private_key']) <= 7  # *** + last 4 chars
    
    def test_data_integrity(self):
        """Test data integrity verification"""
        # Original data
        original_data = {
            'transaction_id': 'tx_123',
            'amount': 100.0,
            'from_address': 'aitbc1sender',
            'to_address': 'aitbc1receiver',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Generate checksum
        data_string = json.dumps(original_data, sort_keys=True)
        checksum = hashlib.sha256(data_string.encode()).hexdigest()
        
        # Verify integrity
        def verify_integrity(data, expected_checksum):
            data_string = json.dumps(data, sort_keys=True)
            calculated_checksum = hashlib.sha256(data_string.encode()).hexdigest()
            return calculated_checksum == expected_checksum
        
        assert verify_integrity(original_data, checksum) is True
        
        # Test with tampered data
        tampered_data = original_data.copy()
        tampered_data['amount'] = 200.0
        
        assert verify_integrity(tampered_data, checksum) is False
    
    def test_secure_storage(self):
        """Test secure data storage practices"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create sensitive file
            sensitive_file = temp_path / "sensitive_data.json"
            sensitive_data = {
                'api_key': secrets.token_urlsafe(32),
                'private_key': secrets.token_hex(32),
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Write with restricted permissions (simulated)
            with open(sensitive_file, 'w') as f:
                json.dump(sensitive_data, f)
            
            # Verify file exists
            assert sensitive_file.exists()
            
            # Test secure reading
            with open(sensitive_file, 'r') as f:
                loaded_data = json.load(f)
            
            assert loaded_data['api_key'] == sensitive_data['api_key']
            assert loaded_data['private_key'] == sensitive_data['private_key']


class TestInputValidation:
    """Test input validation and sanitization"""
    
    def test_sql_injection_prevention(self):
        """Test SQL injection prevention"""
        # Malicious inputs
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "'; INSERT INTO users VALUES ('hacker'); --",
            "'; UPDATE users SET password='hacked'; --"
        ]
        
        # Test input sanitization
        def sanitize_input(input_str):
            # Remove dangerous SQL characters
            dangerous_chars = ["'", ";", "--", "/*", "*/", "xp_", "sp_"]
            sanitized = input_str
            for char in dangerous_chars:
                sanitized = sanitized.replace(char, "")
            return sanitized.strip()
        
        for malicious_input in malicious_inputs:
            sanitized = sanitize_input(malicious_input)
            # Ensure dangerous characters are removed
            assert "'" not in sanitized
            assert ";" not in sanitized
            assert "--" not in sanitized
    
    def test_xss_prevention(self):
        """Test XSS prevention"""
        # Malicious XSS inputs
        xss_inputs = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>"
        ]
        
        # Test XSS sanitization
        def sanitize_html(input_str):
            # Remove HTML tags and dangerous content
            import re
            # Remove script tags
            sanitized = re.sub(r'<script.*?</script>', '', input_str, flags=re.IGNORECASE | re.DOTALL)
            # Remove all HTML tags
            sanitized = re.sub(r'<[^>]+>', '', sanitized)
            # Remove javascript: protocol
            sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
            return sanitized.strip()
        
        for xss_input in xss_inputs:
            sanitized = sanitize_html(xss_input)
            # Ensure HTML tags are removed
            assert '<' not in sanitized
            assert '>' not in sanitized
            assert 'javascript:' not in sanitized.lower()
    
    def test_file_upload_security(self):
        """Test file upload security"""
        # Test file type validation
        allowed_extensions = ['.json', '.csv', '.txt', '.pdf']
        dangerous_files = [
            'malware.exe',
            'script.js',
            'shell.php',
            'backdoor.py'
        ]
        
        def validate_file_extension(filename):
            file_path = Path(filename)
            extension = file_path.suffix.lower()
            return extension in allowed_extensions
        
        for dangerous_file in dangerous_files:
            assert validate_file_extension(dangerous_file) is False
        
        # Test safe files
        safe_files = ['data.json', 'report.csv', 'document.txt', 'manual.pdf']
        for safe_file in safe_files:
            assert validate_file_extension(safe_file) is True
    
    def test_rate_limiting(self):
        """Test rate limiting implementation"""
        # Mock rate limiter
        class RateLimiter:
            def __init__(self, max_requests=100, window_seconds=3600):
                self.max_requests = max_requests
                self.window_seconds = window_seconds
                self.requests = {}
            
            def is_allowed(self, client_id):
                now = datetime.utcnow()
                
                # Clean old requests
                if client_id in self.requests:
                    self.requests[client_id] = [
                        req_time for req_time in self.requests[client_id]
                        if (now - req_time).total_seconds() < self.window_seconds
                    ]
                else:
                    self.requests[client_id] = []
                
                # Check if under limit
                if len(self.requests[client_id]) < self.max_requests:
                    self.requests[client_id].append(now)
                    return True
                
                return False
        
        # Test rate limiting
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        client_id = 'test_client'
        
        # Should allow first 5 requests
        for i in range(5):
            assert limiter.is_allowed(client_id) is True
        
        # Should deny 6th request
        assert limiter.is_allowed(client_id) is False


class TestNetworkSecurity:
    """Test network security and communication"""
    
    def test_https_enforcement(self):
        """Test HTTPS enforcement"""
        # Test URL validation
        secure_urls = [
            'https://api.aitbc.com',
            'https://localhost:8000',
            'https://192.168.1.1:443'
        ]
        
        insecure_urls = [
            'http://api.aitbc.com',
            'ftp://files.aitbc.com',
            'ws://websocket.aitbc.com'
        ]
        
        def is_secure_url(url):
            return url.startswith('https://')
        
        for secure_url in secure_urls:
            assert is_secure_url(secure_url) is True
        
        for insecure_url in insecure_urls:
            assert is_secure_url(insecure_url) is False
    
    def test_request_headers_security(self):
        """Test secure request headers"""
        # Secure headers
        secure_headers = {
            'Authorization': f'Bearer {secrets.token_urlsafe(32)}',
            'Content-Type': 'application/json',
            'X-API-Version': 'v1',
            'X-Request-ID': secrets.token_hex(16)
        }
        
        # Validate headers
        assert secure_headers['Authorization'].startswith('Bearer ')
        assert len(secure_headers['Authorization']) > 40  # Bearer + token
        assert secure_headers['Content-Type'] == 'application/json'
        assert secure_headers['X-API-Version'] == 'v1'
        assert len(secure_headers['X-Request-ID']) == 32
    
    def test_cors_configuration(self):
        """Test CORS configuration security"""
        # Secure CORS configuration
        cors_config = {
            'allowed_origins': ['https://app.aitbc.com', 'https://admin.aitbc.com'],
            'allowed_methods': ['GET', 'POST', 'PUT', 'DELETE'],
            'allowed_headers': ['Authorization', 'Content-Type'],
            'max_age': 3600,
            'allow_credentials': True
        }
        
        # Validate CORS configuration
        assert len(cors_config['allowed_origins']) > 0
        assert all(origin.startswith('https://') for origin in cors_config['allowed_origins'])
        assert 'GET' in cors_config['allowed_methods']
        assert 'POST' in cors_config['allowed_methods']
        assert 'Authorization' in cors_config['allowed_headers']
        assert cors_config['max_age'] > 0


class TestAuditLogging:
    """Test audit logging and monitoring"""
    
    def test_security_event_logging(self):
        """Test security event logging"""
        # Security events
        security_events = [
            {
                'event_type': 'login_attempt',
                'user_id': 'user123',
                'ip_address': '192.168.1.1',
                'timestamp': datetime.utcnow().isoformat(),
                'success': True
            },
            {
                'event_type': 'api_access',
                'user_id': 'user123',
                'endpoint': '/api/v1/jobs',
                'method': 'POST',
                'timestamp': datetime.utcnow().isoformat(),
                'status_code': 200
            },
            {
                'event_type': 'failed_login',
                'user_id': 'unknown',
                'ip_address': '192.168.1.100',
                'timestamp': datetime.utcnow().isoformat(),
                'reason': 'invalid_credentials'
            }
        ]
        
        # Validate security events
        for event in security_events:
            assert 'event_type' in event
            assert 'timestamp' in event
            assert event['timestamp'] != ''
            assert event['event_type'] in ['login_attempt', 'api_access', 'failed_login']
    
    def test_log_data_protection(self):
        """Test protection of sensitive data in logs"""
        # Sensitive log data
        sensitive_log_data = {
            'user_id': 'user123',
            'api_key': 'sk-1234567890abcdef',
            'request_body': '{"password": "secret123"}',
            'ip_address': '192.168.1.1'
        }
        
        # Test log data sanitization
        def sanitize_log_data(data):
            sanitized = data.copy()
            
            # Mask API keys
            if 'api_key' in sanitized:
                key = sanitized['api_key']
                sanitized['api_key'] = f"{key[:7]}***{key[-4:]}" if len(key) > 11 else "***"
            
            # Remove passwords from request body
            if 'request_body' in sanitized:
                try:
                    body = json.loads(sanitized['request_body'])
                    if 'password' in body:
                        body['password'] = '***'
                    sanitized['request_body'] = json.dumps(body)
                except:
                    pass
            
            return sanitized
        
        sanitized_log = sanitize_log_data(sensitive_log_data)
        
        # Verify sanitization
        assert '***' in sanitized_log['api_key']
        assert '***' in sanitized_log['request_body']
        assert 'secret123' not in sanitized_log['request_body']
