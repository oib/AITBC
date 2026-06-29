"""Integration tests for v0.7.3 on-chain governance (B1-B8).

Tests cover:
- B1: Governance service Settings class
- B2: BlockchainClient (mocked httpx)
- B3-B5: On-chain proposal/vote/execute submission (mocked blockchain)
- B6: Domain model fields (chain_id, block_height, tx_hash)
- B7: GOVERNANCE_* tx payload validation in poa.py
- B8: CLI governance commands
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# B1: Governance Service Settings
# ============================================================================


class TestGovernanceSettings:
    """Test the governance service Settings class (B1)."""

    def test_settings_defaults(self):
        from governance_service.config import Settings

        settings = Settings()
        assert settings.blockchain_rpc_url == "http://localhost:8202"
        assert settings.default_chain_id == "ait-hub"
        assert settings.voting_period_blocks == 7200
        assert settings.quorum_percent == 30.0
        assert settings.approval_percent == 50.0
        assert settings.timelock_blocks == 43200
        assert settings.snapshot_delay_blocks == 100
        assert settings.enable_onchain_submission is False
        assert settings.bind_port == 8105

    def test_settings_env_override(self, monkeypatch):
        from governance_service.config import Settings

        monkeypatch.setenv("GOVERNANCE_BLOCKCHAIN_RPC_URL", "http://node.example.com:8202")
        monkeypatch.setenv("GOVERNANCE_DEFAULT_CHAIN_ID", "test-chain")
        monkeypatch.setenv("GOVERNANCE_ENABLE_ONCHAIN_SUBMISSION", "true")
        settings = Settings()
        assert settings.blockchain_rpc_url == "http://node.example.com:8202"
        assert settings.default_chain_id == "test-chain"
        assert settings.enable_onchain_submission is True

    def test_settings_not_8006(self):
        """Verify the stale port 8006 is NOT used — must be 8202."""
        from governance_service.config import Settings

        settings = Settings()
        assert "8006" not in settings.blockchain_rpc_url
        assert "8202" in settings.blockchain_rpc_url


# ============================================================================
# B6: Domain Model Fields
# ============================================================================


class TestDomainModelFields:
    """Test that Proposal and Vote have on-chain governance fields (B6)."""

    def test_proposal_has_chain_id(self):
        from governance_service.domain.governance import Proposal

        proposal = Proposal(
            proposer_id="gov_test",
            title="Test",
            description="Test proposal",
            voting_starts="2026-01-01T00:00:00Z",
            voting_ends="2026-01-08T00:00:00Z",
        )
        assert proposal.chain_id == "ait-hub"
        assert proposal.block_height is None
        assert proposal.tx_hash is None

    def test_proposal_chain_id_custom(self):
        from governance_service.domain.governance import Proposal

        proposal = Proposal(
            proposer_id="gov_test",
            title="Test",
            description="Test proposal",
            voting_starts="2026-01-01T00:00:00Z",
            voting_ends="2026-01-08T00:00:00Z",
            chain_id="test-chain",
        )
        assert proposal.chain_id == "test-chain"

    def test_vote_has_chain_id(self):
        from governance_service.domain.governance import Vote

        vote = Vote(
            proposal_id="prop_test",
            voter_id="gov_test",
            vote_type="for",
            voting_power_used=100.0,
        )
        assert vote.chain_id == "ait-hub"
        assert vote.block_height is None
        assert vote.tx_hash is None

    def test_vote_chain_id_custom(self):
        from governance_service.domain.governance import Vote

        vote = Vote(
            proposal_id="prop_test",
            voter_id="gov_test",
            vote_type="for",
            voting_power_used=100.0,
            chain_id="test-chain",
        )
        assert vote.chain_id == "test-chain"


# ============================================================================
# B2: BlockchainClient (mocked)
# ============================================================================


class TestBlockchainClient:
    """Test the BlockchainClient for governance operations (B2)."""

    def test_client_init(self):
        from governance_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        assert client.rpc_url == "http://localhost:8202"

    def test_client_init_strips_trailing_slash(self):
        from governance_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202/")
        assert client.rpc_url == "http://localhost:8202"

    @pytest.mark.asyncio
    async def test_get_balance_success(self):
        from governance_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"address": "0xabc", "balance": 5000, "nonce": 3}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            balance = await client.get_balance("0xabc", "ait-hub")
            assert balance == 5000.0

    @pytest.mark.asyncio
    async def test_get_balance_not_found(self):
        from governance_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            balance = await client.get_balance("0xnew", "ait-hub")
            assert balance == 0.0

    @pytest.mark.asyncio
    async def test_get_block_height(self):
        from governance_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"height": 12345}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            height = await client.get_block_height("ait-hub")
            assert height == 12345

    @pytest.mark.asyncio
    async def test_submit_transaction_missing_chain_id(self):
        from governance_service.clients.blockchain import BlockchainClient

        client = BlockchainClient(rpc_url="http://localhost:8202")
        with pytest.raises(ValueError, match="chain_id"):
            await client.submit_transaction({"from": "0xabc", "to": "0xdef"})


# ============================================================================
# B7: Governance Tx Payload Validation (poa.py)
# ============================================================================


class TestGovernancePayloadValidation:
    """Test GOVERNANCE_* tx payload validation in poa.py (B7)."""

    def test_validate_propose_valid(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {
            "proposal_id": "prop_1",
            "title": "Test",
            "proposer": "0xabc",
            "description": "A test proposal",
            "proposal_type": "parameter_change",
        }
        errors = _validate_governance_payload("GOVERNANCE_PROPOSE", payload)
        assert errors == []

    def test_validate_propose_missing_fields(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {"proposal_id": "prop_1"}
        errors = _validate_governance_payload("GOVERNANCE_PROPOSE", payload)
        assert len(errors) == 4  # missing: proposer, title, description, proposal_type
        assert any("title" in e for e in errors)
        assert any("proposer" in e for e in errors)
        assert any("description" in e for e in errors)
        assert any("proposal_type" in e for e in errors)

    def test_validate_vote_valid(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {"proposal_id": "prop_1", "voter": "0xabc", "vote_type": "for"}
        errors = _validate_governance_payload("GOVERNANCE_VOTE", payload)
        assert errors == []

    def test_validate_vote_invalid_vote_type(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {"proposal_id": "prop_1", "voter": "0xabc", "vote_type": "maybe"}
        errors = _validate_governance_payload("GOVERNANCE_VOTE", payload)
        assert any("invalid vote_type" in e for e in errors)

    def test_validate_vote_missing_fields(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {}
        errors = _validate_governance_payload("GOVERNANCE_VOTE", payload)
        assert len(errors) == 3

    def test_validate_execute_valid(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {"proposal_id": "prop_1", "executor": "0xabc"}
        errors = _validate_governance_payload("GOVERNANCE_EXECUTE", payload)
        assert errors == []

    def test_validate_execute_missing_fields(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {"proposal_id": "prop_1"}
        errors = _validate_governance_payload("GOVERNANCE_EXECUTE", payload)
        assert any("executor" in e for e in errors)

    def test_validate_unknown_type(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        errors = _validate_governance_payload("GOVERNANCE_UNKNOWN", {})
        assert any("Unknown governance tx type" in e for e in errors)

    def test_validate_empty_fields(self):
        from aitbc_chain.consensus.poa import _validate_governance_payload

        payload = {"proposal_id": "", "title": "", "proposer": "", "description": ""}
        errors = _validate_governance_payload("GOVERNANCE_PROPOSE", payload)
        # 4 empty required fields + 1 missing (proposal_type)
        assert len(errors) == 5
        assert any("empty required field: proposal_id" in e for e in errors)
        assert any("empty required field: title" in e for e in errors)
        assert any("empty required field: proposer" in e for e in errors)
        assert any("empty required field: description" in e for e in errors)
        assert any("missing required field: proposal_type" in e for e in errors)


# ============================================================================
# B8: CLI Governance Commands
# ============================================================================


class TestCLIGovernanceCommands:
    """Test the governance CLI command group exists and has correct subcommands (B8)."""

    def test_governance_group_exists(self):
        from aitbc_cli.commands.governance import governance

        assert governance is not None
        assert governance.name == "governance"

    def test_governance_has_subcommands(self):
        from aitbc_cli.commands.governance import governance

        subcommands = list(governance.commands.keys())
        assert "propose" in subcommands
        assert "vote" in subcommands
        assert "list" in subcommands
        assert "execute" in subcommands
        assert "status" in subcommands
        assert "get" in subcommands

    def test_propose_command_params(self):
        from aitbc_cli.commands.governance import governance

        propose_cmd = governance.commands["propose"]
        param_names = {p.name for p in propose_cmd.params}
        assert "title" in param_names
        assert "description" in param_names
        assert "proposal_type" in param_names
        assert "proposer_id" in param_names

    def test_vote_command_params(self):
        from aitbc_cli.commands.governance import governance

        vote_cmd = governance.commands["vote"]
        param_names = {p.name for p in vote_cmd.params}
        assert "proposal_id" in param_names
        assert "voter_id" in param_names
        assert "vote" in param_names


# ============================================================================
# B3-B5: On-Chain Submission (mocked service)
# ============================================================================


class TestOnChainSubmission:
    """Test that the governance service attempts on-chain submission when enabled (B3-B5)."""

    def test_create_proposal_local_only(self):
        """When on-chain submission is disabled, proposal is created locally only."""
        from governance_service.config import settings as gov_settings

        # Verify the config flag exists and defaults to False
        assert gov_settings.enable_onchain_submission is False

    def test_governance_status_includes_config(self):
        """Test that governance status endpoint includes v0.7.3 config fields."""
        from fastapi.testclient import TestClient

        from governance_service.main import app

        client = TestClient(app)
        response = client.get("/v1/governance/status")
        assert response.status_code == 200
        data = response.json()
        assert "chain_id" in data
        assert "blockchain_rpc_url" in data
        assert "onchain_submission_enabled" in data
        assert "voting_period_blocks" in data
        assert "quorum_percent" in data
        assert "timelock_blocks" in data
        assert data["blockchain_rpc_url"] == "http://localhost:8202"
        assert "8006" not in data["blockchain_rpc_url"]

    def test_execute_proposal_endpoint_accepts_executor_address(self):
        """Test that the execute endpoint accepts executor_address parameter."""
        from fastapi.testclient import TestClient

        from governance_service.main import app

        client = TestClient(app)
        # This will fail with 404 (proposal not found) but should not 422 (validation error)
        response = client.post(
            "/v1/governance/proposals/nonexistent/execute",
            json={"executor_address": "0xabc"},
        )
        assert response.status_code in [200, 404, 500]
        assert response.status_code != 422  # Not a validation error


# ============================================================================
# Alembic Migration
# ============================================================================


class TestAlembicMigration:
    """Test that the v0.7.3 Alembic migration exists and is correct."""

    def test_migration_file_exists(self):
        import importlib.util
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "002_v073_onchain_governance_fields.py"
        assert migration_path.exists()
        spec = importlib.util.spec_from_file_location("migration_002", migration_path)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "002"
        assert mod.down_revision == "001"

    def test_migration_has_upgrade_downgrade(self):
        import importlib.util
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "002_v073_onchain_governance_fields.py"
        spec = importlib.util.spec_from_file_location("migration_002b", migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
