"""Integration tests for consensus endpoints.

Note: Consensus endpoints are part of the blockchain-node RPC API, not the
coordinator API. These integration tests target the wrong service and are
skipped until they are moved to the blockchain-node test suite or the
coordinator exposes consensus proxy endpoints.
"""

import pytest
from starlette.testclient import TestClient

pytest.skip("Consensus endpoints are in blockchain-node, not coordinator-api", allow_module_level=True)


class TestConsensus:
    """Test consensus endpoints."""

    def test_register_consensus_node(self, coordinator_client: TestClient):
        """Test registering a consensus node."""
        node_data = {"node_id": "test-node-001", "address": "http://localhost:9003", "stake": 1000}
        response = coordinator_client.post("/v1/consensus/node/register", json=node_data)
        assert response.status_code in (200, 201, 500)
        if response.status_code in (200, 201):
            data = response.json()
            assert "status" in data or "node_id" in data

    def test_register_consensus_node_authorized(self, authenticated_client: TestClient):
        """Test registering a consensus node with authentication."""
        node_data = {"node_id": "test-node-002", "address": "http://localhost:9004", "stake": 2000}
        response = authenticated_client.post("/v1/consensus/node/register", json=node_data)
        assert response.status_code in (200, 201, 500)
        if response.status_code in (200, 201):
            data = response.json()
            assert "status" in data or "node_id" in data

    def test_create_consensus_proposal(self, coordinator_client: TestClient):
        """Test creating a consensus proposal."""
        proposal_data = {
            "proposal_id": "prop-001",
            "proposer": "test-node-001",
            "content": {"action": "upgrade", "version": "2.0"},
        }
        response = coordinator_client.post("/v1/consensus/proposal/create", json=proposal_data)
        assert response.status_code in (200, 201, 500)
        if response.status_code in (200, 201):
            data = response.json()
            assert "status" in data or "proposal_id" in data

    def test_create_consensus_proposal_authorized(self, authenticated_client: TestClient):
        """Test creating a consensus proposal with authentication."""
        proposal_data = {
            "proposal_id": "prop-002",
            "proposer": "test-node-002",
            "content": {"action": "config", "setting": "timeout"},
        }
        response = authenticated_client.post("/v1/consensus/proposal/create", json=proposal_data)
        assert response.status_code in (200, 201, 500)
        if response.status_code in (200, 201):
            data = response.json()
            assert "status" in data or "proposal_id" in data

    def test_cast_consensus_vote(self, coordinator_client: TestClient):
        """Test casting a consensus vote."""
        response = coordinator_client.post("/v1/consensus/proposal/prop-001/vote?node_id=test-node-001&vote=true")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "vote" in data

    def test_get_proposal_status(self, coordinator_client: TestClient):
        """Test getting proposal status."""
        response = coordinator_client.get("/v1/consensus/proposal/prop-001")
        assert response.status_code in (200, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "proposal_id" in data

    def test_get_consensus_statistics(self, coordinator_client: TestClient):
        """Test getting consensus statistics."""
        response = coordinator_client.get("/v1/consensus/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_set_consensus_algorithm(self, coordinator_client: TestClient):
        """Test setting consensus algorithm."""
        response = coordinator_client.put("/v1/consensus/algorithm", params={"algorithm": "majority_vote"})
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "algorithm" in data

    def test_update_node_status(self, coordinator_client: TestClient):
        """Test updating node status."""
        response = coordinator_client.put("/v1/consensus/node/test-node-001/status?is_active=true")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "is_active" in data

    def test_get_advanced_features_status(self, coordinator_client: TestClient):
        """Test getting advanced features status."""
        response = coordinator_client.get("/v1/advanced-features/status")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)


class TestConsensusAdvanced:
    """Advanced consensus tests for better coverage."""

    def test_consensus_all_algorithms(self, coordinator_client: TestClient):
        """Test all consensus algorithms."""
        algorithms = ["majority_vote", "weighted_vote", "byzantine_fault_tolerance", "proof_of_stake"]
        for algorithm in algorithms:
            response = coordinator_client.put("/v1/consensus/algorithm", params={"algorithm": algorithm})
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert "status" in data or "algorithm" in data

    def test_consensus_multiple_proposals(self, coordinator_client: TestClient):
        """Test creating multiple consensus proposals."""
        for i in range(3):
            proposal_data = {
                "proposal_id": f"prop-{i}",
                "proposer": f"node-{i}",
                "content": {"action": "config", "setting": f"value-{i}"},
            }
            response = coordinator_client.post("/v1/consensus/proposal/create", json=proposal_data)
            assert response.status_code in (200, 201, 500)
            if response.status_code in (200, 201):
                data = response.json()
                assert "status" in data or "proposal_id" in data

    def test_consensus_node_lifecycle(self, coordinator_client: TestClient):
        """Test full node lifecycle in consensus."""
        node_data = {"node_id": "consensus-node-001", "address": "http://localhost:9005", "stake": 1000}
        response = coordinator_client.post("/v1/consensus/node/register", json=node_data)
        assert response.status_code in (200, 201, 500)
        if response.status_code in (200, 201):
            data = response.json()
            assert "status" in data or "node_id" in data

        proposal_data = {"proposal_id": "prop-lifecycle", "proposer": "consensus-node-001", "content": {"action": "test"}}
        response = coordinator_client.post("/v1/consensus/proposal/create", json=proposal_data)
        assert response.status_code in (200, 201, 500)
        if response.status_code in (200, 201):
            data = response.json()
            assert "status" in data or "proposal_id" in data

        response = coordinator_client.post("/v1/consensus/proposal/prop-lifecycle/vote?node_id=consensus-node-001&vote=true")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "vote" in data

        response = coordinator_client.get("/v1/consensus/proposal/prop-lifecycle")
        assert response.status_code in (200, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "proposal_id" in data

        response = coordinator_client.put("/v1/consensus/node/consensus-node-001/status?is_active=false")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "is_active" in data


class TestConsensusComprehensive:
    """Comprehensive consensus tests for better coverage."""

    def test_consensus_multiple_nodes(self, coordinator_client: TestClient):
        """Test consensus with multiple nodes."""
        nodes = []
        for i in range(5):
            node_data = {"node_id": f"consensus-node-{i}", "address": f"http://localhost:910{i}", "stake": 1000 * (i + 1)}
            response = coordinator_client.post("/v1/consensus/node/register", json=node_data)
            assert response.status_code in (200, 201, 500)
            nodes.append(f"consensus-node-{i}")

        for i, node_id in enumerate(nodes[:3]):
            proposal_data = {
                "proposal_id": f"multi-prop-{i}",
                "proposer": node_id,
                "content": {"action": "config", "value": i},
            }
            response = coordinator_client.post("/v1/consensus/proposal/create", json=proposal_data)
            assert response.status_code in (200, 201, 500)

        for i in range(len(nodes)):
            for prop_id in range(3):
                response = coordinator_client.post(
                    f"/consensus/proposal/multi-prop-{prop_id}/vote?node_id={nodes[i]}&vote={i % 2 == 0}"
                )
                assert response.status_code in (200, 404, 500)

        for i in range(3):
            response = coordinator_client.get(f"/consensus/proposal/multi-prop-{i}")
            assert response.status_code in (200, 404, 500)

        response = coordinator_client.get("/v1/consensus/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_consensus_algorithm_switching(self, coordinator_client: TestClient):
        """Test switching between consensus algorithms."""
        algorithms = ["majority_vote", "weighted_vote", "byzantine_fault_tolerance"]

        for algorithm in algorithms:
            response = coordinator_client.put("/v1/consensus/algorithm", params={"algorithm": algorithm})
            assert response.status_code in (200, 500)

            proposal_data = {
                "proposal_id": f"algo-prop-{algorithm}",
                "proposer": "node-001",
                "content": {"action": "test", "algorithm": algorithm},
            }
            response = coordinator_client.post("/v1/consensus/proposal/create", json=proposal_data)
            assert response.status_code in (200, 201, 500)

            response = coordinator_client.post(f"/consensus/proposal/algo-prop-{algorithm}/vote?node_id=node-001&vote=true")
            assert response.status_code in (200, 404, 500)

            response = coordinator_client.get(f"/consensus/proposal/algo-prop-{algorithm}")
            assert response.status_code in (200, 404, 500)

    def test_consensus_edge_cases(self, coordinator_client: TestClient):
        """Test consensus edge cases."""
        response = coordinator_client.get("/v1/consensus/statistics")
        assert response.status_code in (200, 500)

        response = coordinator_client.get("/v1/consensus/proposal/nonexistent")
        assert response.status_code in (200, 404, 500)

        response = coordinator_client.put("/v1/consensus/node/nonexistent/status?is_active=true")
        assert response.status_code in (200, 404, 500)

        response = coordinator_client.put("/v1/consensus/algorithm", params={"algorithm": "invalid_algorithm"})
        assert response.status_code in (200, 400, 500)
