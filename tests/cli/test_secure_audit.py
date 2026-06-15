"""
Secure Audit Tests
Tests for tamper-evident audit logger
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSecureAuditLogger:
    """Test SecureAuditLogger class"""

    def test_init(self):
        """Test SecureAuditLogger initialization"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            assert logger.log_dir == Path(tmpdir)
            assert logger.log_file == Path(tmpdir) / "audit_secure.jsonl"
            assert logger.integrity_file == Path(tmpdir) / "integrity.json"
            assert logger.integrity_file.exists()

    def test_init_integrity(self):
        """Test integrity file initialization"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            integrity_data = logger._get_integrity_data()

            assert integrity_data["genesis_hash"] is None
            assert integrity_data["last_hash"] is None
            assert integrity_data["entry_count"] == 0
            assert "created_at" in integrity_data
            assert integrity_data["version"] == "1.0"

    def test_log(self):
        """Test logging an audit event"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logger.log("test_action", {"key": "value"}, "test_user")

            # Check log file was created
            assert logger.log_file.exists()

            # Check integrity was updated
            integrity_data = logger._get_integrity_data()
            assert integrity_data["entry_count"] == 1
            assert integrity_data["genesis_hash"] is not None
            assert integrity_data["last_hash"] is not None

    def test_verify_integrity_no_log(self):
        """Test integrity verification with no log file"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            is_valid, issues = logger.verify_integrity()

            assert is_valid is True
            assert "No audit log exists" in issues

    def test_get_logs_empty(self):
        """Test getting logs when empty"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logs = logger.get_logs(verify=False)

            assert logs == []

    def test_get_logs_with_entries(self):
        """Test getting logs with entries"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logger.log("action1", {"key": "value1"}, "user1")
            logger.log("action2", {"key": "value2"}, "user2")

            logs = logger.get_logs(limit=10, verify=False)

            assert len(logs) == 2
            assert logs[0]["action"] == "action1"
            assert logs[1]["action"] == "action2"

    def test_get_logs_with_filter(self):
        """Test getting logs with action filter"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logger.log("action1", {"key": "value1"}, "user1")
            logger.log("action2", {"key": "value2"}, "user2")
            logger.log("action1", {"key": "value3"}, "user3")

            logs = logger.get_logs(limit=10, action_filter="action1", verify=False)

            assert len(logs) == 2
            assert all(log["action"] == "action1" for log in logs)

    def test_search_logs(self):
        """Test searching logs"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logger.log("create_wallet", {"address": "0x123"}, "user1")
            logger.log("delete_wallet", {"address": "0x456"}, "user2")
            logger.log("create_wallet", {"address": "0x789"}, "user3")

            results = logger.search_logs("create_wallet", limit=10)

            assert len(results) == 2
            assert all("create_wallet" in str(r) for r in results)

    def test_get_chain_info(self):
        """Test getting chain information"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logger.log("test_action", {}, "test_user")

            chain_info = logger.get_chain_info()

            assert "genesis_hash" in chain_info
            assert "last_hash" in chain_info
            assert "entry_count" in chain_info
            assert chain_info["entry_count"] == 1
            assert "created_at" in chain_info
            assert "version" in chain_info

    def test_export_audit_report(self):
        """Test exporting audit report"""
        try:
            from utils.secure_audit import SecureAuditLogger
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SecureAuditLogger(log_dir=Path(tmpdir))

            logger.log("action1", {"key": "value1"}, "user1")
            logger.log("action2", {"key": "value2"}, "user2")

            report = logger.export_audit_report()

            assert "audit_report" in report
            assert "integrity" in report["audit_report"]
            assert "statistics" in report["audit_report"]
            assert report["audit_report"]["statistics"]["total_entries"] == 2


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_log_action(self):
        """Test log_action convenience function"""
        try:
            from utils.secure_audit import log_action, secure_audit_logger  # noqa: F401
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the global logger's log_dir
            from utils.secure_audit import SecureAuditLogger

            new_logger = SecureAuditLogger(log_dir=Path(tmpdir))

            # Temporarily replace global logger
            with patch("utils.secure_audit.secure_audit_logger", new_logger):
                log_action("test_action", {"key": "value"}, "test_user")

                integrity_data = new_logger._get_integrity_data()
                assert integrity_data["entry_count"] == 1

    def test_verify_audit_integrity(self):
        """Test verify_audit_integrity convenience function"""
        try:
            from utils.secure_audit import (
                secure_audit_logger,  # noqa: F401
                verify_audit_integrity,
            )
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            from utils.secure_audit import SecureAuditLogger

            new_logger = SecureAuditLogger(log_dir=Path(tmpdir))

            with patch("utils.secure_audit.secure_audit_logger", new_logger):
                is_valid, issues = verify_audit_integrity()

                assert is_valid is True

    def test_get_audit_logs(self):
        """Test get_audit_logs convenience function"""
        try:
            from utils.secure_audit import get_audit_logs, secure_audit_logger  # noqa: F401
        except ImportError:
            pytest.skip("eth_utils import failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            from utils.secure_audit import SecureAuditLogger

            new_logger = SecureAuditLogger(log_dir=Path(tmpdir))

            with patch("utils.secure_audit.secure_audit_logger", new_logger):
                logs = get_audit_logs(limit=10)

                assert logs == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
