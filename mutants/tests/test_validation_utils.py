"""Tests for aitbc.utils.validation"""

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


class TestValidateAddress:
    def test_valid_address(self):
        assert validate_address("ait123abc") is True

    def test_empty_address(self):
        with pytest.raises(ValidationError):
            validate_address("")

    def test_invalid_address(self):
        with pytest.raises(ValidationError):
            validate_address("invalid")


class TestValidateHash:
    def test_valid_hash(self):
        assert validate_hash("a" * 64) is True

    def test_empty_hash(self):
        with pytest.raises(ValidationError):
            validate_hash("")

    def test_invalid_hash(self):
        with pytest.raises(ValidationError):
            validate_hash("short")


class TestValidateUrl:
    def test_valid_url(self):
        assert validate_url("https://example.com") is True

    def test_invalid_url(self):
        with pytest.raises(ValidationError):
            validate_url("not-a-url")

    def test_empty_url(self):
        with pytest.raises(ValidationError):
            validate_url("")


class TestValidatePort:
    def test_valid_port(self):
        assert validate_port(8080) is True

    def test_invalid_port_string(self):
        with pytest.raises(ValidationError):
            validate_port("8080")

    def test_port_too_high(self):
        with pytest.raises(ValidationError):
            validate_port(70000)

    def test_port_zero(self):
        with pytest.raises(ValidationError):
            validate_port(0)


class TestValidateEmail:
    def test_valid_email(self):
        assert validate_email("test@example.com") is True

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            validate_email("not-an-email")

    def test_empty_email(self):
        with pytest.raises(ValidationError):
            validate_email("")


class TestValidateNonEmpty:
    def test_valid_string(self):
        assert validate_non_empty("hello") is True

    def test_empty_string(self):
        with pytest.raises(ValidationError):
            validate_non_empty("")

    def test_none(self):
        with pytest.raises(ValidationError):
            validate_non_empty(None)

    def test_empty_list(self):
        with pytest.raises(ValidationError):
            validate_non_empty([])


class TestValidatePositiveNumber:
    def test_positive(self):
        assert validate_positive_number(10) is True

    def test_zero(self):
        with pytest.raises(ValidationError):
            validate_positive_number(0)

    def test_negative(self):
        with pytest.raises(ValidationError):
            validate_positive_number(-5)

    def test_string(self):
        with pytest.raises(ValidationError):
            validate_positive_number("10")


class TestValidateRange:
    def test_in_range(self):
        assert validate_range(50, 0, 100) is True

    def test_out_of_range(self):
        with pytest.raises(ValidationError):
            validate_range(150, 0, 100)

    def test_string_value(self):
        with pytest.raises(ValidationError):
            validate_range("50", 0, 100)


class TestValidateChainId:
    def test_valid_chain_id(self):
        assert validate_chain_id("ait-devnet") is True

    def test_empty_chain_id(self):
        with pytest.raises(ValidationError):
            validate_chain_id("")

    def test_invalid_chain_id(self):
        with pytest.raises(ValidationError):
            validate_chain_id("INVALID_CHAIN")


class TestValidateUuid:
    def test_valid_uuid(self):
        assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_empty_uuid(self):
        with pytest.raises(ValidationError):
            validate_uuid("")

    def test_invalid_uuid(self):
        with pytest.raises(ValidationError):
            validate_uuid("not-a-uuid")
