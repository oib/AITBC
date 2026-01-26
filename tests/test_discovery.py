"""Test file to verify pytest discovery is working"""

def test_pytest_discovery():
    """Simple test to verify pytest can discover test files"""
    assert True

def test_another_discovery_test():
    """Another test to verify multiple tests are discovered"""
    assert 1 + 1 == 2
