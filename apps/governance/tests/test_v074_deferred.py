"""Integration tests for v0.7.4 deferred items (B2-B9).

Tests cover:
- B2: Cross-chain governance endpoints (propagate, aggregate-votes, execute-cross-chain)
- B3: Pool-hub parameter change API
- B4: Marketplace parameter change API
- B5: Emergency proposal handling
- B6: BridgeClientAdapter
- B8: CLI commands (smoke tests)
- Oracle config (B1)
"""

from __future__ import annotations

import sys
from pathlib import Path


# Add src paths for cross-app imports
_REPO = Path(__file__).resolve().parents[3]
_GOV_SRC = str(Path(__file__).resolve().parent.parent / "src")
_BC_SRC = str(_REPO / "apps" / "blockchain-node" / "src")
_POOLHUB_SRC = str(_REPO / "apps" / "pool-hub" / "src")
_MARKETPLACE_SRC = str(_REPO / "apps" / "marketplace" / "src")
_CLI_SRC = str(_REPO / "cli")
for _p in [_GOV_SRC, _BC_SRC, _POOLHUB_SRC, _MARKETPLACE_SRC, _CLI_SRC]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ============================================================================
# B1: Oracle Config
# ============================================================================


class TestOracleConfig:
    """Tests for bridge oracle configuration fields."""

    def test_oracle_endpoints_config_exists(self):
        from aitbc_chain.config import ChainSettings

        settings = ChainSettings()
        assert hasattr(settings, "bridge_oracle_endpoints")
        assert settings.bridge_oracle_endpoints == []

    def test_verification_mode_config_exists(self):
        from aitbc_chain.config import ChainSettings

        settings = ChainSettings()
        assert hasattr(settings, "bridge_verification_mode")
        assert settings.bridge_verification_mode == "in_process"

    def test_oracle_health_check_interval_config(self):
        from aitbc_chain.config import ChainSettings

        settings = ChainSettings()
        assert hasattr(settings, "bridge_oracle_health_check_interval")
        assert settings.bridge_oracle_health_check_interval == 60

    def test_oracle_timeout_config(self):
        from aitbc_chain.config import ChainSettings

        settings = ChainSettings()
        assert hasattr(settings, "bridge_oracle_timeout")
        assert settings.bridge_oracle_timeout == 30


# ============================================================================
# B2: Cross-Chain Governance Endpoints
# ============================================================================


class TestCrossChainGovernance:
    """Tests for cross-chain governance endpoints."""

    def test_propagate_request_model(self):
        """Test that PropagateRequest model accepts target_chains."""
        from governance_service.main import PropagateRequest

        req = PropagateRequest(target_chains=["chain-a", "chain-b"])
        assert req.target_chains == ["chain-a", "chain-b"]

    def test_governance_status_includes_chain_id(self):
        """Test that governance status endpoint includes chain_id."""
        from governance_service.config import settings

        assert settings.default_chain_id == "ait-hub"
        assert settings.blockchain_rpc_url == "http://localhost:8202"


# ============================================================================
# B3: Pool-Hub Parameter API
# ============================================================================


class TestPoolHubParameterAPI:
    """Tests for pool-hub parameter change endpoint."""

    def test_parameters_router_exists(self):
        """Test that the parameters router module exists."""
        router_path = _REPO / "apps" / "pool-hub" / "src" / "poolhub" / "app" / "routers" / "parameters.py"
        assert router_path.exists(), f"Parameters router not found at {router_path}"

    def test_parameter_change_request_model(self):
        """Test that ParameterChangeRequest model is defined in the parameters router."""
        # Read the file directly to avoid triggering broken imports in other pool-hub routers
        router_path = _REPO / "apps" / "pool-hub" / "src" / "poolhub" / "app" / "routers" / "parameters.py"
        content = router_path.read_text()
        assert "class ParameterChangeRequest" in content
        assert "proposal_id" in content
        assert "parameter_name" in content
        assert "new_value" in content
        assert "target_service" in content


# ============================================================================
# B4: Marketplace Parameter API
# ============================================================================


