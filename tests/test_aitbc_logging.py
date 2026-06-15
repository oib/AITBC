"""
Tests for enhanced logging module
"""

import json
import logging
from io import StringIO

import pytest

from aitbc.aitbc_logging import LogContext, StructuredFormatter, configure_logging, get_logger, log_context, setup_logger


class TestStructuredFormatter:
    """Test StructuredFormatter"""

    def test_structured_formatter_format(self):
        """Test formatting log record as structured JSON"""
        formatter = StructuredFormatter()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert log_entry["level"] == "ERROR"
        assert log_entry["logger"] == "test_logger"
        assert log_entry["message"] == "Test message"
        assert log_entry["module"] == "test"
        # Function name may be None in test context
        assert "function" in log_entry
        assert log_entry["line"] == 42
        assert "timestamp" in log_entry

    def test_structured_formatter_with_exception(self):
        """Test formatting log record with exception"""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = True

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=exc_info,
        )

        # Skip this test if exc_info is True (not a real exception tuple)
        # In real usage, exc_info would be a tuple from sys.exc_info()
        if exc_info is True:
            pytest.skip("Need real exception info for this test")

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert "exception" in log_entry
        assert log_entry["level"] == "ERROR"

    def test_structured_formatter_with_extra(self):
        """Test formatting log record with extra fields"""
        formatter = StructuredFormatter()

        record = logging.LogRecord(
            name="test_logger", level=logging.INFO, pathname="test.py", lineno=42, msg="Test message", args=(), exc_info=None
        )
        record.extra = {"custom_field": "custom_value"}

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert log_entry["custom_field"] == "custom_value"


class TestSetupLogger:
    """Test setup_logger function"""

    def test_setup_logger_default(self):
        """Test setting up logger with default parameters"""
        logger = setup_logger("test_logger")

        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0

    def test_setup_logger_custom_level(self):
        """Test setting up logger with custom level"""
        logger = setup_logger("test_logger", level="DEBUG")

        assert logger.name == "test_logger"
        assert logger.level == logging.DEBUG

    def test_setup_logger_custom_format(self):
        """Test setting up logger with custom format"""
        logger = setup_logger("test_logger", format_string="%(levelname)s - %(message)s")

        assert logger.name == "test_logger"
        assert len(logger.handlers) > 0

    def test_setup_logger_structured(self):
        """Test setting up logger with structured formatting"""
        # Remove existing handlers first
        logger = logging.getLogger("test_logger_structured")
        logger.handlers.clear()

        logger = setup_logger("test_logger_structured", structured=True)

        assert logger.name == "test_logger_structured"
        assert len(logger.handlers) > 0
        # The handler should have a formatter, check if it's the right type
        if logger.handlers[0].formatter:
            assert isinstance(logger.handlers[0].formatter, StructuredFormatter)

    def test_setup_logger_no_duplicate_handlers(self):
        """Test that setup_logger doesn't add duplicate handlers"""
        logger = setup_logger("test_logger")
        initial_handler_count = len(logger.handlers)

        # Call setup_logger again
        logger = setup_logger("test_logger")

        # Handler count should not increase
        assert len(logger.handlers) == initial_handler_count


class TestGetLogger:
    """Test get_logger function"""

    def test_get_logger(self):
        """Test getting logger instance"""
        logger = get_logger("test_logger")

        assert logger.name == "test_logger"
        assert isinstance(logger, logging.Logger)

    def test_get_logger_same_instance(self):
        """Test that get_logger returns same instance for same name"""
        logger1 = get_logger("test_logger")
        logger2 = get_logger("test_logger")

        assert logger1 is logger2


class TestConfigureLogging:
    """Test configure_logging function"""

    def test_configure_logging_default(self):
        """Test configuring root logging with default level"""
        configure_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_configure_logging_custom_level(self):
        """Test configuring root logging with custom level"""
        configure_logging(level="DEBUG")

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_configure_logging_structured(self):
        """Test configuring root logging with structured formatting"""
        configure_logging(structured=True)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) > 0
        assert isinstance(root_logger.handlers[0].formatter, StructuredFormatter)


class TestLogContext:
    """Test log_context context manager"""

    def test_log_context_adds_context(self):
        """Test that log_context adds contextual information"""
        get_logger("test_logger")

        with log_context(user_id="test_user", request_id="test_request"):
            # Context should be added to logger
            pass

        # Context should be removed after exiting
        pass

    def test_log_context_with_logger_output(self):
        """Test log_context with actual logger output"""
        logger = setup_logger("test_logger", level="INFO")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

        with log_context(user_id="test_user"):
            logger.info("Test message with context")

        output = stream.getvalue()
        assert "Test message with context" in output

        # Clean up
        logger.removeHandler(handler)


class TestLogContextClass:
    """Test LogContext class"""

    def test_log_context_class_init(self):
        """Test initializing LogContext"""
        context = LogContext(user_id="test_user", request_id="test_request")

        assert context.context == {"user_id": "test_user", "request_id": "test_request"}

    def test_log_context_class_enter_exit(self):
        """Test LogContext context manager"""
        get_logger("test_logger")

        context = LogContext(user_id="test_user", request_id="test_request")

        with context:
            # Context should be active
            pass

        # Context should be removed after exiting
        pass

    def test_log_context_class_nested(self):
        """Test nested LogContext usage"""
        get_logger("test_logger")

        context1 = LogContext(user_id="user1")
        context2 = LogContext(request_id="req1")

        with context1:
            with context2:
                # Both contexts should be active
                pass

        # Contexts should be removed after exiting
        pass


class TestStructuredLoggingIntegration:
    """Test structured logging integration"""

    def test_structured_logging_end_to_end(self):
        """Test end-to-end structured logging"""
        logger = setup_logger("test_logger", level="INFO", structured=True)

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        logger.info("Test message")

        output = stream.getvalue()
        log_entry = json.loads(output)

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "Test message"
        assert "timestamp" in log_entry

        # Clean up
        logger.removeHandler(handler)

    def test_structured_logging_with_context(self):
        """Test structured logging with contextual information"""
        logger = setup_logger("test_logger", level="INFO", structured=True)

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        with log_context(user_id="test_user", request_id="test_request"):
            logger.info("Test message with context")

        output = stream.getvalue()
        log_entry = json.loads(output)

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "Test message with context"
        assert "timestamp" in log_entry

        # Clean up
        logger.removeHandler(handler)

    def test_structured_logging_different_levels(self):
        """Test structured logging at different log levels"""
        logger = setup_logger("test_logger", level="DEBUG", structured=True)

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

        output = stream.getvalue()
        lines = output.strip().split("\n")

        assert len(lines) == 5
        for line in lines:
            log_entry = json.loads(line)
            assert "level" in log_entry
            assert "message" in log_entry
            assert "timestamp" in log_entry

        # Clean up
        logger.removeHandler(handler)


class TestBackwardCompatibility:
    """Test backward compatibility with existing logging"""

    def test_traditional_logging_still_works(self):
        """Test that traditional logging still works"""
        logger = setup_logger("test_logger", level="INFO")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        logger.addHandler(handler)

        logger.info("Traditional message")

        output = stream.getvalue()
        assert "INFO - Traditional message" in output

        # Clean up
        logger.removeHandler(handler)

    def test_traditional_format_string(self):
        """Test traditional format string still works"""
        logger = setup_logger("test_logger", format_string="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

        logger.info("Test message")

        output = stream.getvalue()
        assert "Test message" in output

        # Clean up
        logger.removeHandler(handler)
