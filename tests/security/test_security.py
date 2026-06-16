"""Security tests for AITBC services."""

import pytest

from aitbc.exceptions import ValidationError
from aitbc.utils.validation import (
    validate_address,
    validate_chain_id,
    validate_email,
    validate_hash,
    validate_non_empty,
    validate_port,
    validate_positive_number,
    validate_range,
    validate_url,
    validate_uuid,
)


class TestInputValidation:
    """Test input validation functions."""

    def test_validate_address(self) -> None:
        """Test Ethereum address validation."""
        assert validate_address("ait123abc456") is True
        with pytest.raises(ValidationError):
            validate_address("0x742d35Cc6634C0532925a3b8D4003f2E8")
        with pytest.raises(ValidationError):
            validate_address("not-an-address")
        with pytest.raises(ValidationError):
            validate_address("")

    def test_validate_hash(self) -> None:
        """Test hash validation."""
        assert validate_hash("a" * 64) is True
        with pytest.raises(ValidationError):
            validate_hash("0x123")
        with pytest.raises(ValidationError):
            validate_hash("")

    def test_validate_url(self) -> None:
        """Test URL validation."""
        assert validate_url("http://localhost:8080") is True
        assert validate_url("https://example.com") is True
        with pytest.raises(ValidationError):
            validate_url("not-a-url")
        with pytest.raises(ValidationError):
            validate_url("")

    def test_validate_port(self) -> None:
        """Test port validation."""
        assert validate_port(8080) is True
        with pytest.raises(ValidationError):
            validate_port(0)
        with pytest.raises(ValidationError):
            validate_port(65536)
        with pytest.raises(ValidationError):
            validate_port("not-a-port")

    def test_validate_email(self) -> None:
        """Test email validation."""
        assert validate_email("test@example.com") is True
        with pytest.raises(ValidationError):
            validate_email("invalid-email")
        with pytest.raises(ValidationError):
            validate_email("")

    def test_validate_non_empty(self) -> None:
        """Test non-empty string validation."""
        assert validate_non_empty("test") is True
        assert validate_non_empty(["item"]) is True
        assert validate_non_empty({"key": "value"}) is True
        with pytest.raises(ValidationError):
            validate_non_empty("")
        with pytest.raises(ValidationError):
            validate_non_empty("   ")
        with pytest.raises(ValidationError):
            validate_non_empty(None)

    def test_validate_positive_number(self) -> None:
        """Test positive number validation."""
        assert validate_positive_number(10) is True
        assert validate_positive_number(10.5) is True
        with pytest.raises(ValidationError):
            validate_positive_number(0)
        with pytest.raises(ValidationError):
            validate_positive_number(-5)
        with pytest.raises(ValidationError):
            validate_positive_number("not-a-number")

    def test_validate_range(self) -> None:
        """Test range validation."""
        assert validate_range(5, 0, 10) is True
        with pytest.raises(ValidationError):
            validate_range(-1, 0, 10)
        with pytest.raises(ValidationError):
            validate_range(15, 0, 10)
        with pytest.raises(ValidationError):
            validate_range("not-a-number", 0, 10)

    def test_validate_chain_id(self) -> None:
        """Test chain ID validation."""
        assert validate_chain_id("ait-hub") is True
        assert validate_chain_id("test-chain") is True
        with pytest.raises(ValidationError):
            validate_chain_id("Invalid_Chain")
        with pytest.raises(ValidationError):
            validate_chain_id("")

    def test_validate_uuid(self) -> None:
        """Test UUID validation."""
        assert validate_uuid("123e4567-e89b-12d3-a456-426614174000") is True
        assert validate_uuid("123E4567-E89B-12D3-A456-426614174000") is True
        with pytest.raises(ValidationError):
            validate_uuid("not-a-uuid")
        with pytest.raises(ValidationError):
            validate_uuid("")
