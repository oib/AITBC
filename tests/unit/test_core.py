"""Unit tests for aitbc.core modules."""

import pytest

from aitbc.aitbc_logging import BlockchainTextFormatter, StructuredFormatter, configure_logging, get_logger, setup_logger


class TestLogging:
    """Test aitbc logging utilities."""

    def test_configure_logging(self) -> None:
        """Test configure_logging function."""
        configure_logging(level="DEBUG")
        logger = get_logger(__name__)
        assert logger is not None
        assert logger.level <= 10  # DEBUG level

    def test_get_logger(self) -> None:
        """Test get_logger function."""
        logger = get_logger("test.logger")
        assert logger is not None
        assert logger.name == "test.logger"

    def test_setup_logger(self) -> None:
        """Test setup_logger function."""
        logger = setup_logger("test.setup", level="INFO")
        assert logger is not None
        assert logger.level <= 20  # INFO level

    def test_structured_formatter(self) -> None:
        """Test StructuredFormatter."""
        formatter = StructuredFormatter()
        import logging

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        assert '"level": "INFO"' in formatted
        assert '"message": "Test message"' in formatted

    def test_blockchain_text_formatter(self) -> None:
        """Test BlockchainTextFormatter (alias for JournalFormatter)."""
        formatter = BlockchainTextFormatter()
        import logging

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        # JournalFormatter format: [LEVEL] [logger_name] message
        assert "[INFO]" in formatted
        assert "[test]" in formatted
        assert "Test message" in formatted


class TestMiddleware:
    """Test middleware components."""

    def test_request_id_middleware_import(self) -> None:
        """Test RequestIDMiddleware can be imported."""
        from aitbc.middleware import RequestIDMiddleware

        assert RequestIDMiddleware is not None

    def test_correlation_id_middleware_import(self) -> None:
        """Test CorrelationIDMiddleware can be imported."""
        from aitbc.middleware import CorrelationIDMiddleware

        assert CorrelationIDMiddleware is not None


class TestConfiguration:
    """Test configuration utilities."""

    def test_hierarchical_config_import(self) -> None:
        """Test HierarchicalConfig can be imported."""
        from aitbc.config import HierarchicalConfig

        assert HierarchicalConfig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