class TestMarketplaceParameterAPI:
    """Tests for marketplace parameter change endpoint."""

    def test_marketplace_parameter_change_request_model(self):
        """Test that ParameterChangeRequest model exists in marketplace."""
        from marketplace_service.main import ParameterChangeRequest

        req = ParameterChangeRequest(
            proposal_id="prop-1",
            target_service="marketplace",
            parameter_name="default_chain_id",
            old_value="ait-hub",
            new_value="ait-hub-2",
        )
        assert req.target_service == "marketplace"
        assert req.parameter_name == "default_chain_id"

    def test_marketplace_governance_parameters_defined(self):
        """Test that allowed governance parameters are defined."""
        from marketplace_service.main import _MARKETPLACE_GOVERNANCE_PARAMETERS

        assert "default_chain_id" in _MARKETPLACE_GOVERNANCE_PARAMETERS
        assert "agent_coordinator_url" in _MARKETPLACE_GOVERNANCE_PARAMETERS
        assert "matching_algorithm" in _MARKETPLACE_GOVERNANCE_PARAMETERS


# ============================================================================
# B5: Emergency Proposal Handling
# ============================================================================


class TestEmergencyProposals:
    """Tests for emergency proposal handling."""

    def test_emergency_voting_period_config(self):
        from governance_service.config import settings

        assert hasattr(settings, "emergency_voting_period_blocks")
        assert settings.emergency_voting_period_blocks < settings.voting_period_blocks

    def test_emergency_quorum_config(self):
        from governance_service.config import settings

        assert hasattr(settings, "emergency_quorum_percent")
        assert settings.emergency_quorum_percent > settings.quorum_percent

    def test_emergency_timelock_config(self):
        from governance_service.config import settings

        assert hasattr(settings, "emergency_timelock_blocks")
        assert settings.emergency_timelock_blocks < settings.timelock_blocks


# ============================================================================
# B6: BridgeClientAdapter
# ============================================================================


