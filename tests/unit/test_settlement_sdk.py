"""Unit tests for atomic cross-chain settlement SDK (v0.9.0 §A6).

Covers:
- HTLC utilities: secret generation, hashlock computation, secret verification,
  timelock calculation (source > dest), timelock validation, state machine
- Settlement types: CrossChainEscrow defaults, EscrowProof fields,
  SettlementConfig defaults, EscrowStatus/HTLCState/ProofType enums
- Proof chaining: proof hash computation, chain building, chain verification
  (valid, broken link, wrong order, non-increasing heights)
- SettlementClient: mocked httpx for all RPC methods
- Trading types: SettlementPhase enum, InterChainTradeData with settlement fields
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc.settlement import (
    CrossChainEscrow,
    EscrowProof,
    EscrowStatus,
    HTLCState,
    HTLCStateMachine,
    ProofType,
    SettlementClient,
    SettlementConfig,
    build_execution_proof,
    build_lock_proof,
    build_release_proof,
    build_settlement_proof,
    build_verification_proof,
    calculate_dest_timelock,
    calculate_source_timelock,
    compute_hashlock,
    compute_proof_hash,
    dict_to_proof,
    generate_secret,
    proof_to_dict,
    validate_timelocks,
    verify_proof_chain,
    verify_secret,
)
from aitbc.trading import InterChainTradeData, SettlementPhase


# ---------------------------------------------------------------------------
# HTLC Utilities — secret generation
# ---------------------------------------------------------------------------


class TestSecretGeneration:
    """Tests for generate_secret() and compute_hashlock()."""

    def test_generate_secret_returns_hex_string(self) -> None:
        secret = generate_secret()
        assert isinstance(secret, str)
        # 32 bytes = 64 hex characters
        assert len(secret) == 64

    def test_generate_secret_is_hex(self) -> None:
        secret = generate_secret()
        int(secret, 16)  # raises ValueError if not hex

    def test_generate_secret_is_unique(self) -> None:
        secrets = {generate_secret() for _ in range(100)}
        assert len(secrets) == 100  # all unique

    def test_generate_secret_is_32_bytes(self) -> None:
        secret = generate_secret()
        assert len(bytes.fromhex(secret)) == 32


# ---------------------------------------------------------------------------
# HTLC Utilities — hashlock computation
# ---------------------------------------------------------------------------


class TestHashlock:
    """Tests for compute_hashlock() and verify_secret()."""

    def test_compute_hashlock_returns_sha256(self) -> None:
        secret = "a" * 64
        hashlock = compute_hashlock(secret)
        assert isinstance(hashlock, str)
        assert len(hashlock) == 64  # SHA256 = 32 bytes = 64 hex

    def test_compute_hashlock_is_deterministic(self) -> None:
        secret = "deadbeef" * 8
        h1 = compute_hashlock(secret)
        h2 = compute_hashlock(secret)
        assert h1 == h2

    def test_compute_hashlock_different_for_different_secrets(self) -> None:
        s1 = generate_secret()
        s2 = generate_secret()
        assert compute_hashlock(s1) != compute_hashlock(s2)

    def test_verify_secret_correct(self) -> None:
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        assert verify_secret(secret, hashlock) is True

    def test_verify_secret_wrong_secret(self) -> None:
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        wrong_secret = generate_secret()
        assert verify_secret(wrong_secret, hashlock) is False

    def test_verify_secret_wrong_hashlock(self) -> None:
        secret = generate_secret()
        wrong_hashlock = "0" * 64
        assert verify_secret(secret, wrong_hashlock) is False

    def test_verify_secret_empty_secret(self) -> None:
        hashlock = compute_hashlock("test")
        assert verify_secret("", hashlock) is False


# ---------------------------------------------------------------------------
# HTLC Utilities — timelock calculation
# ---------------------------------------------------------------------------


class TestTimelockCalculation:
    """Tests for calculate_source_timelock() and calculate_dest_timelock()."""

    def test_source_timelock_basic(self) -> None:
        result = calculate_source_timelock(
            current_block_height=100,
            timeout_seconds=3600,
            block_time_seconds=5,
            margin_blocks=10,
        )
        # 3600 / 5 = 720 blocks + 10 margin = 730 + 100 = 830
        assert result == 830

    def test_source_timelock_with_different_block_time(self) -> None:
        result = calculate_source_timelock(
            current_block_height=1000,
            timeout_seconds=600,
            block_time_seconds=2,
            margin_blocks=5,
        )
        # 600 / 2 = 300 + 5 = 305 + 1000 = 1305
        assert result == 1305

    def test_source_timelock_zero_timeout(self) -> None:
        result = calculate_source_timelock(
            current_block_height=100,
            timeout_seconds=0,
            block_time_seconds=5,
            margin_blocks=10,
        )
        assert result == 110  # 0 blocks + 10 margin + 100

    def test_source_timelock_invalid_block_time(self) -> None:
        with pytest.raises(ValueError, match="block_time_seconds must be positive"):
            calculate_source_timelock(100, 3600, 0)

    def test_dest_timelock_basic(self) -> None:
        # source_timelock=830, source_block_time=5, dest_block_time=5, margin=20
        # 830 * 5 = 4150 seconds / 5 = 830 - 20 = 810
        result = calculate_dest_timelock(
            source_timelock=830,
            source_block_time=5,
            dest_block_time=5,
            margin_blocks=20,
        )
        assert result == 810

    def test_dest_timelock_different_block_times(self) -> None:
        # source_timelock=1000, source_block_time=10, dest_block_time=2, margin=20
        # 1000 * 10 = 10000 seconds / 2 = 5000 - 20 = 4980
        result = calculate_dest_timelock(
            source_timelock=1000,
            source_block_time=10,
            dest_block_time=2,
            margin_blocks=20,
        )
        assert result == 4980

    def test_dest_timelock_minimum_one_block(self) -> None:
        # Very small source timelock with large margin should still be >= 1
        result = calculate_dest_timelock(
            source_timelock=5,
            source_block_time=10,
            dest_block_time=10,
            margin_blocks=100,
        )
        assert result >= 1

    def test_dest_timelock_invalid_source_block_time(self) -> None:
        with pytest.raises(ValueError, match="source_block_time must be positive"):
            calculate_dest_timelock(100, 0, 5)

    def test_dest_timelock_invalid_dest_block_time(self) -> None:
        with pytest.raises(ValueError, match="dest_block_time must be positive"):
            calculate_dest_timelock(100, 5, 0)


# ---------------------------------------------------------------------------
# HTLC Utilities — timelock validation
# ---------------------------------------------------------------------------


class TestTimelockValidation:
    """Tests for validate_timelocks()."""

    def test_valid_timelocks(self) -> None:
        # source: 200 blocks remaining * 5s = 1000s
        # dest: 100 blocks remaining * 5s = 500s
        # margin: 500s > 300s minimum
        errors = validate_timelocks(
            source_timelock=300,
            dest_timelock=200,
            source_current_height=100,
            dest_current_height=100,
            source_block_time=5,
            dest_block_time=5,
            min_margin_seconds=300,
        )
        assert errors == []

    def test_source_timelock_not_in_future(self) -> None:
        errors = validate_timelocks(
            source_timelock=100,
            dest_timelock=200,
            source_current_height=100,
            dest_current_height=100,
        )
        assert any("Source timelock" in e for e in errors)

    def test_dest_timelock_not_in_future(self) -> None:
        errors = validate_timelocks(
            source_timelock=300,
            dest_timelock=100,
            source_current_height=100,
            dest_current_height=100,
        )
        assert any("Dest timelock" in e for e in errors)

    def test_dest_expires_after_source(self) -> None:
        # source: 200 blocks * 5s = 1000s
        # dest: 300 blocks * 5s = 1500s (expires after source!)
        errors = validate_timelocks(
            source_timelock=300,
            dest_timelock=400,
            source_current_height=100,
            dest_current_height=100,
            source_block_time=5,
            dest_block_time=5,
        )
        assert any("must expire before source" in e for e in errors)

    def test_insufficient_margin(self) -> None:
        # source: 210 blocks * 5s = 1050s
        # dest: 200 blocks * 5s = 1000s
        # margin: 50s < 300s minimum
        errors = validate_timelocks(
            source_timelock=310,
            dest_timelock=300,
            source_current_height=100,
            dest_current_height=100,
            source_block_time=5,
            dest_block_time=5,
            min_margin_seconds=300,
        )
        assert any("Margin" in e for e in errors)

    def test_multiple_errors(self) -> None:
        errors = validate_timelocks(
            source_timelock=50,
            dest_timelock=50,
            source_current_height=100,
            dest_current_height=100,
        )
        assert len(errors) >= 2  # both not in future


# ---------------------------------------------------------------------------
# HTLC State Machine
# ---------------------------------------------------------------------------


class TestHTLCStateMachine:
    """Tests for HTLCStateMachine."""

    def test_valid_transition_created_to_funded(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.CREATED, HTLCState.FUNDED) is True

    def test_valid_transition_funded_to_completed(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.FUNDED, HTLCState.COMPLETED) is True

    def test_valid_transition_funded_to_refunded(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.FUNDED, HTLCState.REFUNDED) is True

    def test_valid_transition_funded_to_expired(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.FUNDED, HTLCState.EXPIRED) is True

    def test_valid_transition_expired_to_refunded(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.EXPIRED, HTLCState.REFUNDED) is True

    def test_invalid_transition_created_to_completed(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.CREATED, HTLCState.COMPLETED) is False

    def test_invalid_transition_completed_to_refunded(self) -> None:
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.COMPLETED, HTLCState.REFUNDED) is False

    def test_invalid_transition_refunded_to_anything(self) -> None:
        sm = HTLCStateMachine()
        for target in HTLCState:
            assert sm.can_transition(HTLCState.REFUNDED, target) is False

    def test_transition_returns_new_state(self) -> None:
        sm = HTLCStateMachine()
        result = sm.transition(HTLCState.CREATED, HTLCState.FUNDED)
        assert result == HTLCState.FUNDED

    def test_transition_invalid_raises(self) -> None:
        sm = HTLCStateMachine()
        with pytest.raises(ValueError, match="Invalid HTLC state transition"):
            sm.transition(HTLCState.CREATED, HTLCState.COMPLETED)

    def test_is_terminal_completed(self) -> None:
        sm = HTLCStateMachine()
        assert sm.is_terminal(HTLCState.COMPLETED) is True

    def test_is_terminal_refunded(self) -> None:
        sm = HTLCStateMachine()
        assert sm.is_terminal(HTLCState.REFUNDED) is True

    def test_is_terminal_not_funded(self) -> None:
        sm = HTLCStateMachine()
        assert sm.is_terminal(HTLCState.FUNDED) is False

    def test_full_lifecycle_happy_path(self) -> None:
        """created → funded → completed"""
        sm = HTLCStateMachine()
        state = HTLCState.CREATED
        state = sm.transition(state, HTLCState.FUNDED)
        state = sm.transition(state, HTLCState.COMPLETED)
        assert state == HTLCState.COMPLETED
        assert sm.is_terminal(state)

    def test_full_lifecycle_timeout_path(self) -> None:
        """created → funded → expired → refunded"""
        sm = HTLCStateMachine()
        state = HTLCState.CREATED
        state = sm.transition(state, HTLCState.FUNDED)
        state = sm.transition(state, HTLCState.EXPIRED)
        state = sm.transition(state, HTLCState.REFUNDED)
        assert state == HTLCState.REFUNDED
        assert sm.is_terminal(state)

    def test_full_lifecycle_direct_refund(self) -> None:
        """created → funded → refunded"""
        sm = HTLCStateMachine()
        state = HTLCState.CREATED
        state = sm.transition(state, HTLCState.FUNDED)
        state = sm.transition(state, HTLCState.REFUNDED)
        assert state == HTLCState.REFUNDED


# ---------------------------------------------------------------------------
# Settlement Types
# ---------------------------------------------------------------------------


class TestEscrowStatus:
    """Tests for EscrowStatus enum."""

    def test_all_values(self) -> None:
        assert EscrowStatus.PENDING == "pending"
        assert EscrowStatus.LOCKED == "locked"
        assert EscrowStatus.VERIFIED == "verified"
        assert EscrowStatus.EXECUTING == "executing"
        assert EscrowStatus.COMPLETED == "completed"
        assert EscrowStatus.REFUNDED == "refunded"
        assert EscrowStatus.FAILED == "failed"
        assert EscrowStatus.DISPUTED == "disputed"

    def test_count(self) -> None:
        assert len(list(EscrowStatus)) == 8


class TestHTLCState:
    """Tests for HTLCState enum."""

    def test_all_values(self) -> None:
        assert HTLCState.CREATED == "created"
        assert HTLCState.FUNDED == "funded"
        assert HTLCState.COMPLETED == "completed"
        assert HTLCState.REFUNDED == "refunded"
        assert HTLCState.EXPIRED == "expired"

    def test_count(self) -> None:
        assert len(list(HTLCState)) == 5


class TestProofType:
    """Tests for ProofType enum."""

    def test_all_values(self) -> None:
        assert ProofType.LOCK == "lock"
        assert ProofType.VERIFICATION == "verification"
        assert ProofType.EXECUTION == "execution"
        assert ProofType.RELEASE == "release"
        assert ProofType.SETTLEMENT == "settlement"

    def test_count(self) -> None:
        assert len(list(ProofType)) == 5


class TestCrossChainEscrow:
    """Tests for CrossChainEscrow dataclass."""

    def test_defaults(self) -> None:
        escrow = CrossChainEscrow(
            escrow_id="esc-1",
            trade_id="trade-1",
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="0xabc",
            recipient="0xdef",
            amount=1000,
        )
        assert escrow.asset == "native"
        assert escrow.status == EscrowStatus.PENDING
        assert escrow.secret_hash == ""
        assert escrow.secret == ""
        assert escrow.source_timelock == 0
        assert escrow.dest_timelock == 0
        assert escrow.lock_proof == {}
        assert escrow.execution_proof == {}
        assert escrow.release_proof == {}
        assert escrow.source_lock_tx_hash == ""
        assert escrow.dest_execution_tx_hash == ""
        assert escrow.source_release_tx_hash == ""
        assert escrow.dest_release_tx_hash == ""
        assert escrow.created_at == 0.0
        assert escrow.locked_at == 0.0
        assert escrow.settled_at == 0.0
        assert escrow.refunded_at == 0.0
        assert escrow.timeout_seconds == 3600
        assert escrow.timeout_extended is False

    def test_with_htlc_fields(self) -> None:
        escrow = CrossChainEscrow(
            escrow_id="esc-2",
            trade_id="trade-2",
            source_chain="ait-hub",
            dest_chain="ait-island-2",
            sender="0x111",
            recipient="0x222",
            amount=5000,
            secret_hash="abc123",
            source_timelock=1000,
            dest_timelock=900,
            timeout_seconds=7200,
        )
        assert escrow.secret_hash == "abc123"
        assert escrow.source_timelock == 1000
        assert escrow.dest_timelock == 900
        assert escrow.timeout_seconds == 7200


class TestEscrowProof:
    """Tests for EscrowProof dataclass."""

    def test_defaults(self) -> None:
        proof = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=100,
            block_hash="0xhash",
            tx_hash="0xtx",
        )
        assert proof.proposer_signature == ""
        assert proof.validator_signatures == []
        assert proof.merkle_proof == []
        assert proof.timestamp == 0.0
        assert proof.previous_proof_hash == ""

    def test_with_signatures(self) -> None:
        proof = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=100,
            block_hash="0xhash",
            tx_hash="0xtx",
            proposer_signature="0xsig",
            validator_signatures=["0xsig1", "0xsig2"],
            merkle_proof=["0xproof1", "0xproof2"],
            previous_proof_hash="0xprev",
        )
        assert proof.proposer_signature == "0xsig"
        assert len(proof.validator_signatures) == 2
        assert len(proof.merkle_proof) == 2
        assert proof.previous_proof_hash == "0xprev"


class TestSettlementConfig:
    """Tests for SettlementConfig dataclass."""

    def test_defaults(self) -> None:
        config = SettlementConfig()
        assert config.enabled is False
        assert config.htlc_enabled is True
        assert config.default_timeout_seconds == 3600
        assert config.large_trade_timeout_seconds == 86400
        assert config.max_timeout_extension_seconds == 604800
        assert config.source_timelock_margin_blocks == 10
        assert config.dest_timelock_margin_blocks == 20
        assert config.require_proof_verification is True
        assert config.require_multisig is True
        assert config.settlement_rpc_url == "http://localhost:8202"
        assert config.trading_rpc_url == "http://localhost:8104"
        assert config.timeout == 30

    def test_custom_config(self) -> None:
        config = SettlementConfig(
            enabled=True,
            default_timeout_seconds=7200,
            settlement_rpc_url="http://node1:8202",
        )
        assert config.enabled is True
        assert config.default_timeout_seconds == 7200
        assert config.settlement_rpc_url == "http://node1:8202"


# ---------------------------------------------------------------------------
# Proof Chaining
# ---------------------------------------------------------------------------


class TestProofHash:
    """Tests for compute_proof_hash()."""

    def test_hash_is_deterministic(self) -> None:
        proof = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=100,
            block_hash="0xabc",
            tx_hash="0xtx1",
        )
        h1 = compute_proof_hash(proof)
        h2 = compute_proof_hash(proof)
        assert h1 == h2

    def test_hash_changes_with_different_fields(self) -> None:
        p1 = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=100,
            block_hash="0xabc",
            tx_hash="0xtx1",
        )
        p2 = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=101,
            block_hash="0xabc",
            tx_hash="0xtx1",
        )
        assert compute_proof_hash(p1) != compute_proof_hash(p2)

    def test_hash_is_hex_string(self) -> None:
        proof = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=100,
            block_hash="0xabc",
            tx_hash="0xtx1",
        )
        h = compute_proof_hash(proof)
        assert len(h) == 64
        int(h, 16)  # valid hex


class TestProofBuilders:
    """Tests for proof builder functions."""

    def test_build_lock_proof(self) -> None:
        proof = build_lock_proof(
            source_chain="ait-hub",
            lock_tx_hash="0xlock",
            amount=1000,
            sender="0xbuyer",
            recipient="0xseller",
            block_height=100,
            block_hash="0xblock",
        )
        assert proof.proof_type == ProofType.LOCK
        assert proof.chain_id == "ait-hub"
        assert proof.tx_hash == "0xlock"
        assert proof.block_height == 100
        assert proof.previous_proof_hash == ""  # first in chain

    def test_build_verification_proof(self) -> None:
        proof = build_verification_proof(
            dest_chain="ait-island-1",
            verification_tx_hash="0xverify",
            escrow_id="esc-1",
            block_height=200,
            block_hash="0xblock2",
            previous_proof_hash="0xprev",
        )
        assert proof.proof_type == ProofType.VERIFICATION
        assert proof.chain_id == "ait-island-1"
        assert proof.previous_proof_hash == "0xprev"

    def test_build_execution_proof(self) -> None:
        proof = build_execution_proof(
            dest_chain="ait-island-1",
            execution_tx_hash="0xexec",
            trade_id="trade-1",
            block_height=210,
            block_hash="0xblock3",
            previous_proof_hash="0xprev",
        )
        assert proof.proof_type == ProofType.EXECUTION
        assert proof.chain_id == "ait-island-1"

    def test_build_release_proof(self) -> None:
        proof = build_release_proof(
            dest_chain="ait-island-1",
            release_tx_hash="0xrelease",
            escrow_id="esc-1",
            block_height=220,
            block_hash="0xblock4",
            previous_proof_hash="0xprev",
        )
        assert proof.proof_type == ProofType.RELEASE
        assert proof.chain_id == "ait-island-1"

    def test_build_settlement_proof(self) -> None:
        proof = build_settlement_proof(
            source_chain="ait-hub",
            settlement_tx_hash="0xsettle",
            escrow_id="esc-1",
            block_height=150,
            block_hash="0xblock5",
            previous_proof_hash="0xprev",
        )
        assert proof.proof_type == ProofType.SETTLEMENT
        assert proof.chain_id == "ait-hub"


class TestProofSerialization:
    """Tests for proof_to_dict() and dict_to_proof()."""

    def test_round_trip(self) -> None:
        proof = EscrowProof(
            proof_type=ProofType.EXECUTION,
            chain_id="ait-island-1",
            block_height=210,
            block_hash="0xblock",
            tx_hash="0xtx",
            proposer_signature="0xsig",
            validator_signatures=["0xs1", "0xs2"],
            merkle_proof=["0xm1"],
            timestamp=1234567890.0,
            previous_proof_hash="0xprev",
        )
        d = proof_to_dict(proof)
        restored = dict_to_proof(d)
        assert restored.proof_type == proof.proof_type
        assert restored.chain_id == proof.chain_id
        assert restored.block_height == proof.block_height
        assert restored.block_hash == proof.block_hash
        assert restored.tx_hash == proof.tx_hash
        assert restored.proposer_signature == proof.proposer_signature
        assert restored.validator_signatures == proof.validator_signatures
        assert restored.merkle_proof == proof.merkle_proof
        assert restored.timestamp == proof.timestamp
        assert restored.previous_proof_hash == proof.previous_proof_hash

    def test_dict_to_proof_missing_optional_fields(self) -> None:
        d = {
            "proof_type": "lock",
            "chain_id": "ait-hub",
            "block_height": 100,
            "block_hash": "0xhash",
            "tx_hash": "0xtx",
        }
        proof = dict_to_proof(d)
        assert proof.proof_type == ProofType.LOCK
        assert proof.proposer_signature == ""
        assert proof.validator_signatures == []
        assert proof.previous_proof_hash == ""

    def test_dict_to_proof_invalid_proof_type(self) -> None:
        d = {
            "proof_type": "invalid",
            "chain_id": "ait-hub",
            "block_height": 100,
            "block_hash": "0xhash",
            "tx_hash": "0xtx",
        }
        with pytest.raises(ValueError):
            dict_to_proof(d)


class TestVerifyProofChain:
    """Tests for verify_proof_chain()."""

    def _build_valid_chain(self) -> list[EscrowProof]:
        """Build a valid 5-proof settlement chain."""
        lock = build_lock_proof(
            source_chain="ait-hub",
            lock_tx_hash="0xlock",
            amount=1000,
            sender="0xbuyer",
            recipient="0xseller",
            block_height=100,
            block_hash="0xb1",
            timestamp=1000.0,
        )
        verification = build_verification_proof(
            dest_chain="ait-island-1",
            verification_tx_hash="0xverify",
            escrow_id="esc-1",
            block_height=200,
            block_hash="0xb2",
            previous_proof_hash=compute_proof_hash(lock),
            timestamp=2000.0,
        )
        execution = build_execution_proof(
            dest_chain="ait-island-1",
            execution_tx_hash="0xexec",
            trade_id="trade-1",
            block_height=210,
            block_hash="0xb3",
            previous_proof_hash=compute_proof_hash(verification),
            timestamp=3000.0,
        )
        release = build_release_proof(
            dest_chain="ait-island-1",
            release_tx_hash="0xrelease",
            escrow_id="esc-1",
            block_height=220,
            block_hash="0xb4",
            previous_proof_hash=compute_proof_hash(execution),
            timestamp=4000.0,
        )
        settlement = build_settlement_proof(
            source_chain="ait-hub",
            settlement_tx_hash="0xsettle",
            escrow_id="esc-1",
            block_height=150,
            block_hash="0xb5",
            previous_proof_hash=compute_proof_hash(release),
            timestamp=5000.0,
        )
        return [lock, verification, execution, release, settlement]

    def test_valid_chain(self) -> None:
        proofs = self._build_valid_chain()
        errors = verify_proof_chain(proofs)
        assert errors == []

    def test_empty_chain(self) -> None:
        errors = verify_proof_chain([])
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_broken_link(self) -> None:
        proofs = self._build_valid_chain()
        # Break the link between proof 1 and 2
        proofs[1].previous_proof_hash = "0xwrong"
        errors = verify_proof_chain(proofs)
        assert any("previous_proof_hash" in e for e in errors)

    def test_wrong_order(self) -> None:
        proofs = self._build_valid_chain()
        # Swap verification and execution
        proofs[1], proofs[2] = proofs[2], proofs[1]
        errors = verify_proof_chain(proofs)
        assert any("expected" in e for e in errors)

    def test_first_proof_has_previous_hash(self) -> None:
        proofs = self._build_valid_chain()
        proofs[0].previous_proof_hash = "0xshouldbeempty"
        errors = verify_proof_chain(proofs)
        assert any("empty" in e and "previous_proof_hash" in e for e in errors)

    def test_non_increasing_heights_same_chain(self) -> None:
        proofs = self._build_valid_chain()
        # verification and execution are on same chain (ait-island-1)
        # verification: 200, execution: 210 — make execution lower
        proofs[2].block_height = 190  # less than verification's 200
        errors = verify_proof_chain(proofs)
        assert any("block_height" in e for e in errors)

    def test_too_many_proofs(self) -> None:
        proofs = self._build_valid_chain()
        extra = build_settlement_proof(
            source_chain="ait-hub",
            settlement_tx_hash="0xextra",
            escrow_id="esc-1",
            block_height=160,
            block_hash="0xb6",
            previous_proof_hash=compute_proof_hash(proofs[-1]),
        )
        proofs.append(extra)
        errors = verify_proof_chain(proofs)
        assert any("should only have" in e for e in errors)


# ---------------------------------------------------------------------------
# SettlementClient (mocked httpx)
# ---------------------------------------------------------------------------


class TestSettlementClient:
    """Tests for SettlementClient with mocked httpx."""

    @pytest.fixture
    def mock_response(self) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = {"escrow_id": "esc-1", "status": "pending"}
        resp.raise_for_status = MagicMock()
        return resp

    @pytest.mark.asyncio
    async def test_create_escrow(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            result = await client.create_escrow(
                trade_id="trade-1",
                source_chain="ait-hub",
                dest_chain="ait-island-1",
                sender="0xbuyer",
                recipient="0xseller",
                amount=1000,
            )
            assert result["escrow_id"] == "esc-1"
            mock_client.post.assert_called_once()
            args, kwargs = mock_client.post.call_args
            assert "/bridge/settlement/create" in args[0]
            assert kwargs["json"]["trade_id"] == "trade-1"

    @pytest.mark.asyncio
    async def test_lock_escrow(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.lock_escrow("esc-1")
            args, _ = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/lock" in args[0]

    @pytest.mark.asyncio
    async def test_verify_lock(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.verify_lock("esc-1")
            args, _ = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/verify" in args[0]

    @pytest.mark.asyncio
    async def test_execute_trade(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.execute_trade("esc-1")
            args, _ = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/execute" in args[0]

    @pytest.mark.asyncio
    async def test_settle(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.settle("esc-1", "mysecret")
            args, kwargs = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/settle" in args[0]
            assert kwargs["json"]["secret"] == "mysecret"

    @pytest.mark.asyncio
    async def test_refund(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.refund("esc-1")
            args, _ = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/refund" in args[0]

    @pytest.mark.asyncio
    async def test_get_escrow(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            result = await client.get_escrow("esc-1")
            assert result["escrow_id"] == "esc-1"
            args, _ = mock_client.get.call_args
            assert "/bridge/settlement/esc-1" in args[0]

    @pytest.mark.asyncio
    async def test_get_escrow_status(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            status = await client.get_escrow_status("esc-1")
            assert status == "pending"

    @pytest.mark.asyncio
    async def test_extend_timeout(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.extend_timeout("esc-1", 3600)
            args, kwargs = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/extend-timeout" in args[0]
            assert kwargs["json"]["extension_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_file_dispute(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.file_dispute("esc-1", "quality issue", "evidence")
            args, kwargs = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/dispute" in args[0]
            assert kwargs["json"]["reason"] == "quality issue"

    @pytest.mark.asyncio
    async def test_resolve_dispute(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.resolve_dispute("esc-1", "complete")
            args, kwargs = mock_client.post.call_args
            assert "/bridge/settlement/esc-1/resolve" in args[0]
            assert kwargs["json"]["resolution"] == "complete"

    @pytest.mark.asyncio
    async def test_get_proofs(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {
            "proofs": [
                {"proof_type": "lock", "chain_id": "ait-hub", "block_height": 100, "block_hash": "0x1", "tx_hash": "0xlock"},
                {
                    "proof_type": "settlement",
                    "chain_id": "ait-hub",
                    "block_height": 150,
                    "block_hash": "0x5",
                    "tx_hash": "0xsettle",
                },
            ]
        }
        resp.raise_for_status = MagicMock()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            result = await client.get_proofs("esc-1")
            assert len(result["proofs"]) == 2

    @pytest.mark.asyncio
    async def test_get_lock_proof(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {
            "proofs": [
                {"proof_type": "lock", "chain_id": "ait-hub", "block_height": 100, "block_hash": "0x1", "tx_hash": "0xlock"},
                {
                    "proof_type": "settlement",
                    "chain_id": "ait-hub",
                    "block_height": 150,
                    "block_hash": "0x5",
                    "tx_hash": "0xsettle",
                },
            ]
        }
        resp.raise_for_status = MagicMock()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            result = await client.get_lock_proof("esc-1")
            assert result["proof_type"] == "lock"

    @pytest.mark.asyncio
    async def test_get_lock_proof_not_found(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {"proofs": []}
        resp.raise_for_status = MagicMock()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            result = await client.get_lock_proof("esc-1")
            assert result == {}

    @pytest.mark.asyncio
    async def test_lock_escrow_for_trade(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.lock_escrow_for_trade("trade-1", timeout_seconds=7200)
            args, kwargs = mock_client.post.call_args
            assert "/v1/trading/trades/trade-1/lock-escrow" in args[0]
            assert kwargs["json"]["timeout_seconds"] == 7200

    @pytest.mark.asyncio
    async def test_settle_trade(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.settle_trade("trade-1", "secret123")
            args, kwargs = mock_client.post.call_args
            assert "/v1/trading/trades/trade-1/settle" in args[0]
            assert kwargs["json"]["secret"] == "secret123"

    @pytest.mark.asyncio
    async def test_get_trade_settlement_status(self, mock_response: MagicMock) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            client = SettlementClient()
            await client.get_trade_settlement_status("trade-1")
            args, _ = mock_client.get.call_args
            assert "/v1/trading/trades/trade-1/settlement-status" in args[0]

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            async with SettlementClient() as client:
                assert client is not None
            mock_client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Trading Types — SettlementPhase
# ---------------------------------------------------------------------------


class TestSettlementPhase:
    """Tests for SettlementPhase enum."""

    def test_all_values(self) -> None:
        assert SettlementPhase.NONE == "none"
        assert SettlementPhase.ESCROW_CREATED == "escrow_created"
        assert SettlementPhase.ESCROW_LOCKED == "escrow_locked"
        assert SettlementPhase.LOCK_VERIFIED == "lock_verified"
        assert SettlementPhase.TRADE_EXECUTED == "trade_executed"
        assert SettlementPhase.SETTLED == "settled"
        assert SettlementPhase.REFUNDED == "refunded"
        assert SettlementPhase.DISPUTED == "disputed"

    def test_count(self) -> None:
        assert len(list(SettlementPhase)) == 8


class TestInterChainTradeDataSettlement:
    """Tests for InterChainTradeData settlement fields."""

    def test_settlement_defaults(self) -> None:
        trade = InterChainTradeData(
            trade_id="trade-1",
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="0xbuyer",
            recipient="0xseller",
            amount=1000,
        )
        assert trade.escrow_id == ""
        assert trade.settlement_phase == "none"
        assert trade.secret_hash == ""
        assert trade.source_timelock == 0
        assert trade.dest_timelock == 0

    def test_settlement_fields_set(self) -> None:
        trade = InterChainTradeData(
            trade_id="trade-2",
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="0xbuyer",
            recipient="0xseller",
            amount=5000,
            escrow_id="esc-1",
            settlement_phase="escrow_locked",
            secret_hash="0xhash",
            source_timelock=1000,
            dest_timelock=900,
        )
        assert trade.escrow_id == "esc-1"
        assert trade.settlement_phase == "escrow_locked"
        assert trade.secret_hash == "0xhash"
        assert trade.source_timelock == 1000
        assert trade.dest_timelock == 900
