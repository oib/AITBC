"""Miner test configuration.

production_miner validates environment variables at import time, so these must be
set before the module is first imported by the test files.
"""

import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("MINER_ID", "test-miner")
os.environ.setdefault("MINER_AUTH_TOKEN", "test-auth-token")


@contextmanager
def _mock_http(get=None, post=None):
    """Patch the ``AITBCHTTPClient`` that ``production_miner`` constructs.

    These tests were written against a version that called ``httpx`` at module scope and
    patched ``production_miner.httpx.get``. The module now goes through
    ``aitbc.network.AITBCHTTPClient``, whose ``get``/``post`` return **parsed JSON** rather
    than a response object — so a mock returning ``Mock(status_code=200, json=...)`` does not
    resemble anything the code will see. Yield dicts.

    ``get``/``post`` may each be a value to return, an exception instance to raise, or a
    callable taking the same arguments as the client method.
    """

    def _behaviour(spec):
        if spec is None:
            return MagicMock(return_value=None)
        if isinstance(spec, BaseException):
            return MagicMock(side_effect=spec)
        if callable(spec):
            return MagicMock(side_effect=spec)
        return MagicMock(return_value=spec)

    instance = MagicMock()
    instance.get = _behaviour(get)
    instance.post = _behaviour(post)

    # The module constructs a client per call, so patch the class and hand back one instance.
    with patch("production_miner.AITBCHTTPClient", return_value=instance) as client_class:
        client_class.instance = instance
        yield client_class


@pytest.fixture
def mock_http():
    """Expose ``_mock_http`` as a fixture — conftest is not importable as a module."""
    return _mock_http
