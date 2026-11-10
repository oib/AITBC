"""Tests for aitbc.network.url_safety — the shared SSRF guard for
operator/user-registered outbound URLs (webhook/callback stores, #1577).
"""

import asyncio
import socket

import pytest

from aitbc.network.url_safety import avalidate_outbound_url, validate_outbound_url


def _addrinfo(*addrs: str):
    """Fake getaddrinfo result tuples for the given IP strings."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 443)) for addr in addrs]


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))


@pytest.fixture
def private_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("10.1.2.3"))


@pytest.fixture
def mixed_dns(monkeypatch):
    """One public + one private answer — any non-global answer refuses."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34", "192.168.1.1"))


@pytest.fixture
def dead_dns(monkeypatch):
    def _raise(*a, **k):
        raise socket.gaierror("NXDOMAIN")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)


class TestValidateOutboundUrl:
    def test_public_host_accepted(self, public_dns):
        validate_outbound_url("https://hooks.example.com/alert")

    def test_http_scheme_accepted(self, public_dns):
        validate_outbound_url("http://example.com/hook")

    @pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "gopher://x/1", "//example.com"])
    def test_non_http_schemes_refused(self, url):
        with pytest.raises(ValueError):
            validate_outbound_url(url)

    def test_missing_host_refused(self):
        with pytest.raises(ValueError):
            validate_outbound_url("https:///path-only")

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/hook",
            "https://169.254.169.254/latest/meta-data",
            "http://10.0.0.5/internal",
            "http://192.168.1.1/",
            "http://[::1]/hook",
            "http://0.0.0.0/",
        ],
    )
    def test_literal_non_public_ips_refused(self, url):
        # Literal IPs resolve without DNS — deterministic even offline.
        with pytest.raises(ValueError):
            validate_outbound_url(url)

    def test_hostname_resolving_private_refused(self, private_dns):
        with pytest.raises(ValueError, match="non-public"):
            validate_outbound_url("https://internal.corp/hook")

    def test_mixed_resolution_refused(self, mixed_dns):
        with pytest.raises(ValueError, match="non-public"):
            validate_outbound_url("https://split.example.com/hook")

    def test_unresolvable_host_refused(self, dead_dns):
        with pytest.raises(ValueError, match="does not resolve"):
            validate_outbound_url("https://nope.invalid/hook")

    def test_allowlist_skips_dns(self, dead_dns, monkeypatch):
        monkeypatch.setenv("PARTNER_WEBHOOK_ALLOWED_TARGETS", "hooks.internal,10.0.0.5:8443")
        validate_outbound_url("https://hooks.internal/alert", allowlist_env="PARTNER_WEBHOOK_ALLOWED_TARGETS")
        validate_outbound_url("https://10.0.0.5:8443/hook", allowlist_env="PARTNER_WEBHOOK_ALLOWED_TARGETS")

    def test_allowlist_does_not_leak_across_env_vars(self, dead_dns):
        # A different env var name means the allowlist does not apply.
        with pytest.raises(ValueError):
            validate_outbound_url("https://hooks.internal/alert", allowlist_env="OTHER_TARGETS")

    def test_public_literal_ip_accepted(self):
        # No DNS needed for a literal global address.
        validate_outbound_url("https://93.184.216.34/hook")


class TestAValidateOutboundUrl:
    async def test_public_host_accepted(self, monkeypatch):
        async def _fake_getaddrinfo(self, host, port, *args, **kwargs):
            return _addrinfo("93.184.216.34")

        monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", _fake_getaddrinfo)
        await avalidate_outbound_url("https://example.com/hook")

    async def test_private_refused(self):
        with pytest.raises(ValueError):
            await avalidate_outbound_url("http://192.168.0.1/hook")
