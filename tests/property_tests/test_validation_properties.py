"""
Property-based tests for AITBC validation functions using hypothesis.
Tests ensure that validation functions maintain expected properties across random inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import text, integers, email, uuid, ip_addresses

from aitbc.validation import (
    validate_address,
    validate_hash,
    validate_url,
    validate_port,
    validate_email,
    validate_non_empty,
    validate_positive_number,
    validate_range,
    validate_chain_id,
    validate_uuid
)


class TestValidationProperties:
    """Property-based tests for validation functions"""

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_validate_non_empty_strings(self, text):
        """Test that non-empty strings pass validation"""
        assert validate_non_empty(text)

    @given(st.just(""))
    @settings(max_examples=10)
    def test_validate_empty_strings(self, empty_string):
        """Test that empty strings fail validation"""
        assert not validate_non_empty(empty_string)

    @given(st.integers(min_value=1, max_value=1000000))
    @settings(max_examples=50)
    def test_validate_positive_numbers(self, number):
        """Test that positive numbers pass validation"""
        assert validate_positive_number(number)

    @given(st.integers(max_value=0))
    @settings(max_examples=50)
    def test_validate_non_positive_numbers(self, number):
        """Test that non-positive numbers fail validation"""
        assert not validate_positive_number(number)

    @given(st.integers(min_value=0, max_value=100), st.integers(min_value=101, max_value=200))
    @settings(max_examples=50)
    def test_validate_range_in_bounds(self, value, max_val):
        """Test that values in range pass validation"""
        assert validate_range(value, 0, max_val)

    @given(st.integers(min_value=-100, max_value=-1))
    @settings(max_examples=50)
    def test_validate_range_out_of_bounds(self, value):
        """Test that values out of range fail validation"""
        assert not validate_range(value, 0, 100)

    @given(st.integers(min_value=1, max_value=65535))
    @settings(max_examples=50)
    def test_validate_valid_ports(self, port):
        """Test that valid ports pass validation"""
        assert validate_port(port)

    @given(st.integers(min_value=65536, max_value=100000))
    @settings(max_examples=50)
    def test_validate_invalid_ports(self, port):
        """Test that invalid ports fail validation"""
        assert not validate_port(port)

    @given(st.emails())
    @settings(max_examples=50)
    def test_validate_valid_emails(self, email_addr):
        """Test that valid email addresses pass validation"""
        assert validate_email(email_addr)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: '@' not in x))
    @settings(max_examples=50)
    def test_validate_invalid_emails(self, text):
        """Test that invalid email addresses fail validation"""
        assert not validate_email(text)

    @given(st.just("0x" + "a" * 40))
    @settings(max_examples=10)
    def test_validate_valid_address(self, address):
        """Test that valid Ethereum addresses pass validation"""
        assert validate_address(address)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: not x.startswith('0x')))
    @settings(max_examples=50)
    def test_validate_invalid_address_format(self, text):
        """Test that invalid address formats fail validation"""
        assert not validate_address(text)

    @given(st.just("0x" + "a" * 64))
    @settings(max_examples=10)
    def test_validate_valid_hash(self, hash_str):
        """Test that valid hashes pass validation"""
        assert validate_hash(hash_str)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: not x.startswith('0x')))
    @settings(max_examples=50)
    def test_validate_invalid_hash_format(self, text):
        """Test that invalid hash formats fail validation"""
        assert not validate_hash(text)

    @given(st.just("ait-mainnet"))
    @settings(max_examples=10)
    def test_validate_valid_chain_id(self, chain_id):
        """Test that valid chain IDs pass validation"""
        assert validate_chain_id(chain_id)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: 'ait-' not in x))
    @settings(max_examples=50)
    def test_validate_invalid_chain_id(self, text):
        """Test that invalid chain IDs fail validation"""
        assert not validate_chain_id(text)

    @given(st.uuids())
    @settings(max_examples=50)
    def test_validate_valid_uuid(self, uuid_obj):
        """Test that valid UUIDs pass validation"""
        assert validate_uuid(str(uuid_obj))

    @given(st.text(min_size=1, max_size=50).filter(lambda x: '-' not in x))
    @settings(max_examples=50)
    def test_validate_invalid_uuid(self, text):
        """Test that invalid UUIDs fail validation"""
        assert not validate_uuid(text)

    @given(st.just("http://localhost:8000"))
    @settings(max_examples=10)
    def test_validate_valid_url(self, url):
        """Test that valid URLs pass validation"""
        assert validate_url(url)

    @given(st.text(min_size=1, max_size=50).filter(lambda x: 'http' not in x and 'https' not in x))
    @settings(max_examples=50)
    def test_validate_invalid_url(self, text):
        """Test that invalid URLs fail validation"""
        assert not validate_url(text)
