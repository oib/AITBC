"""
Secure Audit Logger Tests
Tests for tamper-evident audit logger
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import tempfile
import json

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestSecureAuditLogger:
    """Test SecureAuditLogger class"""

    def test_init_default_log_dir(self):
        """Test initialization with default log directory"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            assert logger.log_dir == log_dir
            assert logger.log_file == log_dir / "audit_secure.jsonl"
            assert logger.integrity_file == log_dir / "integrity.json"

    def test_init_integrity_file(self):
        """Test integrity file initialization"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            assert logger.integrity_file.exists()
            
            with open(logger.integrity_file) as f:
                data = json.load(f)
            
            assert data["genesis_hash"] is None
            assert data["last_hash"] is None
            assert data["entry_count"] == 0
            assert "created_at" in data
            assert data["version"] == "1.0"

    def test_get_integrity_data(self):
        """Test getting integrity data"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            data = logger._get_integrity_data()
            
            assert "genesis_hash" in data
            assert "last_hash" in data
            assert "entry_count" in data

    def test_update_integrity(self):
        """Test updating integrity data"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            logger._update_integrity("test_hash_123")
            
            data = logger._get_integrity_data()
            
            assert data["genesis_hash"] == "test_hash_123"
            assert data["last_hash"] == "test_hash_123"
            assert data["entry_count"] == 1
            assert "last_updated" in data

    def test_create_entry_hash(self):
        """Test creating entry hash"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            entry = {
                "timestamp": "2024-01-01T00:00:00Z",
                "action": "test_action",
                "user": "test_user",
                "details": {"key": "value"},
                "nonce": "test_nonce"
            }
            
            hash1 = logger._create_entry_hash(entry, previous_hash=None)
            hash2 = logger._create_entry_hash(entry, previous_hash="prev_hash")
            
            assert hash1 is not None
            assert hash2 is not None
            assert hash1 != hash2  # Different previous hash should produce different hash

    def test_log_entry(self):
        """Test logging an audit entry"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            logger.log("test_action", {"key": "value"}, "test_user")
            
            # Check integrity was updated
            data = logger._get_integrity_data()
            assert data["entry_count"] == 1
            assert data["genesis_hash"] is not None
            assert data["last_hash"] is not None

    def test_log_multiple_entries(self):
        """Test logging multiple audit entries"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            logger.log("action1", {"key": "value1"}, "user1")
            logger.log("action2", {"key": "value2"}, "user2")
            logger.log("action3", {"key": "value3"}, "user3")
            
            data = logger._get_integrity_data()
            assert data["entry_count"] == 3

    def test_verify_integrity(self):
        """Test verifying log integrity"""
        from cli.utils.secure_audit import SecureAuditLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = SecureAuditLogger(log_dir=log_dir)
            
            logger.log("test_action", {"key": "value"}, "test_user")
            
            # Verify should pass for untampered log
            result = logger.verify()
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
