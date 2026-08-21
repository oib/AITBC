"""Tests for the dashboard CLI commands."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def dashboard_ctx_obj():
    config = MagicMock()
    config.coordinator_api_url = "http://localhost:8203"
    config.wallet_daemon_url = "http://localhost:8108"
    config.gpu_service_url = "http://localhost:8101"
    config.hub_discovery_url = "hub.aitbc.bubuit.net"
    config.node_id = "aitbc3"
    config.chain_id = "ait-devnet"
    return {
        "output": "table",
        "output_format": "table",
        "url": None,
        "api_key": None,
        "verbose": 0,
        "debug": False,
        "config": config,
        "chain_id": "ait-devnet",
    }


class TestDashboardCustomer:
    @patch("aitbc_cli.commands.dashboard.AITBCHTTPClient")
    @patch("aitbc_cli.commands.dashboard._auth_headers")
    def test_customer_dashboard(self, mock_auth, mock_client_class, runner, dashboard_ctx_obj):
        mock_auth.return_value = {"Authorization": "Bearer token"}
        mock_client = mock_client_class.return_value
        mock_client.get.side_effect = [
            {
                "items": [
                    {"job_id": "job-1", "state": "COMPLETED", "payment_status": "released", "created_at": "2026-08-21T10:00:00"},
                    {"job_id": "job-2", "state": "QUEUED", "payment_status": "escrowed", "created_at": "2026-08-21T10:01:00"},
                ]
            },
            {"items": [{"wallet_id": "wallet-1", "address": "addr1"}]},
            {"balance": 1.5},
        ]

        from aitbc_cli.commands.dashboard import customer

        result = runner.invoke(customer, [], obj=dashboard_ctx_obj)

        assert result.exit_code == 0, result.output
        assert "Customer Dashboard" in result.output
        assert "job-1" in result.output
        assert "wallet-1" in result.output

    @patch("aitbc_cli.commands.dashboard.AITBCHTTPClient")
    @patch("aitbc_cli.commands.dashboard._auth_headers")
    def test_customer_dashboard_list_response(self, mock_auth, mock_client_class, runner, dashboard_ctx_obj):
        """Older hubs may return a list instead of a dict."""
        mock_auth.return_value = {"Authorization": "Bearer token"}
        mock_client = mock_client_class.return_value
        mock_client.get.side_effect = [
            [{"job_id": "job-1", "state": "COMPLETED"}],
            {"items": []},
        ]

        from aitbc_cli.commands.dashboard import customer

        result = runner.invoke(customer, [], obj=dashboard_ctx_obj)

        assert result.exit_code == 0, result.output
        assert "job-1" in result.output


class TestDashboardShop:
    @patch("aitbc_cli.commands.dashboard.AITBCHTTPClient")
    @patch("aitbc_cli.commands.dashboard._auth_headers")
    def test_shop_dashboard(self, mock_auth, mock_client_class, runner, dashboard_ctx_obj):
        mock_auth.return_value = {"Authorization": "Bearer token"}
        mock_client = mock_client_class.return_value

        def get_side_effect(path, **kwargs):
            if path == "/v1/monitoring/metrics":
                return {"jobs": {"total": 5, "completed": 3, "pending": 1, "failed": 1}, "miners": {"total": 1, "online": 1}}
            if path == "/v1/gpu/discover":
                return {"gpus": [{"id": "gpu-0"}]}
            if path == "/v1/marketplace/offer":
                return {"offers": [{"plugin_id": "p1", "model": "m1", "price": 0.1, "status": "active", "avg_rating": 4.0, "rating_count": 2, "node_id": "aitbc3"}]}
            if path == "/v1/wallets":
                return {"items": [{"wallet_id": "w1"}]}
            if path == "/v1/chains/ait-devnet/wallets/w1/balance":
                return {"balance": 2.0}
            return {}

        mock_client.get.side_effect = get_side_effect
        mock_client.post.side_effect = [
            {"items": [{"job_id": "job-1", "state": "COMPLETED"}]},
            {"total_earnings": 10.0, "paid_earnings": 5.0, "pending_earnings": 5.0},
        ]

        from aitbc_cli.commands.dashboard import shop

        result = runner.invoke(shop, ["--miner-id", "aitbc3"], obj=dashboard_ctx_obj)

        assert result.exit_code == 0, result.output
        assert "Shop Dashboard" in result.output
        assert "p1" in result.output
        assert "aitbc3" in result.output
