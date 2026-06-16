"""
Tests for AITBC API versioning module (api_versioning.py)
This module has 0% coverage and 55 statements.
"""

from datetime import datetime

import pytest

# Import the module normally
from aitbc import api_versioning

# ============================================================================
# APIVersion Enum Tests
# ============================================================================


class TestAPIVersion:
    """Test APIVersion enum"""

    def test_api_version_values(self):
        assert api_versioning.APIVersion.V1.value == "v1"
        assert api_versioning.APIVersion.V2.value == "v2"
        assert api_versioning.APIVersion.LATEST.value == "latest"


# ============================================================================
# DeprecatedAPIError Tests
# ============================================================================


class TestDeprecatedAPIError:
    """Test DeprecatedAPIError exception"""

    def test_deprecated_api_error(self):
        with pytest.raises(api_versioning.DeprecatedAPIError):
            raise api_versioning.DeprecatedAPIError("API is deprecated")


# ============================================================================
# api_version Decorator Tests
# ============================================================================


class TestApiVersionDecorator:
    """Test api_version decorator"""

    def test_api_version_default(self):
        @api_versioning.api_version()
        def test_func():
            return {"data": "test"}

        result = test_func()
        assert result["_meta"]["api_version"] == "v1"
        assert result["data"] == "test"

    def test_api_version_v2(self):
        @api_versioning.api_version(version=api_versioning.APIVersion.V2)
        def test_func():
            return {"data": "test"}

        result = test_func()
        assert result["_meta"]["api_version"] == "v2"

    def test_api_version_deprecated(self):
        @api_versioning.api_version(deprecated=True)
        def test_func():
            return {"data": "test"}

        result = test_func()
        assert result["_meta"]["api_version"] == "v1"
        assert result["_meta"]["deprecated"] is True

    def test_api_version_deprecated_with_dates(self):
        dep_date = datetime(2024, 1, 1)
        sunset_date = datetime(2024, 12, 31)

        @api_versioning.api_version(deprecated=True, deprecation_date=dep_date, sunset_date=sunset_date)
        def test_func():
            return {"data": "test"}

        result = test_func()
        assert result["_meta"]["deprecated"] is True
        assert result["_meta"]["deprecated_since"] == "2024-01-01T00:00:00"
        assert result["_meta"]["sunset_date"] == "2024-12-31T00:00:00"

    def test_api_version_non_dict_response(self):
        @api_versioning.api_version()
        def test_func():
            return "string result"

        result = test_func()
        assert result == "string result"

    def test_api_version_preserves_existing_meta(self):
        @api_versioning.api_version()
        def test_func():
            return {"data": "test", "_meta": {"existing": "value"}}

        result = test_func()
        assert result["_meta"]["api_version"] == "v1"
        assert result["_meta"]["existing"] == "value"

    def test_api_version_wrapper_attributes(self):
        @api_versioning.api_version(version=api_versioning.APIVersion.V2, deprecated=True)
        def test_func():
            return {}

        assert test_func._api_version == "v2"
        assert test_func._deprecated is True
        assert test_func._deprecation_date is None
        assert test_func._sunset_date is None

    def test_api_version_with_args_kwargs(self):
        @api_versioning.api_version()
        def test_func(x, y):
            return {"sum": x + y}

        result = test_func(1, 2)
        assert result["sum"] == 3
        assert result["_meta"]["api_version"] == "v1"


# ============================================================================
# APIVersionRouter Tests
# ============================================================================


class TestAPIVersionRouter:
    """Test APIVersionRouter class"""

    def test_initialization(self):
        router = api_versioning.APIVersionRouter()
        assert router._version_handlers == {}
        assert router._default_version == "v1"

    def test_register_handler(self):
        router = api_versioning.APIVersionRouter()

        def handler_v1():
            return "v1"

        router.register_handler("v1", handler_v1)
        assert "v1" in router._version_handlers
        assert router._version_handlers["v1"] == handler_v1

    def test_register_multiple_handlers(self):
        router = api_versioning.APIVersionRouter()

        def handler_v1():
            return "v1"

        def handler_v2():
            return "v2"

        router.register_handler("v1", handler_v1)
        router.register_handler("v2", handler_v2)

        assert len(router._version_handlers) == 2

    def test_set_default_version(self):
        router = api_versioning.APIVersionRouter()
        router.set_default_version("v2")
        assert router._default_version == "v2"

    def test_route_with_version(self):
        router = api_versioning.APIVersionRouter()

        def handler_v1():
            return "v1"

        router.register_handler("v1", handler_v1)

        handler = router.route("v1")
        assert handler == handler_v1
        assert handler() == "v1"

    def test_route_without_version_uses_default(self):
        router = api_versioning.APIVersionRouter()

        def handler_v1():
            return "v1"

        router.register_handler("v1", handler_v1)

        handler = router.route()
        assert handler == handler_v1

    def test_route_unsupported_version(self):
        router = api_versioning.APIVersionRouter()

        def handler_v1():
            return "v1"

        router.register_handler("v1", handler_v1)

        with pytest.raises(ValueError, match="Unsupported API version"):
            router.route("v3")

    def test_get_supported_versions(self):
        router = api_versioning.APIVersionRouter()

        def handler_v1():
            return "v1"

        def handler_v2():
            return "v2"

        router.register_handler("v1", handler_v1)
        router.register_handler("v2", handler_v2)

        versions = router.get_supported_versions()
        assert "v1" in versions
        assert "v2" in versions
        assert len(versions) == 2

    def test_get_supported_versions_empty(self):
        router = api_versioning.APIVersionRouter()
        versions = router.get_supported_versions()
        assert versions == []