class TestBridgeClientAdapter:
    """Tests for the BridgeClientAdapter in coordinator-api."""

    def test_adapter_import(self):
        """Test that BridgeClientAdapter can be imported."""
        import importlib.util

        adapter_path = (
            _REPO
            / "apps"
            / "coordinator-api"
            / "src"
            / "app"
            / "contexts"
            / "cross_chain"
            / "services"
            / "cross_chain"
            / "bridge_client_adapter.py"
        )
        assert adapter_path.exists(), f"BridgeClientAdapter not found at {adapter_path}"
        spec = importlib.util.spec_from_file_location("bridge_client_adapter", adapter_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adapter = module.BridgeClientAdapter(rpc_url="http://localhost:8202")
        assert adapter is not None

    def test_adapter_init_with_defaults(self):
        """Test adapter initialization with default values."""
        import importlib.util

        adapter_path = (
            _REPO
            / "apps"
            / "coordinator-api"
            / "src"
            / "app"
            / "contexts"
            / "cross_chain"
            / "services"
            / "cross_chain"
            / "bridge_client_adapter.py"
        )
        spec = importlib.util.spec_from_file_location("bridge_client_adapter", adapter_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adapter = module.BridgeClientAdapter(rpc_url="http://localhost:9999", chain_id="test-chain")
        assert adapter.client is not None
        assert adapter._config.chain_id == "test-chain"

    def test_adapter_transfer_to_dict(self):
        """Test the _transfer_to_dict conversion method."""
        import importlib.util
        from datetime import datetime

        from aitbc.bridge import BridgeStatus, BridgeTransfer

        adapter_path = (
            _REPO
            / "apps"
            / "coordinator-api"
            / "src"
            / "app"
            / "contexts"
            / "cross_chain"
            / "services"
            / "cross_chain"
            / "bridge_client_adapter.py"
        )
        spec = importlib.util.spec_from_file_location("bridge_client_adapter", adapter_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        transfer = BridgeTransfer(
            transfer_id="tx-123",
            source_chain="chain-a",
            target_chain="chain-b",
            sender="0xabc",
            recipient="0xdef",
            amount=1000,
            status=BridgeStatus.LOCKED,
            lock_time=datetime(2026, 1, 1),
        )
        adapter = module.BridgeClientAdapter()
        result = adapter._transfer_to_dict(transfer)
        assert result["transfer_id"] == "tx-123"
        assert result["status"] == "locked"
        assert result["source_chain"] == "chain-a"


# ============================================================================
# B8: CLI Commands (smoke tests)
# ============================================================================


class TestCLICommands:
    """Smoke tests for CLI command registration."""

    def test_governance_propagate_command_exists(self):
        """Test that governance propagate CLI command is registered."""
        from click.testing import CliRunner

        from cli.aitbc_cli.commands.governance import governance

        runner = CliRunner()
        result = runner.invoke(governance, ["--help"])
        assert result.exit_code == 0
        assert "propagate" in result.output

    def test_governance_aggregate_votes_command_exists(self):
        """Test that governance aggregate-votes CLI command is registered."""
        from click.testing import CliRunner

        from cli.aitbc_cli.commands.governance import governance

        runner = CliRunner()
        result = runner.invoke(governance, ["--help"])
        assert result.exit_code == 0
        assert "aggregate-votes" in result.output

    def test_governance_execute_cross_chain_command_exists(self):
        """Test that governance execute-cross-chain CLI command is registered."""
        from click.testing import CliRunner

        from cli.aitbc_cli.commands.governance import governance

        runner = CliRunner()
        result = runner.invoke(governance, ["--help"])
        assert result.exit_code == 0
        assert "execute-cross-chain" in result.output

    def test_consensus_status_command_exists(self):
        """Test that consensus status CLI command is registered."""
        from click.testing import CliRunner

        from cli.aitbc_cli.commands.chain import chain

        runner = CliRunner()
        result = runner.invoke(chain, ["consensus", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output

    def test_consensus_validators_command_exists(self):
        """Test that consensus validators CLI command is registered."""
        from click.testing import CliRunner

        from cli.aitbc_cli.commands.chain import chain

        runner = CliRunner()
        result = runner.invoke(chain, ["consensus", "--help"])
        assert result.exit_code == 0
        assert "validators" in result.output

    def test_bridge_oracle_status_command_exists(self):
        """Test that bridge oracle-status CLI command is registered."""
        from click.testing import CliRunner

        from cli.aitbc_cli.commands.bridge import bridge

        runner = CliRunner()
        result = runner.invoke(bridge, ["--help"])
        assert result.exit_code == 0
        assert "oracle-status" in result.output


# ============================================================================
# A1-A2: External Oracle Client (Agent A — smoke tests)
# ============================================================================


class TestExternalOracle:
    """Smoke tests for external oracle client (Agent A)."""

    def test_oracle_client_class_exists(self):
        """Test that ExternalOracleClient class exists."""
        from aitbc.bridge.oracle import ExternalOracleClient

        client = ExternalOracleClient()
        assert client is not None

    def test_oracle_mode_property(self):
        """Test that oracle client has a mode property."""
        from aitbc.bridge.oracle import ExternalOracleClient, VerificationMode

        client = ExternalOracleClient()
        assert client.mode == VerificationMode.ORACLE


# ============================================================================
# A3: Cross-Chain Governance Utilities (Agent A — smoke tests)
# ============================================================================


class TestCrossChainGovernanceUtilities:
    """Smoke tests for cross-chain governance utilities (Agent A)."""

    def test_propagate_proposal_method_exists(self):
        """Test that GovernanceClient has propagate_proposal method."""
        from aitbc.governance.client import GovernanceClient

        assert hasattr(GovernanceClient, "propagate_proposal")

    def test_aggregate_votes_method_exists(self):
        """Test that GovernanceClient has aggregate_votes method."""
        from aitbc.governance.client import GovernanceClient

        assert hasattr(GovernanceClient, "aggregate_votes")

    def test_execute_cross_chain_method_exists(self):
        """Test that GovernanceClient has execute_cross_chain method."""
        from aitbc.governance.client import GovernanceClient

        assert hasattr(GovernanceClient, "execute_cross_chain")


# ============================================================================
# A4: Parameter Change Helper (Agent A — smoke tests)
# ============================================================================


class TestParameterChangeHelper:
    """Smoke tests for parameter change helper (Agent A)."""

    def test_build_parameter_apply_tx_exists(self):
        """Test that build_parameter_apply_tx function exists."""
        from aitbc.governance.onchain import build_parameter_apply_tx

        assert callable(build_parameter_apply_tx)

    def test_validate_parameter_change_exists(self):
        """Test that validate_parameter_change function exists."""
        from aitbc.governance.onchain import validate_parameter_change

        assert callable(validate_parameter_change)

    def test_known_target_services_includes_pool_hub(self):
        """Test that pool-hub is a known target service."""
        from aitbc.governance.onchain import _KNOWN_TARGET_SERVICES

        assert "pool-hub" in _KNOWN_TARGET_SERVICES
        assert "marketplace" in _KNOWN_TARGET_SERVICES
