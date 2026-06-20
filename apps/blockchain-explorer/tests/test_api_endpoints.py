"""
Comprehensive API endpoint tests for the blockchain explorer.

These tests exercise every public endpoint via TestClient. Endpoints that
call external blockchain RPC via httpx are mocked; endpoints that read from
the local sqlite chain DB gracefully return empty results when the DB is
absent (test environment).

Replaces the stub integration tests that were previously `pass`.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


# --- Chains ---


def test_list_chains(client):
    """GET /api/chains returns supported chains"""
    response = client.get("/api/chains")
    assert response.status_code == 200
    data = response.json()
    assert "chains" in data
    assert len(data["chains"]) >= 2
    assert data["chains"][0]["status"] == "active"


# --- Health ---


def test_health_check(client):
    """GET /health returns status and version"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["version"] == "2.0.0"
    assert "features" in data


def test_root_endpoint_404(client):
    """GET / returns 404 (static files served by nginx, not FastAPI)"""
    response = client.get("/")
    assert response.status_code == 404


# --- Chain head (mocked RPC) ---


def test_api_chain_head_success(client):
    """GET /api/chain/head returns block data when RPC is available"""
    mock_block = {"height": 42, "hash": "0xabc123", "proposer": "node-1", "tx_count": 5}

    with patch("main.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_block
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        response = client.get("/api/chain/head")
        assert response.status_code == 200
        data = response.json()
        assert data["height"] == 42


def test_api_chain_head_rpc_error(client):
    """GET /api/chain/head returns empty dict when RPC fails"""
    with patch("main.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        response = client.get("/api/chain/head")
        assert response.status_code == 200
        assert response.json() == {}


# --- Analytics: network stats ---


def test_api_network_stats(client):
    """GET /api/analytics/network-stats returns stats structure"""
    response = client.get("/api/analytics/network-stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_ait" in data
    assert "active_offers" in data
    assert "unique_nodes" in data
    assert "unique_providers" in data
    assert "total_transactions" in data


def test_api_network_stats_with_chain_id(client):
    """GET /api/analytics/network-stats accepts chain_id param"""
    response = client.get("/api/analytics/network-stats", params={"chain_id": "ait-hub.aitbc.bubuit.net"})
    assert response.status_code == 200


# --- Analytics: activity timeline ---


def test_api_activity_timeline(client):
    """GET /api/analytics/activity returns labels and datasets"""
    response = client.get("/api/analytics/activity", params={"days": 7})
    assert response.status_code == 200
    data = response.json()
    assert "labels" in data
    assert "datasets" in data


def test_api_activity_timeline_default_days(client):
    """GET /api/analytics/activity with default days=30"""
    response = client.get("/api/analytics/activity")
    assert response.status_code == 200
    data = response.json()
    assert "labels" in data
    assert "datasets" in data


# --- Analytics: top addresses ---


def test_api_top_addresses(client):
    """GET /api/analytics/top-addresses returns addresses list"""
    response = client.get("/api/analytics/top-addresses", params={"limit": 10})
    assert response.status_code == 200
    data = response.json()
    assert "addresses" in data
    assert isinstance(data["addresses"], list)


def test_api_top_addresses_default_limit(client):
    """GET /api/analytics/top-addresses with default limit=20"""
    response = client.get("/api/analytics/top-addresses")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["addresses"], list)


# --- Analytics: provider reputation ---


def test_api_provider_reputation(client):
    """GET /api/analytics/provider-reputation/{id} returns reputation structure"""
    response = client.get("/api/analytics/provider-reputation/test-provider")
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "level" in data
    assert data["provider_id"] == "test-provider"


def test_api_provider_reputation_score_range(client):
    """Provider reputation score is 0-100"""
    response = client.get("/api/analytics/provider-reputation/some-provider")
    data = response.json()
    assert 0 <= data["score"] <= 100


def test_api_provider_reputation_level_values(client):
    """Provider reputation level is one of the defined tiers"""
    response = client.get("/api/analytics/provider-reputation/another-provider")
    data = response.json()
    assert data["level"] in ("New", "Growing", "Established", "Trusted", "Elite")


# --- Blocks: latest ---


def test_api_latest_blocks(client):
    """GET /api/blocks/latest returns blocks list"""
    response = client.get("/api/blocks/latest", params={"limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert "blocks" in data
    assert isinstance(data["blocks"], list)


def test_api_latest_blocks_with_offset(client):
    """GET /api/blocks/latest with offset param"""
    response = client.get("/api/blocks/latest", params={"limit": 5, "offset": 10})
    assert response.status_code == 200
    data = response.json()
    assert "blocks" in data


# --- Blocks: non-empty ---


def test_api_non_empty_blocks(client):
    """GET /api/blocks/non-empty returns blocks list"""
    response = client.get("/api/blocks/non-empty", params={"limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert "blocks" in data
    assert isinstance(data["blocks"], list)


# --- Blocks: by height ---


def test_api_block_by_height(client):
    """GET /api/blocks/{height} returns block data with transactions"""
    response = client.get("/api/blocks/1")
    assert response.status_code == 200
    data = response.json()
    # Block data may be empty dict if DB unavailable, but should have transactions key
    assert "transactions" in data


# --- Blocks: by hash ---


def test_api_block_by_hash(client):
    """GET /api/blocks/by-hash/{hash} returns block data or empty"""
    response = client.get("/api/blocks/by-hash/0x" + "a" * 64)
    assert response.status_code == 200


def test_api_block_by_hash_invalid(client):
    """GET /api/blocks/by-hash with invalid hash returns empty dict (200)"""
    response = client.get("/api/blocks/by-hash/invalid-hash")
    assert response.status_code == 200
    assert response.json() == {}


# --- Transactions: by hash ---


def test_api_transaction_by_hash(client):
    """GET /api/transactions/by-hash/{hash} returns tx data or empty"""
    response = client.get("/api/transactions/by-hash/0x" + "a" * 64)
    assert response.status_code == 200


def test_api_transaction_by_hash_invalid(client):
    """GET /api/transactions/by-hash with invalid hash returns empty dict (200)"""
    response = client.get("/api/transactions/by-hash/invalid-hash")
    assert response.status_code == 200
    assert response.json() == {}


# --- Transactions: search by address ---


def test_api_search_transactions_by_address(client):
    """GET /api/transactions/search?address=... returns transactions list"""
    response = client.get("/api/transactions/search", params={"address": "test-address"})
    assert response.status_code == 200
    data = response.json()
    assert "transactions" in data
    assert isinstance(data["transactions"], list)


def test_api_search_transactions_missing_address(client):
    """GET /api/transactions/search without address param returns 422"""
    response = client.get("/api/transactions/search")
    assert response.status_code == 422


# --- Blocks: by address ---


def test_api_blocks_by_address(client):
    """GET /api/blocks/by-address/{address} returns blocks list"""
    response = client.get("/api/blocks/by-address/test-address")
    assert response.status_code == 200
    data = response.json()
    assert "blocks" in data
    assert isinstance(data["blocks"], list)


# --- Transactions: get by hash (legacy endpoint) ---


def test_api_get_transaction(client):
    """GET /api/transactions/{tx_hash} returns tx data or empty"""
    response = client.get("/api/transactions/0x" + "a" * 64)
    assert response.status_code == 200


# --- Advanced search: transactions (mocked RPC) ---


def test_search_transactions_advanced(client):
    """GET /api/search/transactions with filters (mocked data layer)"""
    mock_result = {"transactions": [{"hash": "0x123", "type": "transfer"}]}

    with patch("main.get_data_layer") as mock_get_dl:
        mock_dl = AsyncMock()
        mock_dl.get_transactions = AsyncMock(return_value=mock_result)
        mock_get_dl.return_value = mock_dl

        response = client.get(
            "/api/search/transactions",
            params={"address": "0xabc", "tx_type": "transfer", "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data


def test_search_transactions_rpc_404(client):
    """GET /api/search/transactions returns empty list when RPC returns 404"""
    with patch("main.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        response = client.get("/api/search/transactions")
        assert response.status_code == 200
        assert response.json() == {"transactions": []}


def test_search_transactions_rpc_error(client):
    """GET /api/search/transactions returns 503 when RPC is unavailable"""
    with patch("main.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        response = client.get("/api/search/transactions")
        assert response.status_code in (500, 503)


# --- Advanced search: blocks (mocked RPC) ---


def test_search_blocks_advanced(client):
    """GET /api/search/blocks with filters (mocked data layer)"""
    mock_result = {"blocks": [{"height": 1, "hash": "0x123"}]}

    with patch("main.get_data_layer") as mock_get_dl:
        mock_dl = AsyncMock()
        mock_dl.get_blocks = AsyncMock(return_value=mock_result)
        mock_get_dl.return_value = mock_dl

        response = client.get("/api/search/blocks", params={"validator": "node-1", "min_tx": 5})
        assert response.status_code == 200
        data = response.json()
        assert "blocks" in data


def test_search_blocks_rpc_404(client):
    """GET /api/search/blocks returns empty list when RPC returns 404"""
    with patch("main.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        response = client.get("/api/search/blocks")
        assert response.status_code == 200
        assert response.json() == {"blocks": []}


# --- Analytics: overview (mocked data layer) ---


def test_analytics_overview_success(client):
    """GET /api/analytics/overview returns overview data (mocked data layer)"""
    mock_overview = {"total_transactions": 100, "total_blocks": 50}

    with patch("main.get_data_layer") as mock_get_dl:
        mock_dl = AsyncMock()
        mock_dl.get_analytics_overview = AsyncMock(return_value=mock_overview)
        mock_get_dl.return_value = mock_dl

        response = client.get("/api/analytics/overview", params={"period": "24h"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_transactions"] == 100


def test_analytics_overview_rpc_404(client):
    """GET /api/analytics/overview returns 500 when data layer fails"""
    with patch("main.get_data_layer") as mock_get_dl:
        mock_dl = AsyncMock()
        mock_dl.get_analytics_overview = AsyncMock(side_effect=Exception("RPC endpoint not available"))
        mock_get_dl.return_value = mock_dl

        response = client.get("/api/analytics/overview")
        assert response.status_code == 500


# --- Export: search results ---


def test_export_search_csv(client):
    """GET /api/export/search?format=csv exports transactions as CSV"""
    test_data = [
        {
            "hash": "0x123",
            "type": "transfer",
            "from": "0xabc",
            "to": "0xdef",
            "amount": "1.0",
            "fee": "0.001",
            "timestamp": "2024-01-01",
        }
    ]
    response = client.get(
        "/api/export/search", params={"format": "csv", "type": "transactions", "data": json.dumps(test_data)}
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert "attachment" in response.headers.get("content-disposition", "")


def test_export_search_json(client):
    """GET /api/export/search?format=json exports as JSON"""
    test_data = [{"hash": "0x123", "type": "transfer"}]
    response = client.get(
        "/api/export/search", params={"format": "json", "type": "transactions", "data": json.dumps(test_data)}
    )
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")


def test_export_search_blocks_csv(client):
    """GET /api/export/search exports blocks as CSV"""
    test_data = [{"height": 1, "hash": "0x123", "validator": "node-1", "tx_count": 5, "timestamp": "2024-01-01"}]
    response = client.get("/api/export/search", params={"format": "csv", "type": "blocks", "data": json.dumps(test_data)})
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


def test_export_search_no_data(client):
    """GET /api/export/search with no data returns 400"""
    response = client.get("/api/export/search", params={"format": "csv", "type": "transactions", "data": ""})
    assert response.status_code in (400, 500)


def test_export_search_unsupported_format(client):
    """GET /api/export/search with unsupported format returns 400 or 500"""
    test_data = [{"hash": "0x123"}]
    response = client.get(
        "/api/export/search", params={"format": "xml", "type": "transactions", "data": json.dumps(test_data)}
    )
    assert response.status_code in (400, 500)


# --- Export: blocks ---


def test_export_blocks_csv(client):
    """GET /api/export/blocks?format=csv exports latest blocks as CSV"""
    response = client.get("/api/export/blocks", params={"format": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


def test_export_blocks_json(client):
    """GET /api/export/blocks?format=json exports as JSON"""
    response = client.get("/api/export/blocks", params={"format": "json"})
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")


# --- Validation functions ---


def test_validate_tx_hash_valid():
    """Test tx hash validation with valid hashes"""
    from main import validate_tx_hash

    assert validate_tx_hash("0x" + "a" * 64) is True
    assert validate_tx_hash("a" * 64) is True
    assert validate_tx_hash("0x" + "A" * 64) is True


def test_validate_tx_hash_invalid():
    """Test tx hash validation rejects invalid hashes"""
    from main import validate_tx_hash

    assert validate_tx_hash("") is False
    assert validate_tx_hash("short") is False
    assert validate_tx_hash("0x" + "g" * 64) is False  # non-hex char
    assert validate_tx_hash("0x" + "a" * 64 + "/path") is False  # path traversal
    assert validate_tx_hash("0x" + "a" * 64 + "..") is False


def test_validate_chain_id_valid():
    """Test chain ID validation with valid IDs"""
    from main import validate_chain_id

    assert validate_chain_id("ait-hub.aitbc.bubuit.net") is True
    assert validate_chain_id("ait-mainnet") is True
    assert validate_chain_id("test-chain-123") is True


def test_validate_chain_id_invalid():
    """Test chain ID validation rejects invalid IDs"""
    from main import validate_chain_id

    assert validate_chain_id("") is False
    assert validate_chain_id("ab") is False  # too short
    assert validate_chain_id("chain/with/slashes") is False
    assert validate_chain_id("chain..traversal") is False
    assert validate_chain_id("chain?query") is False


# --- Pydantic models ---


def test_transaction_search_model_defaults():
    """Test TransactionSearch model defaults"""
    from main import TransactionSearch

    search = TransactionSearch()
    assert search.address is None
    assert search.amount_min is None
    assert search.limit == 50
    assert search.offset == 0


def test_transaction_search_model_with_values():
    """Test TransactionSearch model with all fields"""
    from main import TransactionSearch

    search = TransactionSearch(
        address="0x123",
        amount_min=1.0,
        amount_max=100.0,
        tx_type="transfer",
        since="2024-01-01",
        until="2024-12-31",
        limit=100,
        offset=10,
    )
    assert search.address == "0x123"
    assert search.amount_max == 100.0
    assert search.limit == 100


def test_block_search_model_defaults():
    """Test BlockSearch model defaults"""
    from main import BlockSearch

    search = BlockSearch()
    assert search.validator is None
    assert search.limit == 50
    assert search.offset == 0


def test_block_search_model_with_values():
    """Test BlockSearch model with all fields"""
    from main import BlockSearch

    search = BlockSearch(validator="node-1", since="2024-01-01", until="2024-12-31", min_tx=5, limit=25, offset=5)
    assert search.validator == "node-1"
    assert search.min_tx == 5
    assert search.limit == 25
