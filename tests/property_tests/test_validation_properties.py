"""
Property-based tests for AITBC validation functions using hypothesis.
Tests ensure that validation functions maintain expected properties across random inputs.
"""

import re

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st


from aitbc.exceptions import ValidationError
from aitbc.utils.validation import (
    validate_address,
    validate_address_strict,
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


class TestValidationProperties:
    """Property-based tests for validation functions"""

    @given(st.text(min_size=1, max_size=100).filter(lambda x: x and x.strip()))
    @settings(max_examples=50)
    def test_validate_non_empty_strings(self, text):
        """Test that non-empty strings pass validation"""
        assert validate_non_empty(text)

    @given(st.just(""))
    @settings(max_examples=10)
    def test_validate_empty_strings(self, empty_string):
        """Test that empty strings fail validation"""
        with pytest.raises(ValidationError):
            validate_non_empty(empty_string)

    @given(st.integers(min_value=1, max_value=1000000))
    @settings(max_examples=50)
    def test_validate_positive_numbers(self, number):
        """Test that positive numbers pass validation"""
        assert validate_positive_number(number)

    @given(st.integers(max_value=0))
    @settings(max_examples=50)
    def test_validate_non_positive_numbers(self, number):
        """Test that non-positive numbers fail validation"""
        with pytest.raises(ValidationError):
            validate_positive_number(number)

    @given(st.integers(min_value=0, max_value=100), st.integers(min_value=101, max_value=200))
    @settings(max_examples=50)
    def test_validate_range_in_bounds(self, value, max_val):
        """Test that values in range pass validation"""
        assert validate_range(value, 0, max_val)

    @given(st.integers(min_value=-100, max_value=-1))
    @settings(max_examples=50)
    def test_validate_range_out_of_bounds(self, value):
        """Test that values out of range fail validation"""
        with pytest.raises(ValidationError):
            validate_range(value, 0, 100)

    @given(st.integers(min_value=1, max_value=65535))
    @settings(max_examples=50)
    def test_validate_valid_ports(self, port):
        """Test that valid ports pass validation"""
        assert validate_port(port)

    @given(st.integers(min_value=65536, max_value=100000))
    @settings(max_examples=50)
    def test_validate_invalid_ports(self, port):
        """Test that invalid ports fail validation"""
        with pytest.raises(ValidationError):
            validate_port(port)

    @given(st.just("test@example.com"))
    @settings(max_examples=10)
    def test_validate_valid_emails(self, email_addr):
        """Test that valid email addresses pass validation"""
        assert validate_email(email_addr)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: "@" not in x))
    @settings(max_examples=50)
    def test_validate_invalid_emails(self, text):
        """Test that invalid email addresses fail validation"""
        with pytest.raises(ValidationError):
            validate_email(text)

    # These two encoded an API that no longer exists, which is most of why the file was
    # skipped. validate_address is non-raising now (validate_address_strict raises), and
    # addresses moved to Ethereum-style 0x with legacy ait1/aitbc1 kept for back-compat --
    # a bare "ait"-prefixed string is no longer valid.

    @given(st.text(alphabet="0123456789abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=30))
    @settings(max_examples=50)
    def test_validate_legacy_address_accepted(self, suffix):
        """Legacy ait1/aitbc1 addresses stay valid while migration is outstanding."""
        assert validate_address(f"ait1{suffix}")
        assert validate_address(f"aitbc1{suffix}")

    @given(st.text(min_size=1, max_size=50).filter(lambda x: not re.match(r"^ait(bc)?1[a-z0-9]+$", x)))
    @settings(max_examples=50)
    def test_validate_rejects_non_addresses(self, text):
        """Anything that is neither a 0x address nor a legacy one is rejected.

        Non-raising: it returns False. The strict variant is what raises.
        """
        assume(not (text.startswith("0x") and len(text) == 42))
        assert validate_address(text) is False

    @given(st.text(min_size=1, max_size=50).filter(lambda x: not re.match(r"^ait(bc)?1[a-z0-9]+$", x)))
    @settings(max_examples=50)
    def test_validate_address_strict_raises_on_the_same_input(self, text):
        """The strict variant must agree with the non-raising one, but by raising."""
        assume(not (text.startswith("0x") and len(text) == 42))
        with pytest.raises(ValidationError):
            validate_address_strict(text)

    @given(st.just("a" * 64))
    @settings(max_examples=10)
    def test_validate_valid_hash(self, hash_str):
        """Test that valid hashes pass validation"""
        assert validate_hash(hash_str)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: not x.isalnum() or len(x) != 64))
    @settings(max_examples=50)
    def test_validate_invalid_hash_format(self, text):
        """Test that invalid hash formats fail validation"""
        with pytest.raises(ValidationError):
            validate_hash(text)

    @given(st.just("ait-mainnet"))
    @settings(max_examples=10)
    def test_validate_valid_chain_id(self, chain_id):
        """Test that valid chain IDs pass validation"""
        assert validate_chain_id(chain_id)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: not x.replace("-", "").isalnum() and x.replace("-", "") != ""))
    @settings(max_examples=50)
    def test_validate_invalid_chain_id(self, text):
        """Test that invalid chain IDs fail validation"""
        with pytest.raises(ValidationError):
            validate_chain_id(text)

    @given(st.uuids())
    @settings(max_examples=50)
    def test_validate_valid_uuid(self, uuid_obj):
        """Test that valid UUIDs pass validation"""
        assert validate_uuid(str(uuid_obj))

    @given(st.text(min_size=1, max_size=50).filter(lambda x: "-" not in x))
    @settings(max_examples=50)
    def test_validate_invalid_uuid(self, text):
        """Test that invalid UUIDs fail validation"""
        with pytest.raises(ValidationError):
            validate_uuid(text)

    @given(st.just("http://localhost:8000"))
    @settings(max_examples=10)
    def test_validate_valid_url(self, url):
        """Test that valid URLs pass validation"""
        assert validate_url(url)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: "http" not in x and "https" not in x))
    @settings(max_examples=50)
    def test_validate_invalid_url(self, text):
        """Test that invalid URLs fail validation"""
        with pytest.raises(ValidationError):
            validate_url(text)
