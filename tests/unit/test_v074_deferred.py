"""Unit tests for v0.7.4 deferred items (Agent A §A5).

Covers:
- ExternalOracleClient (A1): verify_proof, check_finality, is_healthy with
  mocked httpx — endpoint failover, unhealthy cooldown, no-endpoints edge case
- OracleFallbackPolicy (A2): oracle→in-process fallback, health check,
  genuine-vs-infrastructure error distinction, finality fallback
- Cross-chain governance utilities (A3): build_proposal_propagation_tx,
  build_vote_aggregation_tx, build_cross_chain_execute_tx,
  GovernanceClient.propagate_proposal / aggregate_votes / execute_cross_chain
  (mocked httpx)
- Parameter change execution (A4): build_parameter_apply_tx,
  validate_parameter_change — already existed but included for coverage

No real oracle, blockchain node, or governance service required — all HTTP
calls are mocked.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.bridge import (
    BridgeBlockHeader,
    ExternalOracleClient,
    FinalityConfig,
    InProcessVerifier,
    OracleFallbackPolicy,
    ProofVerificationResult,
    VerificationMode,
)
from aitbc.governance import (
    GovernanceClient,
    GovernanceTxType,
    ParameterChangeSchema,
    ProposalData,
    VoteData,
    build_cross_chain_execute_tx,
    build_parameter_apply_tx,
    build_proposal_propagation_tx,
    build_vote_aggregation_tx,
    validate_parameter_change,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = status_code < 400
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def _block_header(
    height: int = 100,
    state_root: str = "0xabc",
    confirmation_count: int = 10,
) -> BridgeBlockHeader:
    return BridgeBlockHeader(
        chain_id="ait-hub",
        height=height,
        hash="0xhash",
        parent_hash="0xparent",
        proposer="0xproposer",
        state_root=state_root,
        signature="0xsig",
        timestamp=datetime(2026, 6, 29, 12, 0, 0),
        confirmation_count=confirmation_count,
    )


def _finality_config() -> FinalityConfig:
    return FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)


def _proof(state_root: str = "0xabc") -> dict:
    return {
        "state_root": state_root,
        "lock_tx_hash": "0xtx",
        "amount": 100,
        "merkle_proof": [],
    }


# ---------------------------------------------------------------------------
# A1: ExternalOracleClient
# ---------------------------------------------------------------------------


class TestExternalOracleClientInit:
    def test_no_endpoints_warning(self) -> None:
        client = ExternalOracleClient()
        assert client.endpoints == []
        assert client.mode == VerificationMode.ORACLE

    def test_endpoints_stripped(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1/", "http://oracle2"])
        assert client.endpoints == ["http://oracle1", "http://oracle2"]

    def test_mode_is_oracle(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        assert client.mode == VerificationMode.ORACLE


class TestExternalOracleClientHealth:
    def test_is_healthy_true_when_endpoint_responds(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        mock_resp = _mock_response(status_code=200)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = MagicMock(return_value=mock_resp)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            assert client.is_healthy() is True

    def test_is_healthy_false_when_endpoint_fails(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = MagicMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            assert client.is_healthy() is False

    def test_is_healthy_false_when_no_endpoints(self) -> None:
        client = ExternalOracleClient()
        assert client.is_healthy() is False

    def test_is_healthy_tries_multiple_endpoints(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1", "http://oracle2"])
        # First endpoint fails, second succeeds.
        fail_resp = MagicMock()
        fail_resp.is_success = False
        fail_resp.status_code = 503
        ok_resp = _mock_response(status_code=200)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get = MagicMock(side_effect=[httpx.ConnectError("refused"), ok_resp])
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            assert client.is_healthy() is True


class TestExternalOracleClientVerifyProof:
    def test_verify_proof_success(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        oracle_resp = {
            "valid": True,
            "block_height": 100,
            "state_root": "0xabc",
            "finality_confirmed": True,
            "verification_mode": "oracle",
        }
        mock_resp = _mock_response(json_data=oracle_resp)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_resp)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = client.verify_proof(_proof(), _block_header(), _finality_config())
        assert result.valid is True
        assert result.verification_mode == VerificationMode.ORACLE
        assert result.block_height == 100
        assert result.finality_confirmed is True

    def test_verify_proof_all_endpoints_fail(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post = MagicMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = client.verify_proof(_proof(), _block_header(), _finality_config())
        assert result.valid is False
        assert "unavailable" in result.error.lower() or "all oracle" in result.error.lower()
        assert result.verification_mode == VerificationMode.ORACLE

    def test_verify_proof_no_endpoints(self) -> None:
        client = ExternalOracleClient()
        result = client.verify_proof(_proof(), _block_header(), _finality_config())
        assert result.valid is False
        assert "unavailable" in result.error.lower() or "all oracle" in result.error.lower()

    def test_verify_proof_failover_to_second_endpoint(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1", "http://oracle2"])
        oracle_resp = {"valid": True, "verification_mode": "oracle"}
        mock_resp = _mock_response(json_data=oracle_resp)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post = MagicMock(side_effect=[httpx.ConnectError("refused"), mock_resp])
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = client.verify_proof(_proof(), _block_header(), _finality_config())
        assert result.valid is True


class TestExternalOracleClientCheckFinality:
    def test_check_finality_true(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        mock_resp = _mock_response(json_data={"final": True})
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_resp)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            assert client.check_finality(_block_header(), _finality_config(), 100) is True

    def test_check_finality_false_on_failure(self) -> None:
        client = ExternalOracleClient(endpoints=["http://oracle1"])
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post = MagicMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_cls.return_value = mock_client
            assert client.check_finality(_block_header(), _finality_config(), 100) is False


# ---------------------------------------------------------------------------
# A2: OracleFallbackPolicy
# ---------------------------------------------------------------------------


class TestOracleFallbackPolicy:
    def test_oracle_healthy_uses_oracle(self) -> None:
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        policy._oracle_healthy = True

        oracle_result = ProofVerificationResult(valid=True, verification_mode=VerificationMode.ORACLE)
        with patch.object(oracle, "verify_proof", return_value=oracle_result):
            result = policy.verify_with_fallback(_proof(), _block_header(), _finality_config())
        assert result.valid is True
        assert policy.last_mode == VerificationMode.ORACLE

    def test_oracle_unhealthy_uses_in_process(self) -> None:
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        policy._oracle_healthy = False

        with patch.object(oracle, "verify_proof") as mock_oracle:
            policy.verify_with_fallback(_proof(), _block_header(), _finality_config())
        mock_oracle.assert_not_called()
        assert policy.last_mode == VerificationMode.IN_PROCESS

    def test_oracle_infrastructure_error_falls_back(self) -> None:
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        policy._oracle_healthy = True

        infra_error = ProofVerificationResult(
            valid=False,
            error="All oracle endpoints unavailable or failed",
            verification_mode=VerificationMode.ORACLE,
        )
        with patch.object(oracle, "verify_proof", return_value=infra_error):
            policy.verify_with_fallback(_proof(), _block_header(), _finality_config())
        assert policy.last_mode == VerificationMode.IN_PROCESS

    def test_oracle_genuine_failure_does_not_fall_back(self) -> None:
        """A genuine verification failure (not infra error) is returned, not fallen back from."""
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        policy._oracle_healthy = True

        genuine_fail = ProofVerificationResult(
            valid=False,
            error="Merkle proof verification failed",
            verification_mode=VerificationMode.ORACLE,
        )
        with patch.object(oracle, "verify_proof", return_value=genuine_fail):
            with patch.object(in_process, "verify_proof") as mock_inproc:
                result = policy.verify_with_fallback(_proof(), _block_header(), _finality_config())
        mock_inproc.assert_not_called()
        assert result.valid is False
        assert result.error == "Merkle proof verification failed"
        assert policy.last_mode == VerificationMode.ORACLE

    def test_check_finality_with_fallback_oracle_true(self) -> None:
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        policy._oracle_healthy = True

        with patch.object(oracle, "check_finality", return_value=True):
            assert policy.check_finality_with_fallback(_block_header(), _finality_config(), 100) is True

    def test_check_finality_with_fallback_oracle_false_uses_in_process(self) -> None:
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        policy._oracle_healthy = True

        with patch.object(oracle, "check_finality", return_value=False):
            with patch.object(in_process, "check_finality", return_value=True) as mock_inproc:
                assert policy.check_finality_with_fallback(_block_header(), _finality_config(), 100) is True
        mock_inproc.assert_called_once()

    def test_check_oracle_health_updates_status(self) -> None:
        oracle = ExternalOracleClient(endpoints=["http://oracle1"])
        in_process = InProcessVerifier()
        policy = OracleFallbackPolicy(oracle, in_process)
        assert policy.oracle_healthy is False
        with patch.object(oracle, "is_healthy", return_value=True):
            assert policy.check_oracle_health() is True
        assert policy.oracle_healthy is True


# ---------------------------------------------------------------------------
# A3: Cross-chain governance tx builders
# ---------------------------------------------------------------------------


class TestBuildProposalPropagationTx:
    def test_basic_propagation(self) -> None:
        proposal = ProposalData(
            proposal_id="prop_001",
            proposer="0xproposer",
            title="Test Proposal",
            description="A test",
            proposal_type="parameter_change",
            parameters={"key": "value"},
            voting_starts_block=100,
            voting_ends_block=200,
            chain_id="ait-hub",
        )
        tx = build_proposal_propagation_tx(proposal, "ait-island1", executor="0xexec")
        assert tx["type"] == GovernanceTxType.EXECUTE.value
        assert tx["proposal_id"] == "prop_001"
        assert tx["executor"] == "0xexec"
        assert tx["chain_id"] == "ait-island1"
        assert tx["target_chain"] == "ait-island1"
        assert tx["cross_chain_op"] == "proposal_propagation"
        assert tx["proposal"]["proposal_id"] == "prop_001"
        assert tx["proposal"]["source_chain"] == "ait-hub"
        assert tx["proposal"]["title"] == "Test Proposal"

    def test_executor_defaults_empty(self) -> None:
        proposal = ProposalData(proposal_id="p1", proposer="0x1", title="t", description="d")
        tx = build_proposal_propagation_tx(proposal, "ait-island1")
        assert tx["executor"] == ""


class TestBuildVoteAggregationTx:
    def test_basic_aggregation(self) -> None:
        votes = [
            VoteData(proposal_id="p1", voter="0x1", vote_type="for", voting_power=100, chain_id="ait-island1"),
            VoteData(proposal_id="p1", voter="0x2", vote_type="against", voting_power=50, chain_id="ait-island1"),
        ]
        tx = build_vote_aggregation_tx(votes, "ait-island1", executor="0xexec")
        assert tx["type"] == GovernanceTxType.EXECUTE.value
        assert tx["proposal_id"] == "p1"
        assert tx["cross_chain_op"] == "vote_aggregation"
        assert tx["source_chain"] == "ait-island1"
        assert tx["chain_id"] == "ait-hub"
        assert len(tx["votes"]) == 2
        assert tx["votes"][0]["voter"] == "0x1"
        assert tx["votes"][0]["vote_type"] == "for"
        assert tx["votes"][0]["source_chain"] == "ait-island1"

    def test_empty_votes_infers_proposal_id(self) -> None:
        tx = build_vote_aggregation_tx([], "ait-island1", proposal_id="p1")
        assert tx["proposal_id"] == "p1"
        assert tx["votes"] == []

    def test_proposal_id_inferred_from_first_vote(self) -> None:
        votes = [VoteData(proposal_id="p2", voter="0x1", vote_type="for")]
        tx = build_vote_aggregation_tx(votes, "ait-island1")
        assert tx["proposal_id"] == "p2"


class TestBuildCrossChainExecuteTx:
    def test_basic_execute(self) -> None:
        tx = build_cross_chain_execute_tx("p1", ["ait-island1", "ait-island2"], executor="0xexec")
        assert tx["type"] == GovernanceTxType.EXECUTE.value
        assert tx["proposal_id"] == "p1"
        assert tx["cross_chain_op"] == "cross_chain_execute"
        assert tx["target_chains"] == ["ait-island1", "ait-island2"]
        assert tx["chain_id"] == "ait-hub"

    def test_executor_defaults_empty(self) -> None:
        tx = build_cross_chain_execute_tx("p1", ["ait-island1"])
        assert tx["executor"] == ""

    def test_target_chains_copied(self) -> None:
        chains = ["ait-island1"]
        tx = build_cross_chain_execute_tx("p1", chains)
        chains.append("ait-island2")
        assert tx["target_chains"] == ["ait-island1"]


# ---------------------------------------------------------------------------
# A3: GovernanceClient cross-chain methods (mocked HTTP)
# ---------------------------------------------------------------------------


class TestGovernanceClientCrossChain:
    @pytest.mark.asyncio
    async def test_propagate_proposal(self) -> None:
        client = GovernanceClient()
        mock_resp = _mock_response(
            json_data={
                "proposal_id": "p1",
                "propagated_to": ["ait-island1"],
                "failed": [],
                "tx_hashes": {"ait-island1": "0xtx1"},
            }
        )
        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
            result = await client.propagate_proposal("p1", ["ait-island1"])
        assert result["proposal_id"] == "p1"
        assert result["propagated_to"] == ["ait-island1"]
        await client.close()

    @pytest.mark.asyncio
    async def test_aggregate_votes(self) -> None:
        client = GovernanceClient()
        mock_resp = _mock_response(
            json_data={
                "proposal_id": "p1",
                "total_for": 150,
                "total_against": 50,
                "total_abstain": 0,
                "chains_aggregated": ["ait-island1"],
                "votes": [],
            }
        )
        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
            result = await client.aggregate_votes("p1")
        assert result["total_for"] == 150
        assert result["chains_aggregated"] == ["ait-island1"]
        await client.close()

    @pytest.mark.asyncio
    async def test_execute_cross_chain(self) -> None:
        client = GovernanceClient()
        mock_resp = _mock_response(
            json_data={
                "proposal_id": "p1",
                "executed_on": ["ait-island1", "ait-island2"],
                "failed": [],
                "tx_hashes": {"ait-island1": "0xtx1", "ait-island2": "0xtx2"},
            }
        )
        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
            result = await client.execute_cross_chain("p1")
        assert result["executed_on"] == ["ait-island1", "ait-island2"]
        await client.close()


# ---------------------------------------------------------------------------
# A4: Parameter change execution (already existed — coverage tests)
# ---------------------------------------------------------------------------


class TestParameterChangeExecution:
    def test_build_parameter_apply_tx(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="block_reward",
            old_value=10,
            new_value=15,
            description="Increase block reward",
        )
        tx = build_parameter_apply_tx(schema, "p1", "0xexec", "ait-hub")
        assert tx["type"] == GovernanceTxType.EXECUTE.value
        assert tx["proposal_id"] == "p1"
        assert tx["parameter_change"]["target_service"] == "blockchain"
        assert tx["parameter_change"]["parameter_name"] == "block_reward"
        assert tx["parameter_change"]["old_value"] == 10
        assert tx["parameter_change"]["new_value"] == 15

    def test_validate_parameter_change_valid(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="block_reward",
            old_value=10,
            new_value=15,
        )
        errors = validate_parameter_change(schema)
        assert errors == []

    def test_validate_parameter_change_unknown_service(self) -> None:
        schema = ParameterChangeSchema(
            target_service="unknown_service",
            parameter_name="foo",
            old_value=1,
            new_value=2,
        )
        errors = validate_parameter_change(schema)
        assert len(errors) == 1
        assert "unknown target_service" in errors[0]

    def test_validate_parameter_change_unknown_parameter(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="nonexistent_param",
            old_value=1,
            new_value=2,
        )
        errors = validate_parameter_change(schema)
        assert len(errors) == 1
        assert "unknown parameter_name" in errors[0]

    def test_validate_parameter_change_noop(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="block_reward",
            old_value=10,
            new_value=10,
        )
        errors = validate_parameter_change(schema)
        assert any("no-op" in e for e in errors)

    def test_validate_parameter_change_old_value_mismatch(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="block_reward",
            old_value=10,
            new_value=15,
        )
        current_config = {"block_reward": 12}
        errors = validate_parameter_change(schema, current_config)
        assert any("old_value mismatch" in e for e in errors)

    def test_validate_parameter_change_old_value_matches_config(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="block_reward",
            old_value=10,
            new_value=15,
        )
        current_config = {"block_reward": 10}
        errors = validate_parameter_change(schema, current_config)
        assert errors == []
