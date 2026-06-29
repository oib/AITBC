"""Integration tests for v0.6.5 Agent Coordination — chain_id/island_id awareness.

Tests cover:
- B1: Config fields (blockchain_rpc_url, default_chain_id, default_island_id, escrow/TTL)
- B2: Agent registration with chain_id/island_id + discovery filters
- B4: Swarm + workflow chain_id models
- B5: Configurable agent TTL

Escrow-related tests (B3) are skipped until Agent A delivers PaymentEscrow (A1).
"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from src.app.config import settings
from src.app.models import AgentRegistrationRequest, TaskPayment, TaskSubmission
from src.app.routing.agent_discovery import (
    AgentInfo,
    AgentRegistry,
    create_agent_info,
)
from src.app.routers.swarm import CoordinateRequest, JoinRequest
from src.app.routers.workflow import CreateWorkflowRequest, ExecuteWorkflowRequest

from aitbc.crypto import EscrowStatus, PaymentEscrow


# ---------------------------------------------------------------------------
# B1: Config fields
# ---------------------------------------------------------------------------


class TestConfigFields:
    """Test v0.6.5 config fields exist with correct defaults."""

    def test_config_blockchain_rpc_url(self):
        assert hasattr(settings, "blockchain_rpc_url")
        assert settings.blockchain_rpc_url.startswith("http://")

    def test_config_default_chain_id(self):
        assert hasattr(settings, "default_chain_id")
        assert settings.default_chain_id == "ait-hub"

    def test_config_default_island_id(self):
        assert hasattr(settings, "default_island_id")
        assert isinstance(settings.default_island_id, str)

    def test_config_task_payment_escrow_enabled(self):
        assert hasattr(settings, "task_payment_escrow_enabled")
        assert isinstance(settings.task_payment_escrow_enabled, bool)

    def test_config_task_payment_timeout_seconds(self):
        assert hasattr(settings, "task_payment_timeout_seconds")
        assert settings.task_payment_timeout_seconds > 0

    def test_config_task_max_retries(self):
        assert hasattr(settings, "task_max_retries")
        assert settings.task_max_retries > 0

    def test_config_agent_heartbeat_timeout_seconds(self):
        assert hasattr(settings, "agent_heartbeat_timeout_seconds")
        assert settings.agent_heartbeat_timeout_seconds > 0

    def test_config_agent_cleanup_interval_seconds(self):
        assert hasattr(settings, "agent_cleanup_interval_seconds")
        assert settings.agent_cleanup_interval_seconds > 0


# ---------------------------------------------------------------------------
# B2: Agent registration with chain_id/island_id
# ---------------------------------------------------------------------------


class TestAgentRegistrationChainAwareness:
    """Test agent registration and discovery with chain_id/island_id."""

    def test_agent_registration_with_chain_id(self):
        """Register agent with chain_id, verify model accepts it."""
        req = AgentRegistrationRequest(
            agent_id="agent-chain-001",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
            chain_id="ait-hub",
            island_id="island-1",
        )
        assert req.chain_id == "ait-hub"
        assert req.island_id == "island-1"

    def test_agent_registration_without_chain_id_backward_compat(self):
        """Register without chain_id, verify no crash and defaults to None."""
        req = AgentRegistrationRequest(
            agent_id="agent-no-chain-001",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
        )
        assert req.chain_id is None
        assert req.island_id is None

    def test_create_agent_info_with_chain_id(self):
        """create_agent_info passes chain_id/island_id to AgentInfo."""
        info = create_agent_info(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
            chain_id="ait-hub",
            island_id="island-1",
        )
        assert info.chain_id == "ait-hub"
        assert info.island_id == "island-1"

    def test_create_agent_info_without_chain_id_defaults_empty(self):
        """create_agent_info without chain_id defaults to empty strings."""
        info = create_agent_info(
            agent_id="agent-002",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
        )
        assert info.chain_id == ""
        assert info.island_id == ""

    def test_agent_info_to_dict_includes_chain_id(self):
        """AgentInfo.to_dict() includes chain_id and island_id."""
        info = create_agent_info(
            agent_id="agent-003",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
            chain_id="ait-hub",
            island_id="island-1",
        )
        d = info.to_dict()
        assert d["chain_id"] == "ait-hub"
        assert d["island_id"] == "island-1"

    def test_agent_info_from_dict_with_chain_id(self):
        """AgentInfo.from_dict() parses chain_id and island_id."""
        info = create_agent_info(
            agent_id="agent-004",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
            chain_id="ait-hub",
            island_id="island-1",
        )
        d = info.to_dict()
        restored = AgentInfo.from_dict(d)
        assert restored.chain_id == "ait-hub"
        assert restored.island_id == "island-1"

    def test_agent_info_from_dict_without_chain_id_backward_compat(self):
        """AgentInfo.from_dict() handles dicts without chain_id (backward compat)."""
        info = create_agent_info(
            agent_id="agent-005",
            agent_type="worker",
            capabilities=["data_processing"],
            services=["process_data"],
            endpoints={"http": "http://localhost:8001"},
        )
        d = info.to_dict()
        # Simulate old-format dict without chain_id/island_id keys
        d.pop("chain_id")
        d.pop("island_id")
        restored = AgentInfo.from_dict(d)
        assert restored.chain_id == ""
        assert restored.island_id == ""


# ---------------------------------------------------------------------------
# B2: Agent discovery filters
# ---------------------------------------------------------------------------


class TestAgentDiscoveryFilters:
    """Test agent discovery filtering by chain_id/island_id."""

    def _make_registry_with_agents(self) -> AgentRegistry:
        """Create an in-memory registry with test agents on different chains."""
        registry = AgentRegistry(redis_url="redis://localhost:6379/15")
        agents = [
            create_agent_info(
                agent_id="agent-hub-1",
                agent_type="worker",
                capabilities=["data_processing"],
                services=["process_data"],
                endpoints={"http": "http://localhost:8001"},
                chain_id="ait-hub",
                island_id="island-1",
            ),
            create_agent_info(
                agent_id="agent-hub-2",
                agent_type="worker",
                capabilities=["data_processing"],
                services=["process_data"],
                endpoints={"http": "http://localhost:8002"},
                chain_id="ait-hub",
                island_id="island-2",
            ),
            create_agent_info(
                agent_id="agent-edge-1",
                agent_type="worker",
                capabilities=["data_processing"],
                services=["process_data"],
                endpoints={"http": "http://localhost:8003"},
                chain_id="ait-edge",
                island_id="island-1",
            ),
        ]
        for a in agents:
            registry.agents[a.agent_id] = a
        return registry

    @pytest.mark.asyncio
    async def test_agent_discovery_filter_by_chain(self):
        """Discover agents filtered by chain_id."""
        registry = self._make_registry_with_agents()
        results = await registry.discover_agents({"chain_id": "ait-hub"})
        assert len(results) == 2
        assert all(a.chain_id == "ait-hub" for a in results)

    @pytest.mark.asyncio
    async def test_agent_discovery_filter_by_island(self):
        """Discover agents filtered by island_id."""
        registry = self._make_registry_with_agents()
        results = await registry.discover_agents({"island_id": "island-1"})
        assert len(results) == 2
        assert all(a.island_id == "island-1" for a in results)

    @pytest.mark.asyncio
    async def test_agent_discovery_filter_by_chain_and_island(self):
        """Discover agents filtered by both chain_id and island_id."""
        registry = self._make_registry_with_agents()
        results = await registry.discover_agents({"chain_id": "ait-hub", "island_id": "island-1"})
        assert len(results) == 1
        assert results[0].agent_id == "agent-hub-1"

    @pytest.mark.asyncio
    async def test_agent_discovery_no_chain_filter_returns_all(self):
        """Discover without chain_id filter returns all agents."""
        registry = self._make_registry_with_agents()
        results = await registry.discover_agents({})
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_agent_discovery_filter_by_nonexistent_chain(self):
        """Discover with non-existent chain_id returns empty list."""
        registry = self._make_registry_with_agents()
        results = await registry.discover_agents({"chain_id": "nonexistent"})
        assert len(results) == 0


# ---------------------------------------------------------------------------
# B4: Swarm + workflow chain_id models
# ---------------------------------------------------------------------------


class TestSwarmChainAwareness:
    """Test swarm models accept chain_id."""

    def test_swarm_join_with_chain_id(self):
        """JoinRequest accepts chain_id."""
        req = JoinRequest(role="worker", capability="data_processing", priority="normal", chain_id="ait-hub")
        assert req.chain_id == "ait-hub"

    def test_swarm_join_without_chain_id_backward_compat(self):
        """JoinRequest without chain_id defaults to None."""
        req = JoinRequest(role="worker", capability="data_processing", priority="normal")
        assert req.chain_id is None

    def test_swarm_coordinate_with_chain_id(self):
        """CoordinateRequest accepts chain_id."""
        req = CoordinateRequest(task="analyze", collaborators=3, strategy="parallel", timeout_seconds=300, chain_id="ait-hub")
        assert req.chain_id == "ait-hub"

    def test_swarm_coordinate_without_chain_id_backward_compat(self):
        """CoordinateRequest without chain_id defaults to None."""
        req = CoordinateRequest(task="analyze", collaborators=3, strategy="parallel", timeout_seconds=300)
        assert req.chain_id is None


class TestWorkflowChainAwareness:
    """Test workflow models accept chain_id."""

    def test_workflow_create_with_chain_id(self):
        """CreateWorkflowRequest accepts chain_id."""
        req = CreateWorkflowRequest(
            name="test-workflow",
            steps=[{"name": "step1"}],
            chain_id="ait-hub",
        )
        assert req.chain_id == "ait-hub"

    def test_workflow_create_without_chain_id_backward_compat(self):
        """CreateWorkflowRequest without chain_id defaults to None."""
        req = CreateWorkflowRequest(name="test-workflow", steps=[{"name": "step1"}])
        assert req.chain_id is None

    def test_workflow_execute_with_chain_id(self):
        """ExecuteWorkflowRequest accepts chain_id."""
        req = ExecuteWorkflowRequest(input_parameters={"key": "value"}, chain_id="ait-hub")
        assert req.chain_id == "ait-hub"

    def test_workflow_execute_without_chain_id_backward_compat(self):
        """ExecuteWorkflowRequest without chain_id defaults to None."""
        req = ExecuteWorkflowRequest(input_parameters={"key": "value"})
        assert req.chain_id is None


# ---------------------------------------------------------------------------
# B5: Configurable agent TTL
# ---------------------------------------------------------------------------


class TestAgentTTLConfigurable:
    """Test agent TTL is configurable (not hardcoded)."""

    def test_registry_uses_config_defaults(self):
        """AgentRegistry picks up TTL from settings by default."""
        registry = AgentRegistry(redis_url="redis://localhost:6379/15")
        assert registry.cleanup_interval == settings.agent_cleanup_interval_seconds
        assert registry.max_heartbeat_age == settings.agent_heartbeat_timeout_seconds

    def test_registry_accepts_custom_cleanup_interval(self):
        """AgentRegistry accepts custom cleanup_interval."""
        registry = AgentRegistry(redis_url="redis://localhost:6379/15", cleanup_interval=30)
        assert registry.cleanup_interval == 30

    def test_registry_accepts_custom_max_heartbeat_age(self):
        """AgentRegistry accepts custom max_heartbeat_age."""
        registry = AgentRegistry(redis_url="redis://localhost:6379/15", max_heartbeat_age=200)
        assert registry.max_heartbeat_age == 200

    def test_registry_accepts_both_custom_ttls(self):
        """AgentRegistry accepts both custom TTL values."""
        registry = AgentRegistry(redis_url="redis://localhost:6379/15", cleanup_interval=15, max_heartbeat_age=45)
        assert registry.cleanup_interval == 15
        assert registry.max_heartbeat_age == 45


# ---------------------------------------------------------------------------
# B2: Task submission model (chain_id field only — escrow is B3, skipped)
# ---------------------------------------------------------------------------


class TestTaskSubmissionModel:
    """Test TaskSubmission model with chain_id and payment fields (B3)."""

    def test_task_submission_backward_compat(self):
        """TaskSubmission without chain_id works (backward compat)."""
        req = TaskSubmission(task_data={"action": "process"}, priority="normal")
        assert req.task_data == {"action": "process"}
        assert req.priority == "normal"
        assert req.chain_id is None
        assert req.payment is None

    def test_task_submission_with_chain_id(self):
        """TaskSubmission accepts chain_id."""
        req = TaskSubmission(task_data={"action": "process"}, priority="normal", chain_id="ait-hub")
        assert req.chain_id == "ait-hub"

    def test_task_submission_with_payment(self):
        """TaskSubmission accepts payment details."""
        payment = TaskPayment(amount=1000, requester="addr1", agent="addr2")
        req = TaskSubmission(task_data={"action": "process"}, priority="normal", payment=payment)
        assert req.payment is not None
        assert req.payment.amount == 1000
        assert req.payment.requester == "addr1"
        assert req.payment.agent == "addr2"

    def test_task_submission_without_payment_backward_compat(self):
        """TaskSubmission without payment works (no escrow)."""
        req = TaskSubmission(task_data={"action": "process"}, priority="normal")
        assert req.payment is None


# ---------------------------------------------------------------------------
# B3: Payment escrow lifecycle (requires A1 PaymentEscrow)
# ---------------------------------------------------------------------------


class TestPaymentEscrowLifecycle:
    """Test payment escrow lock/release/refund lifecycle (B3 + A1)."""

    def _make_escrow(self) -> PaymentEscrow:
        """Create a PaymentEscrow with mock callbacks."""
        lock_calls: list[tuple] = []
        release_calls: list[tuple] = []
        refund_calls: list[tuple] = []

        def lock_cb(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
            lock_calls.append((chain_id, from_addr, to_addr, amount))
            return f"lock_tx_{len(lock_calls)}"

        def release_cb(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
            release_calls.append((chain_id, from_addr, to_addr, amount))
            return f"release_tx_{len(release_calls)}"

        def refund_cb(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
            refund_calls.append((chain_id, from_addr, to_addr, amount))
            return f"refund_tx_{len(refund_calls)}"

        escrow = PaymentEscrow(
            lock_callback=lock_cb,
            release_callback=release_cb,
            refund_callback=refund_cb,
            default_timeout=3600.0,
        )
        return escrow

    def test_payment_escrow_lock_release(self):
        """Escrow lock → task complete → release."""
        escrow = self._make_escrow()
        entry = escrow.create_escrow(
            task_id="task-001",
            chain_id="ait-hub",
            requester="addr1",
            agent="addr2",
            amount=1000,
        )
        assert entry.status == EscrowStatus.PENDING

        escrow.lock(entry.escrow_id)
        assert entry.status == EscrowStatus.LOCKED
        assert entry.tx_hash_lock is not None

        escrow.release(entry.escrow_id)
        assert entry.status == EscrowStatus.RELEASED
        assert entry.tx_hash_release is not None

    def test_payment_escrow_lock_refund(self):
        """Escrow lock → task fails → refund."""
        escrow = self._make_escrow()
        entry = escrow.create_escrow(
            task_id="task-002",
            chain_id="ait-hub",
            requester="addr1",
            agent="addr2",
            amount=500,
        )
        escrow.lock(entry.escrow_id)
        assert entry.status == EscrowStatus.LOCKED

        escrow.refund(entry.escrow_id)
        assert entry.status == EscrowStatus.REFUNDED
        assert entry.tx_hash_refund is not None

    def test_payment_escrow_timeout_auto_refund(self):
        """Escrow expires → auto-refund via expire_stale()."""
        escrow = self._make_escrow()
        entry = escrow.create_escrow(
            task_id="task-003",
            chain_id="ait-hub",
            requester="addr1",
            agent="addr2",
            amount=300,
            timeout=0.01,  # 10ms — expires almost immediately
        )
        escrow.lock(entry.escrow_id)
        assert entry.status == EscrowStatus.LOCKED

        import time

        time.sleep(0.02)  # Wait for timeout
        expired = escrow.expire_stale()
        assert len(expired) == 1
        assert expired[0].escrow_id == entry.escrow_id
        assert entry.status == EscrowStatus.REFUNDED

    def test_payment_escrow_no_locked_no_expire(self):
        """expire_stale() returns empty list when no locked escrows."""
        escrow = self._make_escrow()
        expired = escrow.expire_stale()
        assert expired == []

    def test_payment_escrow_get_escrow_for_task(self):
        """get_escrow_for_task() finds escrow by task_id."""
        escrow = self._make_escrow()
        entry = escrow.create_escrow(
            task_id="task-004",
            chain_id="ait-hub",
            requester="addr1",
            agent="addr2",
            amount=200,
        )
        found = escrow.get_escrow_for_task("task-004")
        assert found is not None
        assert found.escrow_id == entry.escrow_id

    def test_payment_escrow_get_escrow_not_found(self):
        """get_escrow_for_task() returns None for unknown task."""
        escrow = self._make_escrow()
        assert escrow.get_escrow_for_task("nonexistent") is None


# ---------------------------------------------------------------------------
# B3: Chain-aware task distribution (load_balancer chain_id routing)
# ---------------------------------------------------------------------------


class TestChainAwareTaskDistribution:
    """Test that chain_id threads through TaskDistributor → LoadBalancer → agent discovery."""

    def test_submit_task_accepts_chain_id(self):
        """TaskDistributor.submit_task accepts chain_id and stores it in task_info."""
        import asyncio

        from src.app.routing.load_balancer import LoadBalancer, TaskDistributor, TaskPriority

        lb = LoadBalancer.__new__(LoadBalancer)
        td = TaskDistributor.__new__(TaskDistributor)
        td.load_balancer = lb
        td.task_queue = asyncio.Queue()
        td.priority_queues = {p: asyncio.Queue() for p in TaskPriority}
        td.distribution_stats = {"tasks_distributed": 0, "tasks_completed": 0, "tasks_failed": 0, "avg_distribution_time": 0.0}

        asyncio.run(td.submit_task({"action": "process"}, TaskPriority.NORMAL, chain_id="ait-hub"))
        task_info = asyncio.run(td.priority_queues[TaskPriority.NORMAL].get())
        assert task_info["chain_id"] == "ait-hub"

    def test_submit_task_without_chain_id_defaults_none(self):
        """TaskDistributor.submit_task without chain_id stores None."""
        import asyncio

        from src.app.routing.load_balancer import LoadBalancer, TaskDistributor, TaskPriority

        td = TaskDistributor.__new__(TaskDistributor)
        td.load_balancer = LoadBalancer.__new__(LoadBalancer)
        td.task_queue = asyncio.Queue()
        td.priority_queues = {p: asyncio.Queue() for p in TaskPriority}
        td.distribution_stats = {"tasks_distributed": 0, "tasks_completed": 0, "tasks_failed": 0, "avg_distribution_time": 0.0}

        asyncio.run(td.submit_task({"action": "process"}, TaskPriority.NORMAL))
        task_info = asyncio.run(td.priority_queues[TaskPriority.NORMAL].get())
        assert task_info["chain_id"] is None

    def test_assign_task_accepts_chain_id(self):
        """LoadBalancer.assign_task accepts chain_id parameter without error."""
        from unittest.mock import AsyncMock, patch

        from src.app.routing.load_balancer import LoadBalancer

        lb = LoadBalancer.__new__(LoadBalancer)
        lb.registry = AsyncMock()
        lb.agent_weights = {}
        lb.agent_metrics = {}
        lb.task_assignments = {}
        lb.assignment_history = []
        lb.total_assignments = 0
        lb.failed_assignments = 0
        lb.strategy = None

        with patch.object(lb, "_find_eligible_agents", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = []
            import asyncio

            result = asyncio.run(lb.assign_task({"action": "process"}, chain_id="ait-hub"))
            assert result is None
            # Verify chain_id was passed to _find_eligible_agents
            mock_find.assert_called_once_with({"action": "process"}, None, chain_id="ait-hub")

    def test_find_eligible_agents_filters_by_chain_id(self):
        """_find_eligible_agents adds chain_id to discovery query when provided."""
        from unittest.mock import AsyncMock

        from src.app.routing.load_balancer import LoadBalancer

        lb = LoadBalancer.__new__(LoadBalancer)
        lb.registry = AsyncMock()
        lb.agent_weights = {}
        lb.agent_metrics = {}

        # Registry returns empty list — we just verify the query includes chain_id
        lb.registry.discover_agents = AsyncMock(return_value=[])
        import asyncio

        asyncio.run(lb._find_eligible_agents({"action": "process"}, chain_id="ait-hub"))
        call_args = lb.registry.discover_agents.call_args
        query = call_args[0][0] if call_args[0] else call_args[1].get("query", {})
        assert query.get("chain_id") == "ait-hub"

    def test_find_eligible_agents_without_chain_id_no_filter(self):
        """_find_eligible_agents does not add chain_id to query when not provided."""
        from unittest.mock import AsyncMock

        from src.app.routing.load_balancer import LoadBalancer

        lb = LoadBalancer.__new__(LoadBalancer)
        lb.registry = AsyncMock()
        lb.agent_weights = {}
        lb.agent_metrics = {}
        lb.registry.discover_agents = AsyncMock(return_value=[])
        import asyncio

        asyncio.run(lb._find_eligible_agents({"action": "process"}))
        call_args = lb.registry.discover_agents.call_args
        query = call_args[0][0] if call_args[0] else call_args[1].get("query", {})
        assert "chain_id" not in query


# ---------------------------------------------------------------------------
# v0.6.5 hardening: WebSocket auth + port fix
# ---------------------------------------------------------------------------


class TestWebSocketAuth:
    """Test WebSocket authentication (v0.6.5 hardening)."""

    def test_authenticate_websocket_with_valid_api_key(self):
        """_authenticate_websocket accepts valid COORDINATOR_API_KEY."""
        from src.app.routers.websocket import _authenticate_websocket

        os.environ["COORDINATOR_API_KEY"] = "test-coordinator-key"
        try:
            assert _authenticate_websocket(websocket=None, token="test-coordinator-key") is True
        finally:
            del os.environ["COORDINATOR_API_KEY"]

    def test_authenticate_websocket_with_valid_secret_key(self):
        """_authenticate_websocket accepts valid SECRET_KEY."""
        from src.app.routers.websocket import _authenticate_websocket

        # SECRET_KEY is already set to "test-secret-key" at module load
        assert _authenticate_websocket(websocket=None, token="test-secret-key") is True

    def test_authenticate_websocket_rejects_no_token(self):
        """_authenticate_websocket rejects None token."""
        from src.app.routers.websocket import _authenticate_websocket

        assert _authenticate_websocket(websocket=None, token=None) is False

    def test_authenticate_websocket_rejects_empty_token(self):
        """_authenticate_websocket rejects empty string token."""
        from src.app.routers.websocket import _authenticate_websocket

        assert _authenticate_websocket(websocket=None, token="") is False

    def test_authenticate_websocket_rejects_wrong_token(self):
        """_authenticate_websocket rejects invalid token."""
        from src.app.routers.websocket import _authenticate_websocket

        assert _authenticate_websocket(websocket=None, token="wrong-key") is False


class TestPortFix:
    """Test that agent_stream.py uses correct port 8202 (not stale 8006)."""

    def test_agent_stream_default_rpc_url_is_8202(self):
        """_submit_transaction defaults to port 8202, not stale 8006."""
        import inspect

        from src.app.websocket import agent_stream

        source = inspect.getsource(agent_stream._submit_transaction)
        assert "8202" in source
        assert "8006" not in source
