"""Tests for the blockchain proxy routes, which every one of them 500'd.

``GET /v1/blocks/{height}`` and its siblings imported ``..config`` -- a module
that does not exist; the real one is ``....config``. The import sat inside the
function body, so nothing failed at import time, and ``except NetworkError`` did
not catch ImportError, so the only symptom was a 500 with no useful body. Only
``/status`` and ``/sync-status`` had tests, and they were the two handlers that
spelled the import correctly.

The second thing pinned here is the difference between a block the node does not
have and a node that is not answering. Both used to come back as status 200 with
``{"status": "error", "error": "RPC connection failed"}``.
"""

from __future__ import annotations

import importlib
import inspect
import re
from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.exceptions import NetworkError

# The routers package rebinds the name ``blockchain`` to the router object, so
# the module itself has to be imported by path rather than as an attribute.
blockchain_module = importlib.import_module("coordinator_api.contexts.blockchain.routers.blockchain")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(blockchain_module.router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


def _network_error_for_status(status: int) -> NetworkError:
    """Build the exception AITBCHTTPClient raises when the node answers ``status``."""
    response = requests.Response()
    response.status_code = status
    cause = requests.HTTPError(f"{status} Client Error", response=response)
    error = NetworkError(f"GET request failed: {cause}")
    error.__cause__ = cause
    return error


@pytest.mark.unit
class TestBlockRoutes:
    @patch("coordinator_api.config.settings")
    @patch("coordinator_api.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_a_block_by_height_reaches_the_node_and_comes_back(self, mock_client_class, mock_settings):
        """The regression test proper: this answered 500 before the import was fixed."""
        mock_settings.blockchain_rpc_url = "http://localhost:8202"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"height": 12900, "hash": "0xabc", "tx_count": 2}

        response = _client().get("/v1/blocks/12900")

        assert response.status_code == 200
        assert response.json()["height"] == 12900
        mock_client.get.assert_called_once_with("http://localhost:8202/rpc/blocks/12900")

    @patch("coordinator_api.config.settings")
    @patch("coordinator_api.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_a_height_the_node_does_not_have_is_a_404(self, mock_client_class, mock_settings):
        """A missing block is an answer, not an outage, and must not read as 200."""
        mock_settings.blockchain_rpc_url = "http://localhost:8202"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = _network_error_for_status(404)

        response = _client().get("/v1/blocks/99999999")

        assert response.status_code == 404

    @patch("coordinator_api.config.settings")
    @patch("coordinator_api.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_an_unreachable_node_is_a_502(self, mock_client_class, mock_settings):
        """A chain that is down is the coordinator's upstream failing, not the caller's."""
        mock_settings.blockchain_rpc_url = "http://localhost:8202"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = NetworkError("Connection refused")

        response = _client().get("/v1/blocks/12900")

        assert response.status_code == 502

    @patch("coordinator_api.config.settings")
    @patch("coordinator_api.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_block_by_hash_is_its_own_route_and_not_a_height(self, mock_client_class, mock_settings):
        """``/blocks/hash/{h}`` spans two segments, so it cannot collide with ``{height}``."""
        mock_settings.blockchain_rpc_url = "http://localhost:8202"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"hash": "0xabc"}

        response = _client().get("/v1/blocks/hash/0xabc")

        assert response.status_code == 200
        mock_client.get.assert_called_once_with("http://localhost:8202/rpc/blocks/hash/0xabc")

    @patch("coordinator_api.config.settings")
    @patch("coordinator_api.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_the_transaction_route_uses_the_path_the_node_serves(self, mock_client_class, mock_settings):
        """The node serves ``/rpc/transaction/{hash}``; the plural spelling always 404'd."""
        mock_settings.blockchain_rpc_url = "http://localhost:8202"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"tx_hash": "0xdead"}

        _client().get("/v1/transactions/0xdead")

        mock_client.get.assert_called_once_with("http://localhost:8202/rpc/transaction/0xdead")


@pytest.mark.unit
def test_every_relative_import_in_the_module_resolves():
    """The general form of the bug: a relative import at the wrong depth.

    These live inside function bodies, so they are not executed at import time
    and no amount of collecting the module proves them good. Resolve each one by
    hand instead, which fails for any handler added at the wrong depth again.
    """
    source = inspect.getsource(blockchain_module)
    package = blockchain_module.__name__.rsplit(".", 1)[0]

    broken = []
    for dots, name in re.findall(r"^\s*from (\.+)(\w[\w.]*) import ", source, re.MULTILINE):
        try:
            importlib.import_module(dots + name, package)
        except ImportError as exc:
            broken.append(f"{dots}{name} -> {exc}")

    assert broken == [], f"relative imports that do not resolve from {package}: {broken}"
