"""
Test file to verify Windsorf test integration is working
"""

import pytest


def test_pytest_discovery():
    """Simple test to verify pytest can discover this file"""
    assert True


def test_windsurf_integration():
    """Test that Windsurf test runner is working"""
    assert "windsurf" in "windsurf test integration"
    

@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_multiplication(input, expected):
    """Parameterized test example"""
    result = input * 2
    assert result == expected
