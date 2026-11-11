"""#1789 — BroadcastGossipBackend refuses unauthenticated remote redis.

The broadcast bus is a same-host transport: fleet deployments bind redis
to loopback and carry the password in ``GOSSIP_BROADCAST_URL``. Remote,
untrusted gossip enters via the relay/websocket path, which has the
validator challenge/response auth. What the bus must never become is a
remote-unauthenticated pub/sub channel — ``start()`` now fails closed on
a non-loopback redis URL with no password.
"""

from __future__ import annotations

import pytest
from aitbc_chain.gossip.backends.broadcast import BroadcastGossipBackend


def test_loopback_without_password_allowed() -> None:
    BroadcastGossipBackend._check_url_auth("redis://127.0.0.1:6379/0")
    BroadcastGossipBackend._check_url_auth("redis://localhost:6379")
    BroadcastGossipBackend._check_url_auth("redis://[::1]:6379/0")


def test_loopback_with_password_allowed() -> None:
    BroadcastGossipBackend._check_url_auth("redis://:s3cret@127.0.0.1:6379/0")
    BroadcastGossipBackend._check_url_auth("redis://default:s3cret@localhost:6379/0")


def test_remote_without_password_rejected() -> None:
    with pytest.raises(ValueError, match="no password"):
        BroadcastGossipBackend._check_url_auth("redis://redis.example.com:6379/0")
    with pytest.raises(ValueError, match="no password"):
        BroadcastGossipBackend._check_url_auth("rediss://10.0.0.5:6380")


def test_remote_with_password_allowed() -> None:
    BroadcastGossipBackend._check_url_auth("redis://:s3cret@redis.example.com:6379/0")
    BroadcastGossipBackend._check_url_auth("rediss://default:s3cret@10.0.0.5:6380")


def test_non_redis_scheme_passes_through() -> None:
    # from_url rejects unsupported schemes itself; the auth check must not
    # misparse them (e.g. unix sockets carry no host at all).
    BroadcastGossipBackend._check_url_auth("unix:///var/run/redis.sock")


@pytest.mark.asyncio
async def test_start_fails_closed_on_remote_passwordless_url() -> None:
    backend = BroadcastGossipBackend("redis://redis.example.com:6379/0")
    with pytest.raises(ValueError, match="no password"):
        await backend.start()
    assert backend._redis is None
    assert backend._running is False
