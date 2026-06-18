"""
Tests for security hardening utilities
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from aitbc.security import SecurityAuditLog, SecurityAuditor, SecurityValidator


class TestSecurityValidator:
    """Tests for SecurityValidator"""

    def test_validate_email_valid(self):
        """Test validate_email with valid email"""
        assert SecurityValidator.validate_email("test@example.com") is True
        assert SecurityValidator.validate_email("user.name+tag@domain.co.uk") is True

    def test_validate_email_invalid(self):
        """Test validate_email with invalid email"""
        assert SecurityValidator.validate_email("invalid") is False
        assert SecurityValidator.validate_email("@example.com") is False
        assert SecurityValidator.validate_email("test@") is False

    def test_validate_url_valid(self):
        """Test validate_url with valid URL"""
        assert SecurityValidator.validate_url("https://example.com") is True
        assert SecurityValidator.validate_url("http://localhost:8000") is True
        assert SecurityValidator.validate_url("https://192.168.1.1:8080/path") is True

    def test_validate_url_invalid(self):
        """Test validate_url with invalid URL"""
        assert SecurityValidator.validate_url("not-a-url") is False
        assert SecurityValidator.validate_url("ftp://example.com") is False
        assert SecurityValidator.validate_url("") is False

    def test_validate_ethereum_address_valid(self):
        """Test validate_ethereum_address with valid address"""
        assert SecurityValidator.validate_ethereum_address("0x1234567890abcdef1234567890abcdef12345678") is True
        assert SecurityValidator.validate_ethereum_address("0xABCDEF1234567890ABCDEF1234567890ABCDEF12") is True

    def test_validate_ethereum_address_invalid(self):
        """Test validate_ethereum_address with invalid address"""
        assert SecurityValidator.validate_ethereum_address("0x123") is False
        assert SecurityValidator.validate_ethereum_address("1234567890abcdef1234567890abcdef12345678") is False
        assert SecurityValidator.validate_ethereum_address("0x1234567890abcdef1234567890abcdef123456789") is False

    def test_validate_tx_hash_valid(self):
        """Test validate_tx_hash with valid hash"""
        valid_hash = "0x" + "12" * 32  # 64 hex chars total (32 * 2)
        assert SecurityValidator.validate_tx_hash(valid_hash) is True

    def test_validate_tx_hash_invalid(self):
        """Test validate_tx_hash with invalid hash"""
        assert SecurityValidator.validate_tx_hash("0x123") is False
        assert (
            SecurityValidator.validate_tx_hash("1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234") is False
        )

    def test_sanitize_html(self):
        """Test sanitize_html"""
        html = "<script>alert('xss')</script>"
        sanitized = SecurityValidator.sanitize_html(html)

        assert "&lt;script&gt;" in sanitized
        assert "<script>" not in sanitized

    def test_sanitize_json_string(self):
        """Test sanitize_json_string"""
        json_str = '{"key": "value\x00with\x1fcontrol"}'
        sanitized = SecurityValidator.sanitize_json_string(json_str)

        assert "\x00" not in sanitized
        assert "\x1f" not in sanitized

    def test_validate_json_structure_valid(self):
        """Test validate_json_structure with valid structure"""
        data = {"field1": "value1", "field2": "value2"}
        required_fields = ["field1", "field2"]

        assert SecurityValidator.validate_json_structure(data, required_fields) is True

    def test_validate_json_structure_missing_field(self):
        """Test validate_json_structure with missing field"""
        data = {"field1": "value1"}
        required_fields = ["field1", "field2"]

        assert SecurityValidator.validate_json_structure(data, required_fields) is False

    def test_validate_json_structure_not_dict(self):
        """Test validate_json_structure with non-dict"""
        data = ["not", "a", "dict"]
        required_fields = ["field1"]

        assert SecurityValidator.validate_json_structure(data, required_fields) is False

    def test_sanitize_filename(self):
        """Test sanitize_filename"""
        filename = "../../../etc/passwd"
        sanitized = SecurityValidator.sanitize_filename(filename)

        assert "/" not in sanitized
        assert "\\" not in sanitized

    def test_sanitize_filename_control_chars(self):
        """Test sanitize_filename removes control characters"""
        filename = "file\x00name\x1ftest"
        sanitized = SecurityValidator.sanitize_filename(filename)

        assert "\x00" not in sanitized
        assert "\x1f" not in sanitized


class TestSecurityAuditLog:
    """Tests for SecurityAuditLog dataclass"""

    def test_creation(self):
        """Test SecurityAuditLog creation"""
        log = SecurityAuditLog(
            timestamp=datetime.now(),
            action="test_action",
            user="test_user",
            ip_address="127.0.0.1",
            details={"key": "value"},
            severity="INFO",
        )

        assert log.action == "test_action"
        assert log.user == "test_user"

    def test_defaults(self):
        """Test SecurityAuditLog with defaults"""
        log = SecurityAuditLog(timestamp=datetime.now(), action="test_action", user=None, ip_address=None, details={})

        assert log.severity == "INFO"


class TestSecurityAuditor:
    """Tests for SecurityAuditor"""

    def test_initialization(self):
        """Test SecurityAuditor initialization"""
        auditor = SecurityAuditor()

        assert auditor.log_file is None
        assert auditor.audit_logs == []

    def test_initialization_with_file(self):
        """Test SecurityAuditor with log file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"
            auditor = SecurityAuditor(log_file)

            assert auditor.log_file == log_file

    @patch("aitbc.security.audit.logger")
    def test_log_event(self, mock_logger):
        """Test log_event"""
        auditor = SecurityAuditor()

        auditor.log_event(action="test_action", user="test_user", ip_address="127.0.0.1", details={"key": "value"})

        assert len(auditor.audit_logs) == 1
        assert auditor.audit_logs[0].action == "test_action"
        mock_logger.info.assert_called_once()

    def test_log_event_with_file(self):
        """Test log_event writes to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"
            auditor = SecurityAuditor(log_file)

            auditor.log_event(action="test_action")

            assert log_file.exists()
            with open(log_file) as f:
                content = f.read()
                assert "test_action" in content

    def test_get_recent_logs(self):
        """Test get_recent_logs"""
        auditor = SecurityAuditor()
        auditor.log_event(action="action1")
        auditor.log_event(action="action2")

        logs = auditor.get_recent_logs(hours=24)

        assert len(logs) == 2

    def test_get_logs_by_user(self):
        """Test get_logs_by_user"""
        auditor = SecurityAuditor()
        auditor.log_event(action="test", user="user1")
        auditor.log_event(action="test", user="user2")

        logs = auditor.get_logs_by_user("user1")

        assert len(logs) == 1
        assert logs[0].user == "user1"

    def test_get_logs_by_action(self):
        """Test get_logs_by_action"""
        auditor = SecurityAuditor()
        auditor.log_event(action="action1")
        auditor.log_event(action="action2")

        logs = auditor.get_logs_by_action("action1")

        assert len(logs) == 1
        assert logs[0].action == "action1"

    def test_get_logs_by_severity(self):
        """Test get_logs_by_severity"""
        auditor = SecurityAuditor()
        auditor.log_event(action="test", severity="INFO")
        auditor.log_event(action="test", severity="WARNING")

        logs = auditor.get_logs_by_severity("INFO")

        assert len(logs) == 1
        assert logs[0].severity == "INFO"

    def test_clear_old_logs(self):
        """Test clear_old_logs"""
        auditor = SecurityAuditor()
        auditor.log_event(action="test")

        cleared = auditor.clear_old_logs(days=30)

        assert cleared == 0  # Logs are recent

    def test_get_statistics(self):
        """Test get_statistics"""
        auditor = SecurityAuditor()
        auditor.log_event(action="test", user="user1", severity="INFO")
        auditor.log_event(action="test", user="user2", severity="WARNING")

        stats = auditor.get_statistics()

        assert stats["total_logs"] == 2
        assert stats["unique_users"] == 2
        assert stats["unique_actions"] == 1
        assert stats["severity_breakdown"]["INFO"] == 1
        assert stats["severity_breakdown"]["WARNING"] == 1

    def test_get_statistics_empty(self):
        """Test get_statistics with no logs"""
        auditor = SecurityAuditor()

        stats = auditor.get_statistics()

        assert stats["total_logs"] == 0
        assert stats["unique_users"] == 0
        assert stats["unique_actions"] == 0
