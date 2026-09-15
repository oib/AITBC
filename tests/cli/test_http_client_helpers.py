"""Unit tests for the shared coordinator URL/auth helpers (GAP-22).

Every coordinator consumer funnels through these so a configured
``coordinator_api_url`` works identically whether it holds a service root
(``http://host``), a versioned base (``http://host/v1``), or the public nginx
mount (``https://<hub>/c/v1``).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from aitbc_cli.utils.http_client import (
    auth_client_kwargs,
    auth_headers,
    looks_like_jwt,
    normalize_base_url,
    origin_base_url,
    service_root_url,
)


class TestServiceRootUrl:
    """service_root_url strips one trailing /v1 for absolute-path callers."""

    def test_plain_root_unchanged(self):
        assert service_root_url("http://localhost:8203") == "http://localhost:8203"

    def test_trailing_slash_removed(self):
        assert service_root_url("http://localhost:8203/") == "http://localhost:8203"

    def test_trailing_v1_stripped(self):
        assert service_root_url("http://localhost:8203/v1") == "http://localhost:8203"

    def test_public_mount_prefix_kept(self):
        assert service_root_url("https://hub.example.net/c/v1") == "https://hub.example.net/c"

    def test_agent_mount_prefix_kept(self):
        assert service_root_url("https://hub.example.net/agent/v1") == "https://hub.example.net/agent"

    def test_default_used_for_empty(self):
        assert service_root_url("", "http://localhost:8203") == "http://localhost:8203"
        assert service_root_url(None, "http://localhost:8203/v1") == "http://localhost:8203"


class TestNormalizeBaseUrl:
    """normalize_base_url always yields a base ending in /v1."""

    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("http://localhost:8203", "http://localhost:8203/v1"),
            ("http://localhost:8203/", "http://localhost:8203/v1"),
            ("http://localhost:8203/v1", "http://localhost:8203/v1"),
            ("http://localhost:8203/v1/", "http://localhost:8203/v1"),
            ("https://hub.example.net/c", "https://hub.example.net/c/v1"),
            ("https://hub.example.net/c/v1", "https://hub.example.net/c/v1"),
        ],
    )
    def test_normalize(self, given, expected):
        assert normalize_base_url(given) == expected

    def test_default_used_for_empty(self):
        assert normalize_base_url(None, "http://localhost:8203") == "http://localhost:8203/v1"


class TestOriginBaseUrl:
    """origin_base_url reduces to scheme://host for mounted-prefix configs."""

    def test_drops_api_mount(self):
        assert origin_base_url("https://hub.example.net/api/v1/agent") == "https://hub.example.net"

    def test_keeps_port(self):
        assert origin_base_url("http://localhost:8107/api/v1/agent") == "http://localhost:8107"

    def test_default_used_for_empty(self):
        assert origin_base_url("", "https://hub.example.net") == "https://hub.example.net"

    def test_bare_value_returned_when_unparseable(self):
        assert origin_base_url("not-a-url") == "not-a-url"


class TestLooksLikeJwt:
    def test_jwt_shape(self):
        assert looks_like_jwt("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln")

    def test_plain_key(self):
        assert not looks_like_jwt("aitbc-test-key")

    def test_dots_without_ey_prefix(self):
        assert not looks_like_jwt("aa.bb.cc")


class TestAuthClientKwargs:
    """Precedence: explicit key → credential store → config key."""

    def test_explicit_jwt_becomes_bearer(self):
        kwargs = auth_client_kwargs("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln", "cfg-key")
        assert kwargs == {"headers": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"}}

    def test_explicit_plain_key_becomes_api_key(self):
        kwargs = auth_client_kwargs("plain-key", "cfg-key")
        assert kwargs == {"api_key": "plain-key"}

    def test_stored_credential_preferred_over_config_key(self):
        with patch("aitbc_cli.auth.AuthManager") as mgr_cls:
            mgr_cls.return_value.get_credential.return_value = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"
            kwargs = auth_client_kwargs(None, "cfg-key")
        assert kwargs == {"headers": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"}}
        mgr_cls.return_value.get_credential.assert_called_once_with("client", quiet=True)

    def test_stored_plain_key_becomes_api_key(self):
        with patch("aitbc_cli.auth.AuthManager") as mgr_cls:
            mgr_cls.return_value.get_credential.return_value = "stored-plain-key"
            kwargs = auth_client_kwargs(None, "cfg-key")
        assert kwargs == {"api_key": "stored-plain-key"}

    def test_config_key_fallback_when_store_empty(self):
        with patch("aitbc_cli.auth.AuthManager") as mgr_cls:
            mgr_cls.return_value.get_credential.return_value = None
            kwargs = auth_client_kwargs(None, "cfg-key")
        assert kwargs == {"api_key": "cfg-key"}

    def test_no_credential_returns_empty(self):
        with patch("aitbc_cli.auth.AuthManager") as mgr_cls:
            mgr_cls.return_value.get_credential.return_value = None
            kwargs = auth_client_kwargs(None, None)
        assert kwargs == {}

    def test_store_skipped_when_disabled(self):
        with patch("aitbc_cli.auth.AuthManager") as mgr_cls:
            kwargs = auth_client_kwargs(None, "cfg-key", use_store=False)
        mgr_cls.assert_not_called()
        assert kwargs == {"api_key": "cfg-key"}

    def test_admin_credential_path(self):
        with patch("aitbc_cli.auth.AuthManager") as mgr_cls:
            mgr_cls.return_value.get_admin_token.return_value = "eyJhIiwiYiJ9.eyJ4In0=.c2ln"
            kwargs = auth_client_kwargs(None, "cfg-key", credential="admin")
        mgr_cls.return_value.get_admin_token.assert_called_once_with()
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")


class TestAuthHeaders:
    def test_bearer_header(self):
        headers = auth_headers("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln")
        assert headers == {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"}

    def test_api_key_header(self):
        headers = auth_headers("plain-key")
        assert headers == {"X-API-Key": "plain-key"}

    def test_empty(self):
        assert auth_headers(None, None, use_store=False) == {}
