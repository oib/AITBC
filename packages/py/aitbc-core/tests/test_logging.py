"""
Tests for aitbc.logging module.
"""
import json
import logging
import sys
from io import StringIO

import pytest

from aitbc.logging import StructuredLogFormatter, setup_logger, get_audit_logger


class TestStructuredLogFormatter:
    """Tests for StructuredLogFormatter."""

    def test_basic_format(self):
        """Test that basic log record is formatted as JSON with required fields."""
        formatter = StructuredLogFormatter(service_name="test-service", env="test")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["service"] == "test-service"
        assert data["env"] == "test"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Hello world"
        assert "timestamp" in data

    def test_extra_fields(self):
        """Test that extra fields on the record are included in output."""
        formatter = StructuredLogFormatter(service_name="svc", env="prod")
        record = logging.LogRecord(
            name="my.logger",
            level=logging.WARNING,
            pathname=__file__,
            lineno=20,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        # Add extra field
        record.request_id = "req-123"
        record.user_id = 42

        output = formatter.format(record)
        data = json.loads(output)

        assert data["request_id"] == "req-123"
        assert data["user_id"] == 42

    def test_exception_info(self):
        """Test that exception information is included when present."""
        formatter = StructuredLogFormatter(service_name="svc", env="dev")
        try:
            1 / 0
        except ZeroDivisionError:
            import sys
            record = logging.LogRecord(
                name="error.logger",
                level=logging.ERROR,
                pathname=__file__,
                lineno=30,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ZeroDivisionError" in data["exception"]

    def test_non_serializable_extra(self):
        """Test that non-serializable extra fields are converted to strings."""
        class CustomObj:
            def __str__(self):
                return "custom_object"

        formatter = StructuredLogFormatter(service_name="svc", env="test")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname=__file__,
            lineno=40,
            msg="test",
            args=(),
            exc_info=None,
        )
        obj = CustomObj()
        record.obj = obj  # not JSON serializable by default

        output = formatter.format(record)
        data = json.loads(output)

        assert data["obj"] == "custom_object"


class TestSetupLogger:
    """Tests for setup_logger."""

    def test_returns_logger_with_correct_name(self):
        """Logger name should match the provided name."""
        logger = setup_logger(name="my.test.logger", service_name="svc")
        assert logger.name == "my.test.logger"

    def test_has_console_handler(self):
        """Logger should have at least one StreamHandler writing to stdout."""
        logger = setup_logger(name="console.test", service_name="svc")
        # Note: we don't set a file handler, so only console
        console_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(console_handlers) >= 1
        # Check it writes to sys.stdout
        assert console_handlers[0].stream == sys.stdout

    def test_formatter_is_structured(self):
        """Logger's handlers should use StructuredLogFormatter."""
        logger = setup_logger(name="fmt.test", service_name="svc", env="staging")
        for handler in logger.handlers:
            assert isinstance(handler.formatter, StructuredLogFormatter)
            assert handler.formatter.service_name == "svc"
            assert handler.formatter.env == "staging"

    def test_idempotent(self):
        """Calling setup_logger multiple times should not add duplicate handlers."""
        logger = setup_logger(name="idempotent.test", service_name="svc")
        initial_handlers = len(logger.handlers)
        # Call again
        logger2 = setup_logger(name="idempotent.test", service_name="svc")
        # The function removes existing handlers before adding, so count should remain the same
        assert len(logger.handlers) == initial_handlers
        assert logger is logger2

    def test_file_handler(self, tmp_path):
        """If log_file is provided, a FileHandler should be added."""
        log_file = tmp_path / "test.log"
        logger = setup_logger(name="file.test", service_name="svc", log_file=str(log_file))
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == str(log_file)


class TestGetAuditLogger:
    """Tests for get_audit_logger."""

    def test_returns_logger_with_suffix(self):
        """Audit logger name should include '.audit' suffix."""
        logger = get_audit_logger(service_name="myservice")
        assert logger.name == "myservice.audit"

    def test_has_handlers_on_first_call(self):
        """First call should set up the audit logger with handlers."""
        # Remove if exists from previous tests
        logger = get_audit_logger(service_name="newaudit")
        # It should have handlers because setup_logger is called internally
        assert len(logger.handlers) >= 1

    def test_caching_consistent(self):
        """Multiple calls should return the same logger instance."""
        logger1 = get_audit_logger(service_name="cached")
        logger2 = get_audit_logger(service_name="cached")
        assert logger1 is logger2
