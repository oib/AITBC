"""Unit tests for aitbc.governance.types (v0.10.1 A2).

Covers ParameterChangeSchema — field validation, to_apply_dict() helper,
and backward compatibility with existing proposal data.
"""

from __future__ import annotations

from aitbc.governance.types import (
    ExecuteData,
    GovernanceConfig,
    GovernanceTxType,
    ParameterChangeSchema,
    ProposalData,
    ProposalType,
    VoteChoice,
)


def test_parameter_change_schema_basic_fields() -> None:
    """ParameterChangeSchema has all required fields."""
    schema = ParameterChangeSchema(
        target_service="poolhub",
        parameter_name="max_concurrent",
        old_value=10,
        new_value=20,
    )
    assert schema.target_service == "poolhub"
    assert schema.parameter_name == "max_concurrent"
    assert schema.old_value == 10
    assert schema.new_value == 20
    assert schema.description == ""


def test_parameter_change_schema_with_description() -> None:
    """ParameterChangeSchema accepts an optional description."""
    schema = ParameterChangeSchema(
        target_service="marketplace",
        parameter_name="matching_fee_percent",
        old_value=5.0,
        new_value=3.0,
        description="Reduce marketplace matching fee from 5% to 3%",
    )
    assert schema.description == "Reduce marketplace matching fee from 5% to 3%"


def test_parameter_change_schema_to_apply_dict_poolhub() -> None:
    """to_apply_dict() produces the request body for pool-hub parameter API."""
    schema = ParameterChangeSchema(
        target_service="poolhub",
        parameter_name="max_concurrent",
        old_value=10,
        new_value=20,
    )
    apply_dict = schema.to_apply_dict()
    assert apply_dict == {
        "target_service": "poolhub",
        "parameter_name": "max_concurrent",
        "new_value": 20,
    }


def test_parameter_change_schema_to_apply_dict_marketplace() -> None:
    """to_apply_dict() produces the request body for marketplace parameter API."""
    schema = ParameterChangeSchema(
        target_service="marketplace",
        parameter_name="matching_fee_percent",
        old_value=5.0,
        new_value=3.0,
    )
    apply_dict = schema.to_apply_dict()
    assert apply_dict["target_service"] == "marketplace"
    assert apply_dict["parameter_name"] == "matching_fee_percent"
    assert apply_dict["new_value"] == 3.0


def test_parameter_change_schema_to_apply_dict_blockchain() -> None:
    """to_apply_dict() works for blockchain target service."""
    schema = ParameterChangeSchema(
        target_service="blockchain",
        parameter_name="block_time_seconds",
        old_value=2,
        new_value=3,
    )
    apply_dict = schema.to_apply_dict()
    assert apply_dict["target_service"] == "blockchain"
    assert apply_dict["new_value"] == 3


def test_parameter_change_schema_stored_in_proposal_data() -> None:
    """ParameterChangeSchema can be stored in ProposalData.parameters dict."""
    schema = ParameterChangeSchema(
        target_service="poolhub",
        parameter_name="enabled",
        old_value=True,
        new_value=False,
    )
    proposal = ProposalData(
        proposal_id="prop-1",
        proposer="0xabc",
        title="Disable whisper service",
        description="Temporarily disable whisper",
        proposal_type=ProposalType.PARAMETER_CHANGE.value,
        parameters={
            "target_service": schema.target_service,
            "parameter_name": schema.parameter_name,
            "old_value": schema.old_value,
            "new_value": schema.new_value,
        },
    )
    assert proposal.parameters["target_service"] == "poolhub"
    assert proposal.parameters["new_value"] is False


def test_governance_tx_type_values() -> None:
    """GovernanceTxType has the expected enum values."""
    assert GovernanceTxType.PROPOSE.value == "GOVERNANCE_PROPOSE"
    assert GovernanceTxType.VOTE.value == "GOVERNANCE_VOTE"
    assert GovernanceTxType.EXECUTE.value == "GOVERNANCE_EXECUTE"


def test_proposal_type_values() -> None:
    """ProposalType has the expected enum values."""
    assert ProposalType.PARAMETER_CHANGE.value == "parameter_change"
    assert ProposalType.EMERGENCY.value == "emergency"


def test_vote_choice_values() -> None:
    """VoteChoice has the expected enum values."""
    assert VoteChoice.FOR.value == "for"
    assert VoteChoice.AGAINST.value == "against"
    assert VoteChoice.ABSTAIN.value == "abstain"


def test_governance_config_defaults() -> None:
    """GovernanceConfig has sensible defaults."""
    config = GovernanceConfig()
    assert config.chain_id == "ait-hub"
    assert config.voting_period_blocks > 0
    assert config.quorum_percent > 0
    assert config.approval_percent > 0


def test_execute_data_basic() -> None:
    """ExecuteData has the required fields."""
    data = ExecuteData(proposal_id="prop-1", executor="0xabc")
    assert data.proposal_id == "prop-1"
    assert data.executor == "0xabc"
    assert data.chain_id == "ait-hub"
