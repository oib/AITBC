"""Tests for the /v1/consensus/status BFT field reporting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aitbc_chain.config import settings
from aitbc_chain.rpc.routers.consensus import consensus_status_route


@pytest.mark.asyncio
async def test_consensus_status_reports_standard_bft_values(monkeypatch) -> None:
    """With 4 active validators, fault tolerance is 1 and required messages are 3."""
    validator = MagicMock()
    validator.is_active = True
    validator.role = MagicMock()
    validator.role.value = "validator"

    validators = {f"0x{i}": validator for i in range(4)}
    mock_consensus = MagicMock()
    mock_consensus.validators = validators
    mock_consensus.get_consensus_participants.return_value = list(validators.keys())

    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_set", ",".join(validators))
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 1)
    monkeypatch.setattr(settings, "pbft_consensus_enabled", False)
    monkeypatch.setattr(settings, "chain_id", "ait-test")

    with patch("aitbc_chain.consensus.multi_validator_poa.get_consensus", return_value=mock_consensus):
        result = await consensus_status_route()

    assert result["mode"] == "MultiValidatorPoA"
    assert result["multi_validator_enabled"] is True
    assert result["active_validators"] == 4
    assert result["total_validators"] == 4
    assert result["fault_tolerance"] == 1
    assert result["required_messages"] == 3
    assert result["min_attestations"] == 1


@pytest.mark.asyncio
async def test_consensus_status_three_validators_crash_only(monkeypatch) -> None:
    """With 3 validators BFT fault tolerance is 0; only one validator can crash."""
    validator = MagicMock()
    validator.is_active = True
    validator.role = MagicMock()
    validator.role.value = "validator"

    validators = {f"0x{i}": validator for i in range(3)}
    mock_consensus = MagicMock()
    mock_consensus.validators = validators
    mock_consensus.get_consensus_participants.return_value = list(validators.keys())
    mock_consensus._pbft_view = 0
    mock_consensus._pbft_sequence = 0
    mock_consensus._current_epoch = 0

    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_set", ",".join(validators))
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 1)
    monkeypatch.setattr(settings, "pbft_consensus_enabled", True)
    monkeypatch.setattr(settings, "chain_id", "ait-test")

    with patch("aitbc_chain.consensus.multi_validator_poa.get_consensus", return_value=mock_consensus):
        result = await consensus_status_route()

    assert result["mode"] == "MultiValidatorPoA + PBFT"
    assert result["active_validators"] == 3
    assert result["fault_tolerance"] == 0
    assert result["required_messages"] == 1
    assert result["min_attestations"] == 1
    assert result["current_view"] == 0
    assert result["current_sequence"] == 0
    assert result["current_epoch"] == 0
