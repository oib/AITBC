"""Unit tests for the aitbc.bridge verification layer (v0.7.2 §A4).

Covers:
- Verification types (BridgeBlockHeader, FinalityConfig,
  ProofVerificationResult, VerificationMode)
- Oracle client interface (OracleClient ABC, InProcessVerifier,
  ExternalOracleClient stub, MerkleProofVerifier protocol)
- Verification utilities (build_verification_message,
  validate_block_header, check_finality) with mocked recover_signer
- BridgeClient block header + oracle status RPC methods (mocked httpx)

No real blockchain node or crypto library required — recover_signer is
patched to return deterministic addresses.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.bridge import (
    BridgeBlockHeader,
    BridgeClient,
    BridgeConfig,
    ExternalOracleClient,
    FinalityConfig,
    InProcessVerifier,
    MerkleProofVerifier,
    OracleClient,
    ProofVerificationResult,
    VerificationMode,
    build_verification_message,
    check_finality,
    validate_block_header,
)
from aitbc.bridge import ValidatorSet

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


def _block_header(
    *,
    chain_id: str = "ait-hub",
    height: int = 100,
    hash: str = "0xblockhash",
    parent_hash: str = "0xparent",
    proposer: str = "0xProposer",
    state_root: str = "0xstateroot",
    signature: str = "0xsig",
    confirmation_count: int = 0,
    finality_confirmed: bool = False,
) -> BridgeBlockHeader:
    return BridgeBlockHeader(
        chain_id=chain_id,
        height=height,
        hash=hash,
        parent_hash=parent_hash,
        proposer=proposer,
        state_root=state_root,
        signature=signature,
        timestamp=datetime(2026, 1, 1, 0, 0, 0),
        finality_confirmed=finality_confirmed,
        confirmation_count=confirmation_count,
    )


def _validator_set(addresses: list[str], threshold: int = 3) -> ValidatorSet:
    from aitbc.bridge import ValidatorInfo

    return ValidatorSet(
        chain_id="ait-hub",
        epoch=1,
        validators=[ValidatorInfo(address=a, public_key=f"{a}pub", chain_id="ait-hub", epoch=1) for a in addresses],
        threshold=threshold,
        total=len(addresses),
    )


# ---------------------------------------------------------------------------
# A1 — Verification types
# ---------------------------------------------------------------------------


def test_verification_mode_enum() -> None:
    assert VerificationMode.IN_PROCESS.value == "in_process"
    assert VerificationMode.ORACLE.value == "oracle"


def test_verification_mode_is_str_enum() -> None:
    assert VerificationMode.IN_PROCESS == "in_process"
    assert str(VerificationMode.ORACLE) == "oracle"


def test_bridge_block_header_dataclass() -> None:
    header = _block_header(confirmation_count=5, finality_confirmed=True)
    assert header.chain_id == "ait-hub"
    assert header.height == 100
    assert header.hash == "0xblockhash"
    assert header.parent_hash == "0xparent"
    assert header.proposer == "0xProposer"
    assert header.state_root == "0xstateroot"
    assert header.signature == "0xsig"
    assert header.confirmation_count == 5
    assert header.finality_confirmed is True
    assert header.timestamp == datetime(2026, 1, 1, 0, 0, 0)


def test_bridge_block_header_defaults() -> None:
    header = BridgeBlockHeader(
        chain_id="ait-hub",
        height=1,
        hash="0xh",
        parent_hash="0xp",
        proposer="0xP",
        state_root="0xsr",
    )
    assert header.signature == ""
    assert header.timestamp is None
    assert header.finality_confirmed is False
    assert header.confirmation_count == 0


def test_finality_config_defaults() -> None:
    config = FinalityConfig()
    assert config.min_confirmations == 3
    assert config.finality_blocks == 6
    assert config.large_transfer_threshold == 10000
    assert config.grace_period_seconds == 3600


def test_finality_config_custom() -> None:
    config = FinalityConfig(
        min_confirmations=2,
        finality_blocks=10,
        large_transfer_threshold=50000,
        grace_period_seconds=7200,
    )
    assert config.min_confirmations == 2
    assert config.finality_blocks == 10
    assert config.large_transfer_threshold == 50000
    assert config.grace_period_seconds == 7200


def test_proof_verification_result_defaults() -> None:
    result = ProofVerificationResult(valid=True)
    assert result.valid is True
    assert result.error == ""
    assert result.block_height == 0
    assert result.state_root == ""
    assert result.finality_confirmed is False
    assert result.validator_epoch == 0
    assert result.verification_mode == VerificationMode.IN_PROCESS


def test_proof_verification_result_with_values() -> None:
    result = ProofVerificationResult(
        valid=False,
        error="Merkle proof failed",
        block_height=42,
        state_root="0xroot",
        finality_confirmed=True,
        validator_epoch=3,
        verification_mode=VerificationMode.ORACLE,
    )
    assert result.valid is False
    assert result.error == "Merkle proof failed"
    assert result.block_height == 42
    assert result.verification_mode == VerificationMode.ORACLE


# ---------------------------------------------------------------------------
# A2 — Oracle client interface
# ---------------------------------------------------------------------------


def test_in_process_verifier_mode() -> None:
    verifier = InProcessVerifier()
    assert verifier.mode == VerificationMode.IN_PROCESS


def test_in_process_verifier_check_finality_small_transfer() -> None:
    """Small transfers need only min_confirmations."""
    verifier = InProcessVerifier()
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    # 3 confirmations — meets min but not full finality
    header = _block_header(confirmation_count=3)
    assert verifier.check_finality(header, config, transfer_amount=5000) is True


def test_in_process_verifier_check_finality_small_transfer_below() -> None:
    verifier = InProcessVerifier()
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    header = _block_header(confirmation_count=2)
    assert verifier.check_finality(header, config, transfer_amount=5000) is False


def test_in_process_verifier_check_finality_large_transfer() -> None:
    """Large transfers need full finality_blocks."""
    verifier = InProcessVerifier()
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    # 5 confirmations — meets min but NOT full finality (6)
    header = _block_header(confirmation_count=5)
    assert verifier.check_finality(header, config, transfer_amount=50000) is False


def test_in_process_verifier_check_finality_large_transfer_meets() -> None:
    verifier = InProcessVerifier()
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    header = _block_header(confirmation_count=6)
    assert verifier.check_finality(header, config, transfer_amount=50000) is True


def test_in_process_verifier_verify_proof_state_root_mismatch() -> None:
    verifier = InProcessVerifier()
    header = _block_header(state_root="0xheader_root")
    proof = {"state_root": "0xdifferent_root", "amount": 100}
    config = FinalityConfig()
    result = verifier.verify_proof(proof, header, config)
    assert result.valid is False
    assert "State root mismatch" in result.error


def test_in_process_verifier_verify_proof_no_merkle_proof() -> None:
    """Proof without merkle_proof field — should pass (no trie verification)."""
    verifier = InProcessVerifier()
    header = _block_header(state_root="0xroot", confirmation_count=10)
    proof = {"state_root": "0xroot", "amount": 100}
    config = FinalityConfig()
    result = verifier.verify_proof(proof, header, config)
    assert result.valid is True
    assert result.finality_confirmed is True


def test_in_process_verifier_verify_proof_with_merkle_verifier_valid() -> None:
    """Merkle proof verification with a valid proof."""
    mock_verifier = MagicMock(spec=MerkleProofVerifier)
    mock_verifier.verify_merkle_proof.return_value = True
    verifier = InProcessVerifier(merkle_verifier=mock_verifier)

    header = _block_header(state_root="0xroot", confirmation_count=10)
    proof = {
        "state_root": "0xroot",
        "amount": 100,
        "lock_tx_hash": "0xlock",
        "lock_event": "0xevent",
        "merkle_proof": ["0xdeadbeef", "0xcafebabe"],
    }
    config = FinalityConfig()
    result = verifier.verify_proof(proof, header, config)
    assert result.valid is True
    mock_verifier.verify_merkle_proof.assert_called_once()


def test_in_process_verifier_verify_proof_with_merkle_verifier_invalid() -> None:
    """Merkle proof verification with an invalid proof."""
    mock_verifier = MagicMock(spec=MerkleProofVerifier)
    mock_verifier.verify_merkle_proof.return_value = False
    verifier = InProcessVerifier(merkle_verifier=mock_verifier)

    header = _block_header(state_root="0xroot")
    proof = {
        "state_root": "0xroot",
        "amount": 100,
        "lock_tx_hash": "0xlock",
        "lock_event": "0xevent",
        "merkle_proof": ["0xdeadbeef"],
    }
    config = FinalityConfig()
    result = verifier.verify_proof(proof, header, config)
    assert result.valid is False
    assert result.error == "Merkle proof verification failed"


def test_in_process_verifier_verify_proof_merkle_no_verifier_skips() -> None:
    """Merkle proof provided but no verifier set — should skip (not fail)."""
    verifier = InProcessVerifier(merkle_verifier=None)
    header = _block_header(state_root="0xroot", confirmation_count=10)
    proof = {
        "state_root": "0xroot",
        "amount": 100,
        "merkle_proof": ["0xdeadbeef"],
    }
    config = FinalityConfig()
    result = verifier.verify_proof(proof, header, config)
    assert result.valid is True  # skipped, not failed


def test_external_oracle_client_mode() -> None:
    client = ExternalOracleClient(endpoints=["http://oracle.example"])
    assert client.mode == VerificationMode.ORACLE


def test_external_oracle_client_verify_proof_no_endpoints() -> None:
    """With no endpoints, verify_proof returns an invalid result (not raise)."""
    client = ExternalOracleClient()
    result = client.verify_proof({}, _block_header(), FinalityConfig())
    assert result.valid is False
    assert "unavailable" in result.error.lower() or "all oracle" in result.error.lower()


def test_external_oracle_client_check_finality_no_endpoints() -> None:
    """With no endpoints, check_finality returns False (not raise)."""
    client = ExternalOracleClient()
    assert client.check_finality(_block_header(), FinalityConfig(), 100) is False


def test_oracle_client_is_abstract() -> None:
    """OracleClient cannot be instantiated directly."""
    with pytest.raises(TypeError):
        OracleClient()  # type: ignore[abstract]


def test_merkle_proof_verifier_protocol() -> None:
    """MerkleProofVerifier is a runtime-checkable protocol."""

    class FakeVerifier:
        def verify_merkle_proof(
            self,
            state_root: str,
            key: str,
            value: str,
            proof: list[bytes],
        ) -> bool:
            return True

    assert isinstance(FakeVerifier(), MerkleProofVerifier)


# ---------------------------------------------------------------------------
# A3 — Verification utilities
# ---------------------------------------------------------------------------


def test_build_verification_message() -> None:
    header = _block_header()
    msg = build_verification_message(header)
    assert msg["chain_id"] == "ait-hub"
    assert msg["height"] == 100
    assert msg["hash"] == "0xblockhash"
    assert msg["parent_hash"] == "0xparent"
    assert msg["proposer"] == "0xProposer"
    assert msg["state_root"] == "0xstateroot"
    # signature should NOT be in the message
    assert "signature" not in msg
    # finality/confirmation fields should NOT be in the message
    assert "finality_confirmed" not in msg
    assert "confirmation_count" not in msg
    assert "timestamp" not in msg


def test_validate_block_header_valid() -> None:
    header = _block_header(signature="0xvalidsig")
    with patch("aitbc.bridge.verification.recover_signer") as mock_recover:
        mock_recover.return_value = "0xProposer"
        valid, error, recovered = validate_block_header(header)
    assert valid is True
    assert error == ""
    assert recovered == "0xProposer"


def test_validate_block_header_with_validator_set_member() -> None:
    header = _block_header(signature="0xvalidsig")
    vset = _validator_set(["0xProposer", "0xB", "0xC"])
    with patch("aitbc.bridge.verification.recover_signer") as mock_recover:
        mock_recover.return_value = "0xProposer"
        valid, error, recovered = validate_block_header(header, vset)
    assert valid is True
    assert recovered == "0xProposer"


def test_validate_block_header_with_validator_set_non_member() -> None:
    header = _block_header(signature="0xvalidsig")
    vset = _validator_set(["0xA", "0xB", "0xC"])
    with patch("aitbc.bridge.verification.recover_signer") as mock_recover:
        mock_recover.return_value = "0xIntruder"
        valid, error, recovered = validate_block_header(header, vset)
    assert valid is False
    assert "not in validator set" in error
    assert recovered == "0xIntruder"


def test_validate_block_header_case_insensitive_membership() -> None:
    """Validator set stores lowercase, recover_signer returns checksum."""
    header = _block_header(signature="0xvalidsig")
    vset = _validator_set(["0xproposer", "0xb", "0xc"])  # lowercase
    with patch("aitbc.bridge.verification.recover_signer") as mock_recover:
        mock_recover.return_value = "0xProposer"  # checksum
        valid, _error, _recovered = validate_block_header(header, vset)
    assert valid is True


def test_validate_block_header_no_signature() -> None:
    header = _block_header(signature="")
    valid, error, recovered = validate_block_header(header)
    assert valid is False
    assert error == "Block header has no signature"
    assert recovered is None


def test_validate_block_header_invalid_signature() -> None:
    header = _block_header(signature="0xbadsig")
    with patch("aitbc.bridge.verification.recover_signer") as mock_recover:
        mock_recover.return_value = None
        valid, error, recovered = validate_block_header(header)
    assert valid is False
    assert error == "Invalid block header signature"
    assert recovered is None


def test_check_finality_meets_threshold() -> None:
    header = _block_header(confirmation_count=6)
    config = FinalityConfig(min_confirmations=3, finality_blocks=6)
    has_finality, required = check_finality(header, config, transfer_amount=5000)
    assert has_finality is True
    assert required == 3


def test_check_finality_below_threshold() -> None:
    header = _block_header(confirmation_count=2)
    config = FinalityConfig(min_confirmations=3, finality_blocks=6)
    has_finality, required = check_finality(header, config, transfer_amount=5000)
    assert has_finality is False
    assert required == 3


def test_check_finality_large_transfer_requires_more() -> None:
    """Large transfer needs finality_blocks, not just min_confirmations."""
    header = _block_header(confirmation_count=4)
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    has_finality, required = check_finality(header, config, transfer_amount=50000)
    assert has_finality is False
    assert required == 6


def test_check_finality_large_transfer_meets() -> None:
    header = _block_header(confirmation_count=6)
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    has_finality, required = check_finality(header, config, transfer_amount=50000)
    assert has_finality is True
    assert required == 6


def test_check_finality_exact_threshold() -> None:
    """Transfer amount exactly at threshold should require full finality."""
    header = _block_header(confirmation_count=6)
    config = FinalityConfig(min_confirmations=3, finality_blocks=6, large_transfer_threshold=10000)
    has_finality, required = check_finality(header, config, transfer_amount=10000)
    assert has_finality is True
    assert required == 6  # exactly at threshold → full finality


# ---------------------------------------------------------------------------
# A4 — BridgeClient block header + oracle status RPC methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_client_get_block_header() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(
        200,
        {
            "chain_id": "ait-hub",
            "height": 100,
            "hash": "0xblockhash",
            "state_root": "0xroot",
            "proposer": "0xProposer",
            "signature": "0xsig",
            "finality_confirmed": True,
            "confirmation_count": 6,
        },
    )
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    result = await client.get_block_header("ait-hub", 100)
    assert result["chain_id"] == "ait-hub"
    assert result["height"] == 100
    assert result["state_root"] == "0xroot"
    mock_http.get.assert_awaited_once()
    call = mock_http.get.await_args
    assert call.args[0] == "/bridge/block-headers/ait-hub/100"


@pytest.mark.asyncio
async def test_bridge_client_store_block_header() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(200, {"status": "stored", "height": 100})
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    header_data = {
        "chain_id": "ait-hub",
        "height": 100,
        "hash": "0xblockhash",
        "parent_hash": "0xparent",
        "proposer": "0xProposer",
        "state_root": "0xroot",
        "signature": "0xsig",
    }
    result = await client.store_block_header(header_data)
    assert result["status"] == "stored"
    mock_http.post.assert_awaited_once()
    call = mock_http.post.await_args
    assert call.args[0] == "/bridge/block-headers"
    assert call.kwargs["json"]["chain_id"] == "ait-hub"
    assert call.kwargs["json"]["signature"] == "0xsig"


@pytest.mark.asyncio
async def test_bridge_client_oracle_status() -> None:
    client = BridgeClient(BridgeConfig(rpc_url=RPC_URL))
    resp = _mock_response(
        200,
        {
            "verification_mode": "in_process",
            "finality_blocks": 6,
            "min_confirmations": 3,
            "validator_sets": {"ait-hub": {"epoch": 1, "validators": 5}},
            "block_headers_stored": {"ait-hub": 42},
        },
    )
    mock_http = _mock_async_client(resp)
    client._client = mock_http

    result = await client.oracle_status()
    assert result["verification_mode"] == "in_process"
    assert result["finality_blocks"] == 6
    mock_http.get.assert_awaited_once()
    call = mock_http.get.await_args
    assert call.args[0] == "/bridge/oracle/status"


# ---------------------------------------------------------------------------
# Package re-export
# ---------------------------------------------------------------------------


def test_package_reexport_verification() -> None:
    import aitbc.bridge as pkg

    assert hasattr(pkg, "BridgeBlockHeader")
    assert hasattr(pkg, "FinalityConfig")
    assert hasattr(pkg, "ProofVerificationResult")
    assert hasattr(pkg, "VerificationMode")
    assert hasattr(pkg, "OracleClient")
    assert hasattr(pkg, "InProcessVerifier")
    assert hasattr(pkg, "ExternalOracleClient")
    assert hasattr(pkg, "MerkleProofVerifier")
    assert hasattr(pkg, "validate_block_header")
    assert hasattr(pkg, "check_finality")
    assert hasattr(pkg, "build_verification_message")
    assert "BridgeBlockHeader" in pkg.__all__
    assert "FinalityConfig" in pkg.__all__
    assert "ProofVerificationResult" in pkg.__all__
    assert "VerificationMode" in pkg.__all__
    assert "OracleClient" in pkg.__all__
    assert "InProcessVerifier" in pkg.__all__
    assert "ExternalOracleClient" in pkg.__all__
    assert "MerkleProofVerifier" in pkg.__all__
    assert "validate_block_header" in pkg.__all__
    assert "check_finality" in pkg.__all__
    assert "build_verification_message" in pkg.__all__
