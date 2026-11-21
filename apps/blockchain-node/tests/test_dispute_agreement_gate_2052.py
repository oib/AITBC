"""Tests for #2052: real arbitrator identities + EVM agreement binding.

- ``AITBC_DISPUTE_ARBITRATORS`` seeds the authorized arbitrator set;
  unset keeps the historical placeholders (dev default).
- ``AITBC_DISPUTE_AGREEMENT_RPC_URL`` + ``AITBC_DISPUTE_AGREEMENT_CONTRACT``
  make ``file_dispute`` validate the agreement on AIPowerRental: must
  exist, filer must be provider/consumer, respondent the counterparty.
"""

from __future__ import annotations

import pytest
from eth_abi import encode
from eth_utils import to_checksum_address
from unittest.mock import MagicMock

from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract
from aitbc_chain.rpc import dispute_resolution_service as svc_mod
from aitbc_chain.rpc.dispute_resolution_service import DisputeResolutionService

REAL_ARB = to_checksum_address("0x8f3c8f9f2f4b7e1a5c6d3b2a1f0e9d8c7b6a5f4e")
PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
CONSUMER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
STRANGER = "0x9999999999999999999999999999999999999999"


def _agreement_head(provider=PROVIDER, consumer=CONSUMER, agreement_id=0):
    return encode(
        svc_mod._AGREEMENT_HEAD_TYPES,
        [agreement_id, provider, consumer, 3600, 10**18, 0, 3600, 0, 0],
    )


def _fake_web3(payload: bytes):
    w3 = MagicMock()
    w3.is_connected.return_value = True
    w3.eth.call.return_value = payload
    return w3


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "AITBC_DISPUTE_ARBITRATORS",
        "AITBC_DISPUTE_AGREEMENT_RPC_URL",
        "AITBC_DISPUTE_AGREEMENT_CONTRACT",
    ):
        monkeypatch.delenv(var, raising=False)


# --- arbitrator seeding ---


def test_env_seeds_real_arbitrators(monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{REAL_ARB}:95, 0x2222222222222222222222222222222222222222:80")
    contract = DisputeResolutionContract()
    assert REAL_ARB in contract.arbitrators
    assert contract.arbitrators[REAL_ARB] == 95
    assert "0x1111111111111111111111111111111111111111" not in contract.arbitrators


def test_unset_env_keeps_placeholders():
    contract = DisputeResolutionContract()
    assert "0x1111111111111111111111111111111111111111" in contract.arbitrators


def test_malformed_entries_skipped(monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", "not-an-address:50,,0x1234:abc")
    contract = DisputeResolutionContract()
    assert contract.arbitrators == {
        "0x1111111111111111111111111111111111111111": 90,
        "0x2222222222222222222222222222222222222222": 85,
        "0x3333333333333333333333333333333333333333": 88,
    }


def test_env_arbitrator_can_vote_with_checksum_address(monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{REAL_ARB.lower()}:90")
    contract = DisputeResolutionContract()
    filed = contract.file_dispute(1, CONSUMER, "Payment", "r", "0x" + "00" * 32, PROVIDER)
    did = filed["dispute_id"]
    # auth returns EIP-55 checksummed addresses; env stored checksummed too
    vote = contract.submit_arbitration_vote(did, True, 80, "ok", REAL_ARB)
    assert vote["success"], vote


# --- EVM agreement gate ---


def _enable_gate(monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_AGREEMENT_RPC_URL", "http://evm.test")
    monkeypatch.setenv("AITBC_DISPUTE_AGREEMENT_CONTRACT", "0x7bD9485aE10c7d5AB63071D72cd666E02044986B")


def test_gate_disabled_allows_any_agreement():
    svc = DisputeResolutionService()
    result = svc.file_dispute(999999, STRANGER, "Payment", "r", "0x" + "00" * 32, PROVIDER)
    assert result["success"]


def test_gate_accepts_valid_participant_filing(monkeypatch):
    _enable_gate(monkeypatch)
    monkeypatch.setattr("web3.Web3", MagicMock(return_value=_fake_web3(_agreement_head())))
    svc = DisputeResolutionService()
    result = svc.file_dispute(0, PROVIDER, "Payment", "r", "0x" + "00" * 32, CONSUMER)
    assert result["success"], result


def test_gate_rejects_nonparticipant(monkeypatch):
    _enable_gate(monkeypatch)
    monkeypatch.setattr("web3.Web3", MagicMock(return_value=_fake_web3(_agreement_head())))
    svc = DisputeResolutionService()
    result = svc.file_dispute(0, PROVIDER, "Payment", "r", "0x" + "00" * 32, STRANGER)
    assert not result["success"]
    assert "not a participant" in result["error"].lower()


def test_gate_rejects_wrong_respondent(monkeypatch):
    _enable_gate(monkeypatch)
    monkeypatch.setattr("web3.Web3", MagicMock(return_value=_fake_web3(_agreement_head())))
    svc = DisputeResolutionService()
    # consumer files against a third party instead of the provider
    result = svc.file_dispute(0, STRANGER, "Payment", "r", "0x" + "00" * 32, CONSUMER)
    assert not result["success"]
    assert "counterparty" in result["error"].lower()


def test_gate_fails_closed_on_rpc_error(monkeypatch):
    _enable_gate(monkeypatch)
    w3 = MagicMock()
    w3.is_connected.return_value = False
    monkeypatch.setattr("web3.Web3", MagicMock(return_value=w3))
    svc = DisputeResolutionService()
    result = svc.file_dispute(0, PROVIDER, "Payment", "r", "0x" + "00" * 32, CONSUMER)
    assert not result["success"]
    assert "unverifiable" in result["error"].lower() or "unavailable" in result["error"].lower()


def test_gate_fails_closed_on_revert(monkeypatch):
    _enable_gate(monkeypatch)
    from web3.exceptions import ContractLogicError

    w3 = _fake_web3(b"")
    w3.eth.call.side_effect = ContractLogicError("execution reverted: agreement does not exist")
    monkeypatch.setattr("web3.Web3", MagicMock(return_value=w3))
    svc = DisputeResolutionService()
    result = svc.file_dispute(77, PROVIDER, "Payment", "r", "0x" + "00" * 32, CONSUMER)
    assert not result["success"]
    assert "not found" in result["error"].lower()
