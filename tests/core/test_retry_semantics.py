"""Regression tests for method-aware retry semantics (W2c).

The pre-review behavior retried every request on every requests/httpx error —
including writes whose outcome was unknown. The policy now distinguishes:

- pre-send failures (connect refused, DNS, connect timeout): retried for any
  method — the request provably never left the process
- ambiguous failures (read timeouts, mid-stream protocol errors, 5xx
  responses): retried only for spec-idempotent methods, or any method when
  the caller asserts upstream dedup via retry_ambiguous=True
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

from aitbc.network.retry_policy import RetryPolicy
from aitbc_errors import AmbiguousRequestError, RetryError


def _conn_refused() -> requests.ConnectionError:
    """A requests.ConnectionError whose cause chain shows the connection was
    never established — the request provably never reached the server."""
    cause = MaxRetryError(None, "/", NewConnectionError(None, "connection refused"))
    err = requests.ConnectionError("connection refused")
    err.__cause__ = cause
    return err


def _midstream_reset() -> requests.ConnectionError:
    """A ConnectionError whose cause is a mid-stream protocol error — the
    request may already have been sent. Ambiguous."""
    cause = MaxRetryError(None, "/", ProtocolError("connection reset by peer"))
    err = requests.ConnectionError("connection reset")
    err.__cause__ = cause
    return err


class TestSyncPresendRetries:
    """Pre-send failures retry regardless of method."""

    def test_post_connect_timeout_retries(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=[requests.ConnectTimeout("timed out"), {"ok": True}])
        assert policy.execute(fn, method="POST") == {"ok": True}
        assert fn.call_count == 2

    def test_post_conn_refused_retries(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=[_conn_refused(), {"ok": True}])
        assert policy.execute(fn, method="POST") == {"ok": True}
        assert fn.call_count == 2

    def test_presend_exhaustion_raises_retry_error(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=requests.ConnectTimeout("timed out"))
        with pytest.raises(RetryError):
            policy.execute(fn, method="POST")
        assert fn.call_count == 3


class TestSyncAmbiguousWrites:
    """Ambiguous failures refuse to replay non-idempotent writes."""

    def test_post_read_timeout_not_retried(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=requests.ReadTimeout("read timed out"))
        with pytest.raises(AmbiguousRequestError):
            policy.execute(fn, method="POST")
        assert fn.call_count == 1

    def test_post_midstream_reset_not_retried(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=_midstream_reset())
        with pytest.raises(AmbiguousRequestError):
            policy.execute(fn, method="POST")
        assert fn.call_count == 1

    def test_patch_read_timeout_not_retried(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=requests.ReadTimeout("read timed out"))
        with pytest.raises(AmbiguousRequestError):
            policy.execute(fn, method="PATCH")
        assert fn.call_count == 1

    def test_post_5xx_not_retried(self):
        response = Mock()
        response.status_code = 502
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=requests.HTTPError("bad gateway", response=response))
        with pytest.raises(AmbiguousRequestError):
            policy.execute(fn, method="POST")
        assert fn.call_count == 1

    def test_post_with_idempotency_retries_read_timeout(self):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=[requests.ReadTimeout("read timed out"), {"ok": True}])
        assert policy.execute(fn, method="POST", retry_ambiguous=True) == {"ok": True}
        assert fn.call_count == 2

    def test_post_with_idempotency_retries_5xx(self):
        response = Mock()
        response.status_code = 503
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=[requests.HTTPError("unavailable", response=response), {"ok": True}])
        assert policy.execute(fn, method="POST", retry_ambiguous=True) == {"ok": True}
        assert fn.call_count == 2


class TestSyncIdempotentMethods:
    """Spec-idempotent methods keep retrying ambiguous failures."""

    @pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "HEAD", "OPTIONS"])
    def test_safe_method_retries_read_timeout(self, method):
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=[requests.ReadTimeout("read timed out"), {"ok": True}])
        assert policy.execute(fn, method=method) == {"ok": True}
        assert fn.call_count == 2

    def test_get_5xx_retries(self):
        response = Mock()
        response.status_code = 502
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=[requests.HTTPError("bad gateway", response=response), {"ok": True}])
        assert policy.execute(fn, method="GET") == {"ok": True}
        assert fn.call_count == 2

    def test_4xx_never_retried_even_for_safe_methods(self):
        response = Mock()
        response.status_code = 404
        policy = RetryPolicy(max_retries=2)
        fn = Mock(side_effect=requests.HTTPError("not found", response=response))
        with pytest.raises(requests.HTTPError):
            policy.execute(fn, method="GET")
        assert fn.call_count == 1


class TestAsyncSemantics:
    """execute_async uses httpx — transport errors are now actually classified
    (previously the async path caught requests.* exceptions and never matched)."""

    def test_post_connect_error_retries(self):
        policy = RetryPolicy(max_retries=2)
        fn = AsyncMock(side_effect=[httpx.ConnectError("refused"), {"ok": True}])

        async def call():
            return await policy.execute_async(fn, method="POST")

        assert asyncio.run(call()) == {"ok": True}
        assert fn.call_count == 2

    def test_post_read_timeout_not_retried(self):
        policy = RetryPolicy(max_retries=2)
        fn = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))

        async def call():
            return await policy.execute_async(fn, method="POST")

        with pytest.raises(AmbiguousRequestError):
            asyncio.run(call())
        assert fn.call_count == 1

    def test_post_with_idempotency_retries(self):
        policy = RetryPolicy(max_retries=2)
        fn = AsyncMock(side_effect=[httpx.ReadTimeout("read timed out"), {"ok": True}])

        async def call():
            return await policy.execute_async(fn, method="POST", retry_ambiguous=True)

        assert asyncio.run(call()) == {"ok": True}
        assert fn.call_count == 2

    def test_get_read_timeout_retries(self):
        policy = RetryPolicy(max_retries=2)
        fn = AsyncMock(side_effect=[httpx.ReadTimeout("read timed out"), {"ok": True}])

        async def call():
            return await policy.execute_async(fn, method="GET")

        assert asyncio.run(call()) == {"ok": True}
        assert fn.call_count == 2
