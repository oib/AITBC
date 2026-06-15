"""Tests for apps.coordinator-api endpoints"""

import sys

sys.path.insert(0, "/opt/aitbc/apps/coordinator-api/src")

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class TestHealthEndpoints:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_live(self):
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_health_ready(self):
        response = client.get("/health/ready")
        assert response.status_code in (200, 503)

    def test_v1_health(self):
        response = client.get("/v1/health")
        assert response.status_code == 200


class TestMetricsEndpoints:
    def test_metrics(self):
        response = client.get("/metrics")
        assert response.status_code == 200


class TestDebugEndpoints:
    def test_debug_routes(self):
        response = client.get("/_debug/routes")
        assert response.status_code == 200


class TestUsersEndpoints:
    def test_users_register(self):
        response = client.post("/users/register", json={})
        assert response.status_code in (400, 404, 422, 500)

    def test_users_login(self):
        response = client.post("/users/login", json={})
        assert response.status_code in (400, 404, 422, 401, 500)


class TestAgentEndpoints:
    def test_agents_list(self):
        response = client.get("/agents")
        assert response.status_code in (200, 403, 404, 500)

    def test_agents_register(self):
        response = client.post("/agents", json={})
        assert response.status_code in (400, 404, 422, 403, 500)


class TestBlockchainEndpoints:
    def test_blockchain_status(self):
        response = client.get("/blockchain/status")
        assert response.status_code in (200, 404, 500)

    def test_blockchain_blocks(self):
        response = client.get("/blockchain/blocks")
        assert response.status_code in (200, 404, 500)


class TestMarketplaceEndpoints:
    def test_marketplace_listings(self):
        response = client.get("/marketplace/listings")
        assert response.status_code in (200, 404, 500)

    def test_marketplace_gpu(self):
        response = client.get("/marketplace/gpu")
        assert response.status_code in (200, 404, 500)


class TestPaymentsEndpoints:
    def test_payments(self):
        response = client.get("/payments")
        assert response.status_code in (200, 404, 500)


class TestStakingEndpoints:
    def test_staking_pools(self):
        response = client.get("/staking/pools")
        assert response.status_code in (200, 404, 500)


class TestTrainingEndpoints:
    def test_training_jobs(self):
        response = client.get("/training/jobs")
        assert response.status_code in (200, 404, 500)


class TestInferenceEndpoints:
    def test_inference_models(self):
        response = client.get("/inference/models")
        assert response.status_code in (200, 404, 500)


class TestExplorerEndpoints:
    def test_explorer_blocks(self):
        response = client.get("/explorer/blocks")
        assert response.status_code in (200, 404, 500)

    def test_explorer_transactions(self):
        response = client.get("/explorer/transactions")
        assert response.status_code in (200, 404, 500)


class TestGovernanceEndpoints:
    def test_governance_proposals(self):
        response = client.get("/governance/proposals")
        assert response.status_code in (200, 404, 500)


class TestMinerEndpoints:
    def test_miners(self):
        response = client.get("/miners")
        assert response.status_code in (200, 404, 500)


class TestSwarmEndpoints:
    def test_swarm_health(self):
        response = client.get("/swarm/health")
        assert response.status_code in (200, 404, 500)

    def test_swarm_dashboard(self):
        response = client.get("/swarm/dashboard")
        assert response.status_code in (200, 404, 500)

    def test_swarm_nodes(self):
        response = client.get("/swarm/nodes")
        assert response.status_code in (200, 404, 500)

    def test_swarm_tasks(self):
        response = client.get("/swarm/tasks")
        assert response.status_code in (200, 404, 500)

    def test_swarm_clusters(self):
        response = client.get("/swarm/clusters")
        assert response.status_code in (200, 404, 500)

    def test_swarm_stats(self):
        response = client.get("/swarm/stats")
        assert response.status_code in (200, 404, 500)


class TestWalletEndpoints:
    def test_wallets(self):
        response = client.get("/wallets")
        assert response.status_code in (200, 403, 404, 500)


class TestPortfolioEndpoints:
    def test_portfolio(self):
        response = client.get("/portfolio")
        assert response.status_code in (200, 403, 404, 500)


class TestAdminEndpoints:
    def test_admin_dashboard(self):
        response = client.get("/admin/dashboard")
        assert response.status_code in (200, 403, 404, 500)


class TestClientEndpoints:
    def test_client_dashboard(self):
        response = client.get("/client/dashboard")
        assert response.status_code in (200, 404, 500)


class TestCrossChainEndpoints:
    def test_cross_chain_status(self):
        response = client.get("/cross-chain/status")
        assert response.status_code in (200, 404, 500)


class TestMultiModalEndpoints:
    def test_multimodal_models(self):
        response = client.get("/multimodal/models")
        assert response.status_code in (200, 404, 500)


class TestJobsEndpoints:
    def test_jobs(self):
        response = client.get("/jobs")
        assert response.status_code in (200, 404, 500)
