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
        result = consensus_status_route(request=None)

    assert result["mode"] == "MultiValidatorPoA"
    assert result["multi_validator_enabled"] is True
    assert result["active_validators"] == 4
    assert result["total_validators"] == 4
    assert result["fault_tolerance"] == 1
    assert result["required_messages"] == 3
    assert result["min_attestations"] == 1


@pytest.mark.asyncio
async def test_consensus_status_three_validators_crash_only(monkeypatch) -> None:
    """With 3 validators BFT fault tolerance is 0; the #1061 quorum formula gives ceil((3+0+1)/2)=2."""
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

    # #2409: view/sequence are derived from the sealed head, not the dead
    # persisted snapshots — feed a head row through a fake session_scope.
    from contextlib import contextmanager
    from datetime import UTC, datetime, timedelta

    head_ts = datetime.now(UTC) - timedelta(seconds=5)

    @contextmanager
    def fake_scope(chain_id):  # noqa: ARG001
        session = MagicMock()
        session.exec.return_value.first.return_value = (34147, head_ts)
        yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", fake_scope)

    with patch("aitbc_chain.consensus.multi_validator_poa.get_consensus", return_value=mock_consensus):
        result = consensus_status_route(request=None)

    assert result["mode"] == "MultiValidatorPoA + PBFT"
    assert result["active_validators"] == 3
    assert result["fault_tolerance"] == 0
    assert result["required_messages"] == 2
    assert result["min_attestations"] == 1
    # sequence = sealed head height; view = proposer round elapsed since head
    assert result["current_sequence"] == 34147
    assert result["current_view"] == 0  # 5s < any sane proposer round
    assert result["current_epoch"] == 0
