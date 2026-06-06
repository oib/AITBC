"""
Tests for security hardening utilities
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from aitbc.security_hardening import (
    RateLimiter,
    SecurityAuditLog,
    SecurityAuditor,
    SecurityValidator,
    get_security_auditor,
    log_security_event,
)


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
        assert SecurityValidator.validate_tx_hash("1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234") is False

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
            severity="INFO"
        )

        assert log.action == "test_action"
        assert log.user == "test_user"

    def test_defaults(self):
        """Test SecurityAuditLog with defaults"""
        log = SecurityAuditLog(
            timestamp=datetime.now(),
            action="test_action",
            user=None,
            ip_address=None,
            details={}
        )

        assert log.severity == "INFO"


class TestSecurityAuditor:
    """Tests for SecurityAuditor"""

    def test_initialization(self):
        """Test SecurityAuditor initialization"""
        auditor = SecurityAuditor()

        assert auditor.log_file is None
        assert auditor._logs == []

    def test_initialization_with_file(self):
        """Test SecurityAuditor with log file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"
            auditor = SecurityAuditor(log_file)

            assert auditor.log_file == log_file

    @patch('aitbc.security_hardening.logger')
    def test_log_security_event(self, mock_logger):
        """Test log_security_event"""
        auditor = SecurityAuditor()

        auditor.log_security_event(
            action="test_action",
            user="test_user",
            ip_address="127.0.0.1",
            details={"key": "value"}
        )

        assert len(auditor._logs) == 1
        assert auditor._logs[0].action == "test_action"
        mock_logger.info.assert_called_once()

    def test_log_security_event_with_file(self):
        """Test log_security_event writes to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"
            auditor = SecurityAuditor(log_file)

            auditor.log_security_event(action="test_action")

            assert log_file.exists()
            with open(log_file) as f:
                content = f.read()
                assert "test_action" in content

    def test_get_logs_no_filter(self):
        """Test get_logs without filters"""
        auditor = SecurityAuditor()
        auditor.log_security_event(action="action1")
        auditor.log_security_event(action="action2")

        logs = auditor.get_logs()

        assert len(logs) == 2

    def test_get_logs_with_action_filter(self):
        """Test get_logs with action filter"""
        auditor = SecurityAuditor()
        auditor.log_security_event(action="action1")
        auditor.log_security_event(action="action2")

        logs = auditor.get_logs(action="action1")

        assert len(logs) == 1
        assert logs[0].action == "action1"

    def test_get_logs_with_user_filter(self):
        """Test get_logs with user filter"""
        auditor = SecurityAuditor()
        auditor.log_security_event(action="test", user="user1")
        auditor.log_security_event(action="test", user="user2")

        logs = auditor.get_logs(user="user1")

        assert len(logs) == 1
        assert logs[0].user == "user1"

    def test_get_logs_with_severity_filter(self):
        """Test get_logs with severity filter"""
        auditor = SecurityAuditor()
        auditor.log_security_event(action="test", severity="INFO")
        auditor.log_security_event(action="test", severity="CRITICAL")

        logs = auditor.get_logs(severity="CRITICAL")

        assert len(logs) == 1
        assert logs[0].severity == "CRITICAL"

    def test_get_logs_with_limit(self):
        """Test get_logs with limit"""
        auditor = SecurityAuditor()
        for i in range(10):
            auditor.log_security_event(action=f"action{i}")

        logs = auditor.get_logs(limit=5)

        assert len(logs) == 5

    def test_get_critical_logs(self):
        """Test get_critical_logs"""
        auditor = SecurityAuditor()
        auditor.log_security_event(action="test", severity="INFO")
        auditor.log_security_event(action="test", severity="CRITICAL")
        auditor.log_security_event(action="test", severity="CRITICAL")

        logs = auditor.get_critical_logs()

        assert len(logs) == 2
        assert all(log.severity == "CRITICAL" for log in logs)


class TestRateLimiter:
    """Tests for RateLimiter"""

    def test_initialization(self):
        """Test RateLimiter initialization"""
        limiter = RateLimiter(rate=10, per=60)

        assert limiter.rate == 10
        assert limiter.per == 60
        assert limiter._requests == {}

    def test_is_allowed_first_request(self):
        """Test is_allowed for first request"""
        limiter = RateLimiter(rate=10, per=60)

        assert limiter.is_allowed("user1") is True

    def test_is_allowed_within_limit(self):
        """Test is_allowed within rate limit"""
        limiter = RateLimiter(rate=10, per=60)

        for _ in range(5):
            assert limiter.is_allowed("user1") is True

    def test_is_allowed_exceeded(self):
        """Test is_allowed when rate exceeded"""
        limiter = RateLimiter(rate=5, per=60)

        # Make 5 requests
        for _ in range(5):
            limiter.is_allowed("user1")

        # 6th request should be denied
        assert limiter.is_allowed("user1") is False

    @patch('aitbc.security_hardening.logger')
    def test_is_allowed_logs_warning(self, mock_logger):
        """Test is_allowed logs warning when exceeded"""
        limiter = RateLimiter(rate=2, per=60)

        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")  # Should trigger warning

        mock_logger.warning.assert_called_once()

    def test_is_allowed_old_requests_expire(self):
        """Test old requests expire after time window"""
        limiter = RateLimiter(rate=2, per=1)

        limiter.is_allowed("user1")
        limiter.is_allowed("user1")

        # Wait for expiration
        import time
        time.sleep(1.1)

        # Should be allowed again
        assert limiter.is_allowed("user1") is True

    def test_reset(self):
        """Test reset rate limit"""
        limiter = RateLimiter(rate=5, per=60)

        limiter.is_allowed("user1")
        limiter.reset("user1")

        # Should be allowed again after reset
        assert limiter.is_allowed("user1") is True

    @patch('aitbc.security_hardening.logger')
    def test_reset_logs_info(self, mock_logger):
        """Test reset logs info message"""
        limiter = RateLimiter(rate=5, per=60)

        limiter.is_allowed("user1")
        limiter.reset("user1")

        mock_logger.info.assert_called_once()

    def test_get_remaining_requests(self):
        """Test get_remaining_requests"""
        limiter = RateLimiter(rate=10, per=60)

        remaining = limiter.get_remaining_requests("user1")
        assert remaining == 10

        limiter.is_allowed("user1")
        remaining = limiter.get_remaining_requests("user1")
        assert remaining == 9

    def test_get_remaining_requests_no_requests(self):
        """Test get_remaining_requests for new identifier"""
        limiter = RateLimiter(rate=10, per=60)

        remaining = limiter.get_remaining_requests("new_user")
        assert remaining == 10


class TestGlobalSecurityAuditor:
    """Tests for global security auditor functions"""

    @patch('aitbc.security_hardening.logger')
    def test_log_security_event_global(self, mock_logger):
        """Test log_security_event using global auditor"""
        log_security_event(action="test_action")

        auditor = get_security_auditor()
        assert len(auditor._logs) == 1

    def test_get_security_auditor_singleton(self):
        """Test get_security_auditor returns singleton"""
        auditor1 = get_security_auditor()
        auditor2 = get_security_auditor()

        assert auditor1 is auditor2
