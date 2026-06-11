"""
API Versioning Tests
Tests for AITBC API versioning utilities
"""

import pytest

from aitbc.api_versioning import APIVersion, DeprecatedAPIError, api_version


class TestAPIVersion:
    """Test APIVersion enum"""

    def test_api_version_v1(self):
        """Test APIVersion V1"""
        assert APIVersion.V1.value == "v1"

    def test_api_version_v2(self):
        """Test APIVersion V2"""
        assert APIVersion.V2.value == "v2"

    def test_api_version_latest(self):
        """Test APIVersion LATEST"""
        assert APIVersion.LATEST.value == "latest"


class TestDeprecatedAPIError:
    """Test DeprecatedAPIError"""

    def test_deprecated_api_error(self):
        """Test DeprecatedAPIError can be raised"""
        with pytest.raises(DeprecatedAPIError):
            raise DeprecatedAPIError("API is deprecated")


class TestApiVersionDecorator:
    """Test api_version decorator"""

    def test_api_version_decorator_basic(self):
        """Test basic api_version decorator"""
        @api_version(version=APIVersion.V1)
        def test_func():
            return "success"
        
        assert test_func() == "success"

    def test_api_version_decorator_deprecated(self):
        """Test api_version decorator with deprecated flag"""
        @api_version(version=APIVersion.V1, deprecated=True)
        def test_func():
            return "success"
        
        assert test_func() == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
