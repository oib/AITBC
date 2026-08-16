"""Unit tests for the aitbc.governance shared SDK (v0.7.3 §A4).

Covers:
- Governance types (GovernanceTxType, ProposalType, VoteChoice, dataclasses)
- GovernanceClient init + async context manager + mocked REST methods
- On-chain utilities (build_proposal_tx, build_vote_tx, build_execute_tx,
  build_parameter_change_params, validate_governance_payload)

No real governance service required — all HTTP calls are stubbed with AsyncMock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from aitbc.governance import (
    ExecuteData,
    GovernanceClient,
    GovernanceConfig,
    GovernanceTxType,
    ParameterChangeSchema,
    ProposalData,
    ProposalType,
    VoteChoice,
    VoteData,
    build_execute_tx,
    build_parameter_change_params,
    build_proposal_tx,
    build_vote_tx,
    validate_governance_payload,
)
from aitbc.governance.client import GovernanceClient as _GovernanceClient  # noqa: F401

RPC_URL = "http://localhost:8105"


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
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(f"HTTP {status_code}", request=MagicMock(), response=resp)
    return resp


def _sample_proposal_data() -> ProposalData:
    return ProposalData(
        proposal_id="prop_001",
        proposer="alice",
        title="Increase block reward",
        description="Raise the per-block reward from 1.0 to 1.5 AIT",
        proposal_type=ProposalType.PARAMETER_CHANGE.value,
        parameters={"target": "block_reward", "old": 1.0, "new": 1.5},
        voting_starts_block=100,
        voting_ends_block=7300,
    )


def _sample_vote_data() -> VoteData:
    return VoteData(
        proposal_id="prop_001",
        voter="bob",
        vote_type=VoteChoice.FOR.value,
        voting_power=500.0,
        reason="Support this change",
    )


# ---------------------------------------------------------------------------
# Types tests (A1)
# ---------------------------------------------------------------------------


class TestGovernanceTxType:
    def test_values(self) -> None:
        assert GovernanceTxType.PROPOSE.value == "GOVERNANCE_PROPOSE"
        assert GovernanceTxType.VOTE.value == "GOVERNANCE_VOTE"
        assert GovernanceTxType.EXECUTE.value == "GOVERNANCE_EXECUTE"

    def test_str_conversion(self) -> None:
        assert str(GovernanceTxType.PROPOSE) == "GOVERNANCE_PROPOSE"


class TestProposalType:
    def test_values(self) -> None:
        assert ProposalType.PARAMETER_CHANGE.value == "parameter_change"
        assert ProposalType.FUND_ALLOCATION.value == "fund_allocation"
        assert ProposalType.VALIDATOR_CHANGE.value == "validator_change"
        assert ProposalType.EMERGENCY.value == "emergency"
        assert ProposalType.GENERAL.value == "general"


class TestVoteChoice:
    def test_values(self) -> None:
        assert VoteChoice.FOR.value == "for"
        assert VoteChoice.AGAINST.value == "against"
        assert VoteChoice.ABSTAIN.value == "abstain"


class TestGovernanceConfig:
    def test_defaults(self) -> None:
        cfg = GovernanceConfig()
        assert cfg.rpc_url == "http://localhost:8105"
        assert cfg.blockchain_rpc_url == "http://localhost:8202"
        assert cfg.chain_id == "ait-hub"
        assert cfg.voting_period_blocks == 7200
        assert cfg.quorum_percent == 30.0
        assert cfg.approval_percent == 50.0
        assert cfg.timelock_blocks == 86400
        assert cfg.snapshot_delay_blocks == 100
        assert cfg.timeout == 30

    def test_custom(self) -> None:
        cfg = GovernanceConfig(rpc_url="http://gov:9000", chain_id="ait-2")
        assert cfg.rpc_url == "http://gov:9000"
        assert cfg.chain_id == "ait-2"


class TestProposalData:
    def test_defaults(self) -> None:
        d = ProposalData(proposal_id="p1", proposer="a", title="t", description="d")
        assert d.proposal_type == "general"
        assert d.parameters == {}
        assert d.voting_starts_block == 0
        assert d.voting_ends_block == 0
        assert d.chain_id == "ait-hub"

    def test_full(self) -> None:
        d = _sample_proposal_data()
        assert d.proposal_id == "prop_001"
        assert d.proposer == "alice"
        assert d.parameters["new"] == 1.5


class TestVoteData:
    def test_defaults(self) -> None:
        v = VoteData(proposal_id="p1", voter="b", vote_type="for")
        assert v.voting_power == 0.0
        assert v.reason == ""
        assert v.chain_id == "ait-hub"


class TestExecuteData:
    def test_defaults(self) -> None:
        e = ExecuteData(proposal_id="p1", executor="a")
        assert e.chain_id == "ait-hub"


class TestParameterChangeSchema:
    def test_defaults(self) -> None:
        s = ParameterChangeSchema(target_service="blockchain", parameter_name="reward", old_value=1.0, new_value=1.5)
        assert s.description == ""


# ---------------------------------------------------------------------------
# Client tests (A2)
# ---------------------------------------------------------------------------


class TestGovernanceClientInit:
    def test_default_config(self) -> None:
        c = GovernanceClient()
        assert c.config.rpc_url == "http://localhost:8105"
        assert c._client is None

    def test_custom_config(self) -> None:
        cfg = GovernanceConfig(rpc_url="http://custom:8000", timeout=10)
        c = GovernanceClient(cfg)
        assert c.config.rpc_url == "http://custom:8000"
        assert c.config.timeout == 10

    def test_config_property(self) -> None:
        c = GovernanceClient()
        assert isinstance(c.config, GovernanceConfig)


class TestGovernanceClientContextManager:
    async def test_aenter_creates_client(self) -> None:
        async with GovernanceClient() as c:
            assert c._client is not None
        assert c._client is None

    async def test_aexit_closes_client(self) -> None:
        c = GovernanceClient()
        await c.__aenter__()
        assert c._client is not None
        await c.__aexit__(None, None, None)
        assert c._client is None


class TestGovernanceClientMethods:
    """Test all client methods with mocked httpx.AsyncClient."""

    async def test_create_proposal(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"proposal_id": "prop_001", "status": "active"})
        c._client = MagicMock()
        c._client.post = AsyncMock(return_value=mock_resp)
        result = await c.create_proposal({"title": "Test", "proposer": "alice"})
        assert result["proposal_id"] == "prop_001"
        c._client.post.assert_called_once()

    async def test_get_proposal(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"proposal_id": "prop_001", "title": "Test"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_proposal("prop_001")
        assert result["proposal_id"] == "prop_001"
        c._client.get.assert_called_once()

    async def test_list_proposals_list_response(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, [{"proposal_id": "p1"}, {"proposal_id": "p2"}])
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_proposals()
        assert len(result) == 2

    async def test_list_proposals_wrapped_response(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"proposals": [{"proposal_id": "p1"}]})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_proposals(status="active")
        assert len(result) == 1
        # Verify status filter passed as params
        call_args = c._client.get.call_args
        assert call_args.kwargs["params"]["status"] == "active"

    async def test_list_proposals_empty_response(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"unexpected": "shape"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_proposals()
        assert result == []

    async def test_cast_vote(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"vote_id": "v1", "status": "recorded"})
        c._client = MagicMock()
        c._client.post = AsyncMock(return_value=mock_resp)
        result = await c.cast_vote({"proposal_id": "p1", "voter": "bob", "vote_type": "for"})
        assert result["vote_id"] == "v1"

    async def test_list_votes(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, [{"vote_id": "v1"}, {"vote_id": "v2"}])
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.list_votes(proposal_id="p1")
        assert len(result) == 2

    async def test_execute_proposal(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"status": "executed", "tx_hash": "0xabc"})
        c._client = MagicMock()
        c._client.post = AsyncMock(return_value=mock_resp)
        result = await c.execute_proposal("prop_001")
        assert result["tx_hash"] == "0xabc"
        # Verify v2 endpoint path used
        call_args = c._client.post.call_args
        assert "prop_001/execute" in call_args.args[0]

    async def test_get_status(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"status": "healthy"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_status()
        assert result["status"] == "healthy"

    async def test_get_voting_power(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"address": "alice", "voting_power": 1000.0})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_voting_power("alice")
        assert result["voting_power"] == 1000.0

    async def test_get_analytics(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"period": "daily", "proposals": 5})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_analytics(period="daily")
        assert result["proposals"] == 5

    async def test_get_params(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"voting_period_blocks": 7200})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.get_params()
        assert result["voting_period_blocks"] == 7200

    async def test_health(self) -> None:
        c = GovernanceClient()
        mock_resp = _mock_response(200, {"status": "ok"})
        c._client = MagicMock()
        c._client.get = AsyncMock(return_value=mock_resp)
        result = await c.health()
        assert result["status"] == "ok"

    async def test_close(self) -> None:
        c = GovernanceClient()
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        c._client = mock_client
        await c.close()
        mock_client.aclose.assert_called_once()
        assert c._client is None

    async def test_close_when_not_open(self) -> None:
        c = GovernanceClient()
        await c.close()  # should not raise
        assert c._client is None

    async def test_ensure_client_creates_lazy(self) -> None:
        c = GovernanceClient()
        client = c._ensure_client()
        assert client is not None
        assert c._client is client
        # Second call returns same instance
        client2 = c._ensure_client()
        assert client2 is client


# ---------------------------------------------------------------------------
# On-chain utilities tests (A3)
# ---------------------------------------------------------------------------


class TestBuildProposalTx:
    def test_builds_correct_payload(self) -> None:
        data = _sample_proposal_data()
        tx = build_proposal_tx(data)
        assert tx["type"] == "GOVERNANCE_PROPOSE"
        assert tx["proposal_id"] == "prop_001"
        assert tx["proposer"] == "alice"
        assert tx["title"] == "Increase block reward"
        assert tx["description"] == "Raise the per-block reward from 1.0 to 1.5 AIT"
        assert tx["proposal_type"] == "parameter_change"
        assert tx["parameters"]["new"] == 1.5
        assert tx["voting_starts_block"] == 100
        assert tx["voting_ends_block"] == 7300
        assert tx["chain_id"] == "ait-hub"


class TestBuildVoteTx:
    def test_builds_correct_payload(self) -> None:
        data = _sample_vote_data()
        tx = build_vote_tx(data)
        assert tx["type"] == "GOVERNANCE_VOTE"
        assert tx["proposal_id"] == "prop_001"
        assert tx["voter"] == "bob"
        assert tx["vote_type"] == "for"
        assert tx["voting_power"] == 500.0
        assert tx["reason"] == "Support this change"
        assert tx["chain_id"] == "ait-hub"


class TestBuildExecuteTx:
    def test_builds_correct_payload(self) -> None:
        tx = build_execute_tx("prop_001", "carol")
        assert tx["type"] == "GOVERNANCE_EXECUTE"
        assert tx["proposal_id"] == "prop_001"
        assert tx["executor"] == "carol"
        assert tx["chain_id"] == "ait-hub"

    def test_custom_chain_id(self) -> None:
        tx = build_execute_tx("prop_001", "carol", chain_id="ait-2")
        assert tx["chain_id"] == "ait-2"


class TestBuildParameterChangeParams:
    def test_builds_correct_params(self) -> None:
        schema = ParameterChangeSchema(
            target_service="blockchain",
            parameter_name="block_reward",
            old_value=1.0,
            new_value=1.5,
            description="Raise reward",
        )
        params = build_parameter_change_params(schema)
        assert params["target_service"] == "blockchain"
        assert params["parameter_name"] == "block_reward"
        assert params["old_value"] == 1.0
        assert params["new_value"] == 1.5
        assert params["description"] == "Raise reward"


class TestValidateGovernancePayload:
    def test_valid_proposal(self) -> None:
        data = _sample_proposal_data()
        tx = build_proposal_tx(data)
        errors = validate_governance_payload(GovernanceTxType.PROPOSE, tx)
        assert errors == []

    def test_valid_vote(self) -> None:
        data = _sample_vote_data()
        tx = build_vote_tx(data)
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert errors == []

    def test_valid_execute(self) -> None:
        tx = build_execute_tx("prop_001", "carol")
        errors = validate_governance_payload(GovernanceTxType.EXECUTE, tx)
        assert errors == []

    def test_missing_required_field_proposal(self) -> None:
        tx = build_proposal_tx(_sample_proposal_data())
        del tx["title"]
        errors = validate_governance_payload(GovernanceTxType.PROPOSE, tx)
        assert any("title" in e for e in errors)

    def test_empty_required_field_proposal(self) -> None:
        tx = build_proposal_tx(_sample_proposal_data())
        tx["title"] = "   "
        errors = validate_governance_payload(GovernanceTxType.PROPOSE, tx)
        assert any("title" in e for e in errors)

    def test_missing_required_field_vote(self) -> None:
        tx = build_vote_tx(_sample_vote_data())
        del tx["voter"]
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert any("voter" in e for e in errors)

    def test_missing_required_field_execute(self) -> None:
        tx = build_execute_tx("prop_001", "carol")
        del tx["executor"]
        errors = validate_governance_payload(GovernanceTxType.EXECUTE, tx)
        assert any("executor" in e for e in errors)

    def test_type_mismatch(self) -> None:
        tx = build_proposal_tx(_sample_proposal_data())
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert any("type mismatch" in e for e in errors)

    def test_invalid_proposal_type(self) -> None:
        tx = build_proposal_tx(_sample_proposal_data())
        tx["proposal_type"] = "invalid_type"
        errors = validate_governance_payload(GovernanceTxType.PROPOSE, tx)
        assert any("invalid proposal_type" in e for e in errors)

    def test_invalid_vote_type(self) -> None:
        tx = build_vote_tx(_sample_vote_data())
        tx["vote_type"] = "yes"
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert any("invalid vote_type" in e for e in errors)

    def test_voting_ends_before_starts(self) -> None:
        tx = build_proposal_tx(_sample_proposal_data())
        tx["voting_starts_block"] = 500
        tx["voting_ends_block"] = 100
        errors = validate_governance_payload(GovernanceTxType.PROPOSE, tx)
        assert any("voting_ends_block" in e for e in errors)

    def test_negative_voting_power(self) -> None:
        tx = build_vote_tx(_sample_vote_data())
        tx["voting_power"] = -10.0
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert any("voting_power" in e for e in errors)

    def test_non_numeric_voting_power(self) -> None:
        tx = build_vote_tx(_sample_vote_data())
        tx["voting_power"] = "lots"
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert any("voting_power" in e for e in errors)

    def test_zero_voting_power_valid(self) -> None:
        tx = build_vote_tx(_sample_vote_data())
        tx["voting_power"] = 0
        errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
        assert errors == []

    def test_all_valid_proposal_types(self) -> None:
        for pt in ProposalType:
            tx = build_proposal_tx(_sample_proposal_data())
            tx["proposal_type"] = pt.value
            errors = validate_governance_payload(GovernanceTxType.PROPOSE, tx)
            assert errors == [], f"proposal_type={pt.value} should be valid"

    def test_all_valid_vote_choices(self) -> None:
        for vc in VoteChoice:
            tx = build_vote_tx(_sample_vote_data())
            tx["vote_type"] = vc.value
            errors = validate_governance_payload(GovernanceTxType.VOTE, tx)
            assert errors == [], f"vote_type={vc.value} should be valid"
