"""Unit tests for the aitbc.bridge security layer (v0.7.1 §A4).

Covers:
- Validator types (ValidatorInfo, ValidatorSet, ThresholdProof)
- Extended BridgeProof with validator_signatures
- Extended BridgeConfig with multi-sig defaults
- Multi-sig utilities (recover_all_signers, check_threshold,
  verify_threshold_signatures) with mocked recover_signer
- ValidatorSetRegistry (register, get, epoch tracking, membership,
  advance_epoch, remove_inactive, unknown chain)
- BridgeClient validator RPC methods (register_validator,
  get_validator_set, security_status) with mocked httpx

No real blockchain node or crypto library required — recover_signer is
patched to return deterministic addresses.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.bridge import (
    BridgeClient,
    BridgeConfig,
    BridgeProof,
    ThresholdProof,
    ValidatorInfo,
    ValidatorSet,
    ValidatorSetRegistry,
    check_threshold,
    recover_all_signers,
    verify_threshold_signatures,
)
from aitbc.bridge.multisig import recover_all_signers as _recover_all_signers

RPC_URL = "http://localhost:8202"


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
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=resp,
        )
    return resp


def _mock_async_client(resp: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns the given response."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    client.aclose = AsyncMock()
    return client


def _validator(
    address: str,
    *,
    chain_id: str = "ait-hub",
    epoch: int = 1,
    is_active: bool = True,
    public_key: str | None = None,
) -> ValidatorInfo:
    return ValidatorInfo(
        address=address,
        public_key=public_key or f"{address}pub",
        chain_id=chain_id,
        epoch=epoch,
        is_active=is_active,
        registered_at=datetime(2026, 1, 1, 0, 0, 0) if is_active else None,
    )


def _validator_set(
    addresses: list[str],
    *,
    chain_id: str = "ait-hub",
    epoch: int = 1,
    threshold: int = 3,
) -> ValidatorSet:
    return ValidatorSet(
        chain_id=chain_id,
        epoch=epoch,
        validators=[_validator(a, chain_id=chain_id, epoch=epoch) for a in addresses],
        threshold=threshold,
        total=len(addresses),
    )


def _threshold_proof(
    *,
    proposer_signature: str = "0xprop",
    validator_signatures: list[str] | None = None,
    source_chain: str = "ait-hub",
    chain_id: str = "ait-hub",
) -> ThresholdProof:
    return ThresholdProof(
        source_chain=source_chain,
        lock_tx_hash="0xlock",
        amount=3600,
        sender="0xSender",
        recipient="0xRecipient",
        chain_id=chain_id,
        block_height=100,
        block_hash="0xblock",
        proposer_signature=proposer_signature,
        validator_signatures=validator_signatures or [],
    )


# ---------------------------------------------------------------------------
# A1 — Validator types
# ---------------------------------------------------------------------------


def test_validator_info_dataclass() -> None:
    info = _validator("0xVal1", public_key="0xpub1")
    assert info.address == "0xVal1"
    assert info.public_key == "0xpub1"
    assert info.chain_id == "ait-hub"
    assert info.epoch == 1
    assert info.is_active is True
    assert info.registered_at == datetime(2026, 1, 1, 0, 0, 0)


def test_validator_info_inactive_defaults() -> None:
    info = ValidatorInfo(
        address="0xVal2",
        public_key="0xpub2",
        chain_id="ait-2",
        epoch=2,
        is_active=False,
    )
    assert info.is_active is False
    assert info.registered_at is None


def test_validator_set_addresses_property() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC"])
    assert vset.addresses == ["0xA", "0xB", "0xC"]


def test_validator_set_addresses_excludes_inactive() -> None:
    vset = ValidatorSet(
        chain_id="ait-hub",
        epoch=1,
        validators=[
            _validator("0xA", is_active=True),
            _validator("0xB", is_active=False),
            _validator("0xC", is_active=True),
        ],
        threshold=2,
        total=3,
    )
    assert vset.addresses == ["0xA", "0xC"]


def test_validator_set_active_count() -> None:
    vset = ValidatorSet(
        chain_id="ait-hub",
        epoch=1,
        validators=[
            _validator("0xA", is_active=True),
            _validator("0xB", is_active=False),
            _validator("0xC", is_active=True),
            _validator("0xD", is_active=True),
        ],
        threshold=2,
        total=4,
    )
    assert vset.active_count == 3


def test_validator_set_defaults() -> None:
    vset = ValidatorSet(chain_id="ait-hub", epoch=1)
    assert vset.validators == []
    assert vset.threshold == 3
    assert vset.total == 5
    assert vset.addresses == []
    assert vset.active_count == 0


def test_threshold_proof_defaults() -> None:
    proof = _threshold_proof()
    assert proof.validator_signatures == []
    assert proof.proposer_signature == "0xprop"


def test_threshold_proof_with_validator_signatures() -> None:
    proof = _threshold_proof(validator_signatures=["0xsig1", "0xsig2"])
    assert proof.validator_signatures == ["0xsig1", "0xsig2"]


def test_bridge_proof_with_validator_signatures() -> None:
    proof = BridgeProof(
        source_chain="ait-hub",
        lock_tx_hash="0xlock",
        amount=3600,
        sender="0xSender",
        recipient="0xRecipient",
        chain_id="ait-hub",
        block_height=100,
        block_hash="0xblock",
        proposer_signature="0xprop",
        validator_signatures=["0xsig1", "0xsig2"],
    )
    assert proof.validator_signatures == ["0xsig1", "0xsig2"]


def test_bridge_proof_validator_signatures_default_empty() -> None:
    proof = BridgeProof(
        source_chain="ait-hub",
        lock_tx_hash="0xlock",
        amount=3600,
        sender="0xSender",
        recipient="0xRecipient",
        chain_id="ait-hub",
        block_height=100,
        block_hash="0xblock",
        proposer_signature="0xprop",
    )
    assert proof.validator_signatures == []


def test_bridge_config_multisig_defaults() -> None:
    cfg = BridgeConfig()
    assert cfg.multisig_enabled is False
    assert cfg.multisig_threshold == 3
    assert cfg.multisig_validators == 5


def test_bridge_config_multisig_custom() -> None:
    cfg = BridgeConfig(multisig_enabled=True, multisig_threshold=5, multisig_validators=7)
    assert cfg.multisig_enabled is True
    assert cfg.multisig_threshold == 5
    assert cfg.multisig_validators == 7


# ---------------------------------------------------------------------------
# A2 — Multi-sig utilities
# ---------------------------------------------------------------------------


def test_recover_all_signers_valid() -> None:
    sigs = ["0xsig1", "0xsig2", "0xsig3"]
    expected = ["0xVal1", "0xVal2", "0xVal3"]
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.side_effect = expected
        result = recover_all_signers({"a": 1}, sigs)
    assert result == expected
    assert mock_recover.call_count == 3


def test_recover_all_signers_skips_invalid() -> None:
    sigs = ["0xsig1", "0xsig2", "0xsig3"]
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.side_effect = ["0xVal1", None, "0xVal3"]
        result = recover_all_signers({"a": 1}, sigs)
    assert result == ["0xVal1", "0xVal3"]


def test_recover_all_signers_skips_empty() -> None:
    sigs = ["0xsig1", "", "0xsig3"]
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.side_effect = ["0xVal1", "0xVal3"]
        result = recover_all_signers({"a": 1}, sigs)
    assert result == ["0xVal1", "0xVal3"]
    assert mock_recover.call_count == 2  # empty sig skipped


def test_check_threshold_meets() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    meets, count, addrs = check_threshold(["0xA", "0xB", "0xC"], vset)
    assert meets is True
    assert count == 3
    assert addrs == ["0xA", "0xB", "0xC"]


def test_check_threshold_below() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    meets, count, _addrs = check_threshold(["0xA", "0xB"], vset)
    assert meets is False
    assert count == 2


def test_check_threshold_dedup() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    # Same signer appears twice — should only count once
    meets, count, addrs = check_threshold(["0xA", "0xA", "0xB", "0xC"], vset)
    assert meets is True
    assert count == 3
    assert addrs == ["0xA", "0xB", "0xC"]


def test_check_threshold_override() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    # Override threshold to 2 — 2 signers should now meet
    meets, count, _addrs = check_threshold(["0xA", "0xB"], vset, threshold=2)
    assert meets is True
    assert count == 2


def test_check_threshold_filters_non_members() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    # 0xF is not a member — should be filtered out
    meets, count, addrs = check_threshold(["0xA", "0xB", "0xF"], vset)
    assert meets is False
    assert count == 2
    assert "0xF" not in addrs


def test_verify_threshold_signatures_valid() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    proof = _threshold_proof(
        proposer_signature="",
        validator_signatures=["0xsigA", "0xsigB", "0xsigC"],
    )
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.side_effect = ["0xA", "0xB", "0xC"]
        meets, count, addrs = verify_threshold_signatures(proof, vset)
    assert meets is True
    assert count == 3
    assert set(addrs) == {"0xA", "0xB", "0xC"}


def test_verify_threshold_signatures_insufficient() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    proof = _threshold_proof(
        proposer_signature="",
        validator_signatures=["0xsigA", "0xsigB"],
    )
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.side_effect = ["0xA", "0xB"]
        meets, count, _addrs = verify_threshold_signatures(proof, vset)
    assert meets is False
    assert count == 2


def test_verify_threshold_signatures_non_member() -> None:
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    proof = _threshold_proof(
        proposer_signature="",
        validator_signatures=["0xsigX", "0xsigY", "0xsigZ"],
    )
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.side_effect = ["0xF", "0xG", "0xH"]  # none are members
        meets, count, addrs = verify_threshold_signatures(proof, vset)
    assert meets is False
    assert count == 0
    assert addrs == []


def test_verify_threshold_signatures_backward_compat() -> None:
    """Single proposer_signature should work as a 1-sig proof."""
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=1)
    proof = _threshold_proof(
        proposer_signature="0xpropSig",
        validator_signatures=[],  # empty — backward compat
    )
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        mock_recover.return_value = "0xA"
        meets, count, addrs = verify_threshold_signatures(proof, vset)
    assert meets is True
    assert count == 1
    assert addrs == ["0xA"]
    # proposer_signature should have been included in the sigs to verify
    assert mock_recover.call_count == 1


def test_verify_threshold_signatures_combines_proposer_and_validators() -> None:
    """Proposer sig + validator sigs are both collected."""
    vset = _validator_set(["0xA", "0xB", "0xC", "0xD", "0xE"], threshold=3)
    proof = _threshold_proof(
        proposer_signature="0xpropSig",
        validator_signatures=["0xsigB", "0xsigC"],
    )
    with patch("aitbc.bridge.multisig.recover_signer") as mock_recover:
        # First call is proposer sig, then validator sigs
        mock_recover.side_effect = ["0xA", "0xB", "0xC"]
        meets, count, _addrs = verify_threshold_signatures(proof, vset)
    assert meets is True
    assert count == 3
    assert mock_recover.call_count == 3


def test_recover_all_signers_module_reexport() -> None:
    """The module-level function is the same as the re-exported one."""
    assert recover_all_signers is _recover_all_signers


# ---------------------------------------------------------------------------
# A3 — ValidatorSetRegistry
# ---------------------------------------------------------------------------


def test_validator_registry_register_and_get() -> None:
    reg = ValidatorSetRegistry()
    reg.register_validator(_validator("0xA", epoch=1))
    reg.register_validator(_validator("0xB", epoch=1))
    vset = reg.get_validator_set("ait-hub")
    assert vset is not None
    assert set(vset.addresses) == {"0xA", "0xB"}
    assert vset.total == 2
    assert vset.epoch == 1


def test_validator_registry_get_current_epoch() -> None:
    reg = ValidatorSetRegistry()
    assert reg.get_current_epoch("ait-hub") == 0
    reg.register_validator(_validator("0xA", epoch=1))
    assert reg.get_current_epoch("ait-hub") == 1
    reg.register_validator(_validator("0xB", epoch=3))
    assert reg.get_current_epoch("ait-hub") == 3


def test_validator_registry_is_member() -> None:
    reg = ValidatorSetRegistry()
    reg.register_validator(_validator("0xA", epoch=1))
    reg.register_validator(_validator("0xB", epoch=1))
    assert reg.is_member("0xA", "ait-hub") is True
    assert reg.is_member("0xB", "ait-hub") is True
    assert reg.is_member("0xC", "ait-hub") is False


def test_validator_registry_advance_epoch() -> None:
    reg = ValidatorSetRegistry()
    reg.register_validator(_validator("0xA", epoch=1))
    reg.register_validator(_validator("0xB", epoch=1))
    assert reg.get_current_epoch("ait-hub") == 1

    new_set = _validator_set(["0xC", "0xD", "0xE"], epoch=2, threshold=2)
    new_epoch = reg.advance_epoch("ait-hub", new_set)
    assert new_epoch == 2
    assert reg.get_current_epoch("ait-hub") == 2

    # Old epoch retained (grace period)
    old_set = reg.get_validator_set("ait-hub", epoch=1)
    assert old_set is not None
    assert set(old_set.addresses) == {"0xA", "0xB"}

    # New epoch is current
    current = reg.get_validator_set("ait-hub")
    assert current is not None
    assert set(current.addresses) == {"0xC", "0xD", "0xE"}


def test_validator_registry_remove_inactive() -> None:
    reg = ValidatorSetRegistry()
    reg.register_validator(_validator("0xA", epoch=1, is_active=True))
    reg.register_validator(_validator("0xB", epoch=1, is_active=False))
    reg.register_validator(_validator("0xC", epoch=1, is_active=True))

    removed = reg.remove_inactive("ait-hub", 1)
    assert removed == 1
    vset = reg.get_validator_set("ait-hub", 1)
    assert vset is not None
    assert set(vset.addresses) == {"0xA", "0xC"}
    assert vset.total == 2


def test_validator_registry_unknown_chain() -> None:
    reg = ValidatorSetRegistry()
    assert reg.get_validator_set("nonexistent") is None
    assert reg.get_current_epoch("nonexistent") == 0
    assert reg.is_member("0xA", "nonexistent") is False


def test_validator_registry_remove_inactive_unknown_epoch() -> None:
    reg = ValidatorSetRegistry()
    assert reg.remove_inactive("ait-hub", 99) == 0


def test_validator_registry_register_replaces_existing() -> None:
    reg = ValidatorSetRegistry()
    reg.register_validator(_validator("0xA", epoch=1, public_key="0xold"))
    reg.register_validator(_validator("0xA", epoch=1, public_key="0xnew"))
    vset = reg.get_validator_set("ait-hub", 1)
    assert vset is not None
    assert len(vset.validators) == 1
    assert vset.validators[0].public_key == "0xnew"


# ---------------------------------------------------------------------------
# A4 — BridgeClient validator RPC methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_client_register_validator() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(200, {"status": "registered", "address": "0xVal1"})
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    result = await client.register_validator(
        chain_id="ait-hub",
        address="0xVal1",
        public_key="0xpub1",
        signature="0xsig1",
    )
    assert result["status"] == "registered"
    mock_http.post.assert_awaited_once()
    call = mock_http.post.await_args
    assert call.args[0] == "/bridge/validators/register"
    assert call.kwargs["json"]["chain_id"] == "ait-hub"
    assert call.kwargs["json"]["address"] == "0xVal1"
    assert call.kwargs["json"]["public_key"] == "0xpub1"
    assert call.kwargs["json"]["signature"] == "0xsig1"


@pytest.mark.asyncio
async def test_bridge_client_get_validator_set() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(
        200,
        {
            "chain_id": "ait-hub",
            "epoch": 1,
            "threshold": 3,
            "total": 5,
            "validators": [{"address": "0xA"}, {"address": "0xB"}],
        },
    )
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    result = await client.get_validator_set("ait-hub")
    assert result["chain_id"] == "ait-hub"
    assert result["epoch"] == 1
    mock_http.get.assert_awaited_once()
    call = mock_http.get.await_args
    assert call.args[0] == "/bridge/validators/ait-hub"


@pytest.mark.asyncio
async def test_bridge_client_get_validator_set_with_epoch() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(200, {"chain_id": "ait-hub", "epoch": 2})
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    await client.get_validator_set("ait-hub", epoch=2)
    call = mock_http.get.await_args
    assert call.kwargs["params"] == {"epoch": 2}


@pytest.mark.asyncio
async def test_bridge_client_security_status() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(
        200,
        {
            "multisig_enabled": True,
            "threshold": 3,
            "total_validators": 5,
            "active_validators": 4,
        },
    )
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    result = await client.security_status()
    assert result["multisig_enabled"] is True
    assert result["threshold"] == 3
    mock_http.get.assert_awaited_once()
    call = mock_http.get.await_args
    assert call.args[0] == "/bridge/security/status"


# ---------------------------------------------------------------------------
# Package re-export
# ---------------------------------------------------------------------------


def test_package_reexport_security() -> None:
    import aitbc.bridge as pkg

    assert hasattr(pkg, "ValidatorInfo")
    assert hasattr(pkg, "ValidatorSet")
    assert hasattr(pkg, "ThresholdProof")
    assert hasattr(pkg, "ValidatorSetRegistry")
    assert hasattr(pkg, "verify_threshold_signatures")
    assert hasattr(pkg, "recover_all_signers")
    assert hasattr(pkg, "check_threshold")
    assert "ValidatorInfo" in pkg.__all__
    assert "ValidatorSet" in pkg.__all__
    assert "ThresholdProof" in pkg.__all__
    assert "ValidatorSetRegistry" in pkg.__all__
    assert "verify_threshold_signatures" in pkg.__all__
